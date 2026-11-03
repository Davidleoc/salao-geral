"""
Cobrança da assinatura do salão — teste grátis, vencimento, atraso e suspensão.

Ciclo de vida (Assinatura.status):
  TESTE ──(fim do teste)──► AGUARDANDO_PAGAMENTO ──(admin confirma)──► ATIVO
  ATIVO ──(venceu)──► EM_ATRASO ──(passou DIAS_TOLERANCIA_ATRASO)──► SUSPENSO
  qualquer ──(admin/contratante)──► CANCELADO

Régua automática (tarefa_cobranca, uma vez por dia por assinatura):
  - Faltando DIAS_AVISO_VENCIMENTO dias ou menos: e-mail TODO DIA ao contratante + aviso no painel
  - No dia do vencimento: e-mail "vence hoje"
  - Em atraso: e-mail diário com a data da suspensão; admin avisado
  - Passou a tolerância: suspende o salão e avisa os dois lados
O teste grátis segue a mesma régua, com mensagens próprias.

Todas as ações do admin passam por aqui e ficam na auditoria.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.assinatura import Assinatura, Periodicidade, StatusAssinatura
from app.models.log_seguranca import EventoSeguranca
from app.models.pagamento_assinatura import PagamentoAssinatura
from app.models.plano import Plano
from app.models.salao import Salao
from app.services.auditoria import registrar_evento
from app.services.email_service import email_sistema
from app.services.envios import primeira_vez
from app.services.notificacoes import notificar_admin, notificar_salao

STATUS_COM_ACESSO = {StatusAssinatura.TESTE, StatusAssinatura.ATIVO, StatusAssinatura.EM_ATRASO, StatusAssinatura.PAGO}


def brl(valor) -> str:
    return "R$ " + f"{float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dias_do_ciclo(assinatura: Assinatura) -> int:
    return 365 if assinatura.periodicidade == Periodicidade.ANUAL else 30


def dias_restantes(assinatura: Assinatura) -> Optional[int]:
    return (assinatura.data_fim - date.today()).days if assinatura.data_fim else None


# ---------------------------------------------------------------------------
# Pix "copia e cola" (padrão BR Code do Banco Central, sem QR em imagem)
# ---------------------------------------------------------------------------
def _campo(id_: str, valor: str) -> str:
    return f"{id_}{len(valor):02d}{valor}"


def _crc16(texto: str) -> str:
    crc = 0xFFFF
    for byte in texto.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def pix_copia_e_cola(valor: Decimal, identificador: str) -> Optional[str]:
    if not settings.PIX_CHAVE:
        return None
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", settings.PIX_CHAVE)
    txid = "".join(c for c in identificador if c.isalnum())[:25] or "***"
    payload = (
        _campo("00", "01") + _campo("26", conta) + _campo("52", "0000") + _campo("53", "986")
        + _campo("54", f"{float(valor):.2f}") + _campo("58", "BR")
        + _campo("59", settings.PIX_NOME_RECEBEDOR[:25]) + _campo("60", settings.PIX_CIDADE[:15])
        + _campo("62", _campo("05", txid)) + "6304"
    )
    return payload + _crc16(payload)


def _instrucoes_pagamento(salao: Salao, assinatura: Assinatura) -> tuple[list[str], Optional[str]]:
    valor = assinatura.valor_cobrado or Decimal("0")
    pix = pix_copia_e_cola(valor, f"SALAO{salao.id}A{assinatura.id}")
    if pix:
        return ([f"Valor: {brl(valor)}. Pague pelo app do seu banco usando o Pix copia e cola abaixo "
                 "(opção “Pix copia e cola” ou “Pagar com código”)."], pix)
    return ([f"Valor: {brl(valor)}. Nossa equipe enviará os dados do Pix para este e-mail em seguida."], None)


# ---------------------------------------------------------------------------
# Teste grátis
# ---------------------------------------------------------------------------
def iniciar_teste(db: Session, salao: Salao, request=None) -> bool:
    """Chamado quando o dono confirma o e-mail. Começa a contar os dias do teste."""
    a = salao.assinatura
    if not a or a.status != StatusAssinatura.TESTE or a.data_fim is not None:
        return False
    hoje = date.today()
    a.data_inicio = hoje
    a.data_fim = hoje + timedelta(days=settings.DIAS_TESTE)
    salao.ativo = True
    db.commit()
    email_sistema(salao.email_principal, f"Seu teste grátis começou — {settings.APP_NAME}",
                  f"Bem-vindo! Seu teste de {settings.DIAS_TESTE} dias começou",
                  [f"O {salao.nome} já pode usar todos os recursos do plano {a.plano.nome}.",
                   f"O teste vai até {a.data_fim:%d/%m/%Y}. Antes disso avisaremos por e-mail como continuar."],
                  botao_texto="Entrar no painel", botao_url="/minhaagenda/login", tipo="TESTE_INICIO")
    notificar_admin(db, "teste", "Novo teste grátis", f"{salao.nome} — até {a.data_fim:%d/%m}",
                    link=f"/admin/saloes/{salao.id}", salao_id=salao.id)
    return True


def encerrar_teste(db: Session, assinatura: Assinatura, admin=None, request=None) -> None:
    salao = assinatura.salao
    assinatura.status = StatusAssinatura.AGUARDANDO_PAGAMENTO
    assinatura.data_fim = date.today()
    salao.ativo = False
    db.commit()
    paragrafos, pix = _instrucoes_pagamento(salao, assinatura)
    email_sistema(salao.email_principal, f"Seu teste grátis terminou — {settings.APP_NAME}",
                  "Seu teste grátis terminou",
                  [f"Obrigado por testar o {settings.APP_NAME} com o {salao.nome}!",
                   "Para continuar usando a agenda e manter sua página no ar, confirme a assinatura:"] + paragrafos
                  + ["Seus dados continuam guardados: assim que o pagamento for confirmado, tudo volta como estava."],
                  destaque=pix, tipo="TESTE_FIM")
    if admin is not None:
        registrar_evento(db, EventoSeguranca.ASSINATURA_ALTERADA, request, usuario_id=admin.id, salao_id=salao.id,
                         descricao=f"Teste grátis encerrado pelo admin (assinatura {assinatura.id})")
    notificar_salao(db, salao.id, "assinatura", "Teste grátis encerrado",
                    "Confirme a assinatura para continuar usando o sistema.", link="/minhaagenda/assinatura",
                    papeis=["DONO"])


def renovar_teste(db: Session, assinatura: Assinatura, admin, request=None, dias: Optional[int] = None) -> None:
    dias = dias or settings.DIAS_TESTE
    salao = assinatura.salao
    base = max(assinatura.data_fim or date.today(), date.today())
    assinatura.status = StatusAssinatura.TESTE
    assinatura.data_inicio = assinatura.data_inicio or date.today()
    assinatura.data_fim = base + timedelta(days=dias)
    salao.ativo = True
    db.commit()
    email_sistema(salao.email_principal, f"Seu teste grátis foi estendido — {settings.APP_NAME}",
                  "Ganhamos mais tempo juntos!",
                  [f"Estendemos o teste grátis do {salao.nome} por mais {dias} dias.",
                   f"Novo prazo: {assinatura.data_fim:%d/%m/%Y}."],
                  botao_texto="Entrar no painel", botao_url="/minhaagenda/login", tipo="TESTE_RENOVADO")
    registrar_evento(db, EventoSeguranca.ASSINATURA_ALTERADA, request, usuario_id=admin.id, salao_id=salao.id,
                     descricao=f"Teste grátis estendido por {dias} dias até {assinatura.data_fim:%d/%m/%Y}")


# ---------------------------------------------------------------------------
# Pagamento, suspensão, cancelamento (ações do admin)
# ---------------------------------------------------------------------------
def confirmar_pagamento(db: Session, assinatura: Assinatura, admin, request=None, forma: str = "PIX") -> PagamentoAssinatura:
    """Ativa (ou renova) a assinatura por mais um ciclo e registra o pagamento."""
    hoje = date.today()
    salao = assinatura.salao
    tolerancia = hoje - timedelta(days=settings.DIAS_TOLERANCIA_ATRASO)
    mantem_ciclo = (assinatura.status in (StatusAssinatura.ATIVO, StatusAssinatura.EM_ATRASO)
                    and assinatura.data_fim and assinatura.data_fim >= tolerancia)
    inicio = assinatura.data_fim if mantem_ciclo else hoje
    fim = inicio + timedelta(days=dias_do_ciclo(assinatura))

    pagamento = PagamentoAssinatura(
        assinatura_id=assinatura.id, salao_id=salao.id, valor=assinatura.valor_cobrado or Decimal("0"),
        periodo_inicio=inicio, periodo_fim=fim, forma=forma, confirmado_por_id=admin.id if admin else None,
    )
    db.add(pagamento)
    assinatura.status = StatusAssinatura.ATIVO
    assinatura.data_pagamento = datetime.now(timezone.utc)
    assinatura.data_inicio = assinatura.data_inicio or hoje
    assinatura.data_fim = fim
    salao.ativo = True
    db.commit()

    registrar_evento(db, EventoSeguranca.PAGAMENTO_CONFIRMADO, request, usuario_id=admin.id if admin else None,
                     salao_id=salao.id, descricao=f"{brl(pagamento.valor)} — período {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")
    email_sistema(salao.email_principal, f"Pagamento confirmado — {settings.APP_NAME}", "Pagamento confirmado!",
                  [f"Recebemos o pagamento da assinatura do {salao.nome} ({brl(pagamento.valor)}).",
                   f"Sua assinatura está ativa até {fim:%d/%m/%Y}."],
                  botao_texto="Entrar no painel", botao_url="/minhaagenda/login", tipo="PAGAMENTO_CONFIRMADO")
    notificar_salao(db, salao.id, "assinatura", "Pagamento confirmado", f"Assinatura ativa até {fim:%d/%m/%Y}.",
                    link="/minhaagenda/assinatura", papeis=["DONO"])
    return pagamento


def suspender(db: Session, assinatura: Assinatura, motivo: str, admin=None, request=None) -> None:
    salao = assinatura.salao
    assinatura.status = StatusAssinatura.SUSPENSO
    salao.ativo = False
    db.commit()
    paragrafos, pix = _instrucoes_pagamento(salao, assinatura)
    email_sistema(salao.email_principal, f"Assinatura suspensa — {settings.APP_NAME}", "Sua assinatura foi suspensa",
                  [motivo, "Sua página de agendamento e o painel ficam indisponíveis até a regularização."] + paragrafos
                  + ["Nenhum dado foi apagado: ao regularizar, tudo volta como estava."],
                  destaque=pix, tipo="ASSINATURA_SUSPENSA")
    registrar_evento(db, EventoSeguranca.ASSINATURA_ALTERADA, request, usuario_id=admin.id if admin else None,
                     salao_id=salao.id, descricao=f"Suspensa: {motivo}")
    notificar_admin(db, "assinatura", "Assinatura suspensa", f"{salao.nome} — {motivo}",
                    link=f"/admin/saloes/{salao.id}", salao_id=salao.id)


def cancelar(db: Session, assinatura: Assinatura, motivo: str, usuario=None, request=None) -> None:
    salao = assinatura.salao
    assinatura.status = StatusAssinatura.CANCELADO
    assinatura.cancelada_em = datetime.now(timezone.utc)
    salao.ativo = False
    db.commit()
    registrar_evento(db, EventoSeguranca.ASSINATURA_ALTERADA, request, usuario_id=usuario.id if usuario else None,
                     salao_id=salao.id, descricao=f"Cancelada: {motivo}")


# ---------------------------------------------------------------------------
# Régua automática (roda nas tarefas automáticas)
# ---------------------------------------------------------------------------
def _email_cobranca(salao, assinatura, titulo, paragrafos_extra, tipo):
    paragrafos, pix = _instrucoes_pagamento(salao, assinatura)
    email_sistema(salao.email_principal, f"{titulo} — {settings.APP_NAME}", titulo,
                  paragrafos_extra + paragrafos, destaque=pix,
                  botao_texto="Ver minha assinatura", botao_url="/minhaagenda/assinatura", tipo=tipo)


def tarefa_cobranca(db: Session) -> int:
    hoje = date.today()
    acoes = 0
    assinaturas = (db.query(Assinatura)
                   .filter(Assinatura.status.in_([StatusAssinatura.TESTE, StatusAssinatura.ATIVO, StatusAssinatura.EM_ATRASO]),
                           Assinatura.data_fim.isnot(None))
                   .all())
    for a in assinaturas:
        salao = a.salao
        if not salao or salao.encerrado_em:
            continue
        dias = (a.data_fim - hoje).days
        chave_dia = f"{a.id}:{hoje.isoformat()}"

        if a.status == StatusAssinatura.TESTE:
            if 0 <= dias <= settings.DIAS_AVISO_VENCIMENTO and primeira_vez(db, f"teste:aviso:{chave_dia}"):
                quando = "hoje" if dias == 0 else f"em {dias} dia{'s' if dias > 1 else ''}"
                _email_cobranca(salao, a, f"Seu teste grátis termina {quando}",
                                [f"O teste grátis do {salao.nome} vai até {a.data_fim:%d/%m/%Y}.",
                                 "Para não perder o acesso à agenda e à sua página, confirme a assinatura:"], "TESTE_AVISO")
                notificar_salao(db, salao.id, "assinatura", f"Teste grátis termina {quando}",
                                "Confirme a assinatura para continuar.", link="/minhaagenda/assinatura", papeis=["DONO"])
                acoes += 1
            elif dias < 0 and primeira_vez(db, f"teste:fim:{a.id}:{a.data_fim.isoformat()}"):
                encerrar_teste(db, a)
                notificar_admin(db, "teste", "Teste grátis terminou", salao.nome, link=f"/admin/saloes/{salao.id}", salao_id=salao.id)
                acoes += 1

        elif a.status == StatusAssinatura.ATIVO:
            if 0 <= dias <= settings.DIAS_AVISO_VENCIMENTO and primeira_vez(db, f"venc:aviso:{chave_dia}"):
                quando = "vence hoje" if dias == 0 else f"vence em {dias} dia{'s' if dias > 1 else ''}"
                _email_cobranca(salao, a, f"Sua assinatura {quando}",
                                [f"A assinatura do {salao.nome} {quando} ({a.data_fim:%d/%m/%Y})."], "VENCIMENTO_AVISO")
                notificar_salao(db, salao.id, "assinatura", f"Assinatura {quando}", f"Vencimento: {a.data_fim:%d/%m/%Y}",
                                link="/minhaagenda/assinatura", papeis=["DONO"])
                acoes += 1
            elif dias < 0:
                a.status = StatusAssinatura.EM_ATRASO
                db.commit()
                notificar_admin(db, "assinatura", "Assinatura em atraso", f"{salao.nome} — venceu em {a.data_fim:%d/%m}",
                                link=f"/admin/saloes/{salao.id}", salao_id=salao.id)
                acoes += 1
                dias_atraso = -dias
                if primeira_vez(db, f"atraso:aviso:{chave_dia}"):
                    _aviso_atraso(db, salao, a, dias_atraso)

        elif a.status == StatusAssinatura.EM_ATRASO:
            dias_atraso = -dias
            if dias_atraso > settings.DIAS_TOLERANCIA_ATRASO:
                if primeira_vez(db, f"susp:{a.id}:{a.data_fim.isoformat()}"):
                    suspender(db, a, f"A assinatura do {salao.nome} está em atraso há {dias_atraso} dias.")
                    acoes += 1
            elif primeira_vez(db, f"atraso:aviso:{chave_dia}"):
                _aviso_atraso(db, salao, a, dias_atraso)
                acoes += 1
    db.commit()
    return acoes


def _aviso_atraso(db, salao, a, dias_atraso):
    faltam = max(0, settings.DIAS_TOLERANCIA_ATRASO - dias_atraso)
    data_suspensao = a.data_fim + timedelta(days=settings.DIAS_TOLERANCIA_ATRASO + 1)
    _email_cobranca(salao, a, "Assinatura em atraso",
                    [f"A assinatura do {salao.nome} venceu em {a.data_fim:%d/%m/%Y} ({dias_atraso} dia(s) de atraso).",
                     f"Para evitar a suspensão em {data_suspensao:%d/%m/%Y}" + (f" (faltam {faltam} dias)" if faltam else "")
                     + ", faça o pagamento:"], "ATRASO_AVISO")
    notificar_salao(db, salao.id, "assinatura", "Assinatura em atraso",
                    f"Suspensão em {data_suspensao:%d/%m/%Y} se não houver pagamento.", link="/minhaagenda/assinatura",
                    papeis=["DONO"])


def enviar_cobranca_inicial(salao: Salao, assinatura: Assinatura, motivo: str) -> None:
    """Contratação sem teste grátis (ex: documento já usado em outra conta)."""
    _email_cobranca(salao, assinatura, "Confirme sua assinatura", [motivo], "COBRANCA_INICIAL")
