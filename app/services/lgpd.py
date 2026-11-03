"""
LGPD — portabilidade, encerramento de conta e retenção automática.

  exportar_zip(db, salao)        → ZIP com dados.json + CSVs (direito de portabilidade, todos os planos)
  encerrar_conta(...)            → cancela a assinatura e agenda a exclusão para daqui a PRAZO_EXCLUSAO_CONTA_DIAS
  anonimizar_salao(db, salao)    → apaga/anonimiza dados pessoais, mantendo só números financeiros
  tarefa_retencao(db)            → roda nas tarefas automáticas (uma vez por dia)

Retenção (config.py):
  - logs de segurança/auditoria: RETENCAO_LOGS_DIAS
  - avisos do painel (90 dias), controle de envios (120), pedidos de senha e convites antigos
  - lista de espera de dias que já passaram (30 dias)
  - clientes sem atendimento há RETENCAO_CLIENTE_INATIVO_MESES → anonimizados
  - salões encerrados após o prazo → anonimizados

O que fica depois da anonimização: valores e datas dos atendimentos (obrigação fiscal/contábil),
sem nenhum dado que identifique a pessoa.
"""

import csv
import io
import json
import secrets
import zipfile
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agendamento import Agendamento
from app.models.avaliacao_atendimento import AvaliacaoAtendimento
from app.models.cliente import Cliente
from app.models.convite_equipe import ConviteEquipe
from app.models.envio_automatico import EnvioAutomatico
from app.models.foto_salao import FotoSalao
from app.models.lista_espera import ListaEspera
from app.models.log_seguranca import EventoSeguranca, LogSeguranca
from app.models.notificacao import Notificacao
from app.models.notificacao_painel import NotificacaoPainel
from app.models.pacote import Pacote, PacoteCliente
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.solicitacao_senha import SolicitacaoSenha
from app.models.usuario import Usuario
from app.permissoes import ROTULOS, papel_de
from app.security import hash_senha
from app.services import uploads
from app.services.auditoria import registrar_evento
from app.services.email_service import email_sistema
from app.services.notificacoes import notificar_admin

PREFIXO_ANONIMO = "anon-"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if hasattr(v, "value"):
        return v.value
    return str(v)


# ---------------------------------------------------------------------------
# Portabilidade
# ---------------------------------------------------------------------------
def _tabelas(db: Session, salao: Salao) -> dict[str, list[dict]]:
    sid = salao.id
    servicos = db.query(Servico).filter(Servico.salao_id == sid).order_by(Servico.id).all()
    clientes = db.query(Cliente).filter(Cliente.salao_id == sid).order_by(Cliente.id).all()
    equipe = db.query(Usuario).filter(Usuario.salao_id == sid).order_by(Usuario.id).all()
    agendamentos = (db.query(Agendamento).filter(Agendamento.salao_id == sid)
                    .order_by(Agendamento.data, Agendamento.hora_inicio).all())
    pacotes = db.query(Pacote).filter(Pacote.salao_id == sid).order_by(Pacote.id).all()
    vendidos = db.query(PacoteCliente).filter(PacoteCliente.salao_id == sid).order_by(PacoteCliente.id).all()
    avaliacoes = (db.query(AvaliacaoAtendimento)
                  .filter(AvaliacaoAtendimento.salao_id == sid, AvaliacaoAtendimento.respondido_em.isnot(None)).all())

    return {
        "servicos": [{"id": s.id, "nome": s.nome, "descricao": s.descricao, "preco": _txt(s.preco),
                      "custo": _txt(s.custo), "duracao_minutos": s.duracao_minutos, "ativo": s.ativo} for s in servicos],
        "clientes": [{"id": c.id, "nome": c.nome, "telefone": c.telefone, "email": c.email,
                      "observacoes": c.observacoes, "criado_em": _txt(c.criado_em)} for c in clientes],
        "equipe": [{"id": u.id, "nome": u.nome, "email": u.email, "funcao": ROTULOS.get(papel_de(u), papel_de(u)),
                    "especialidade": u.especialidade, "comissao_percentual": _txt(u.comissao_percentual),
                    "ativo": u.ativo} for u in equipe],
        "agendamentos": [{"id": a.id, "data": _txt(a.data), "inicio": _txt(a.hora_inicio), "fim": _txt(a.hora_fim),
                          "cliente_id": a.cliente_id, "cliente": a.cliente.nome if a.cliente else "",
                          "servico": a.servico.nome if a.servico else "", "profissional": a.profissional.nome if a.profissional else "",
                          "valor": _txt(a.valor), "custo": _txt(a.custo), "comissao_percentual": _txt(a.comissao_percentual),
                          "pago_com_pacote": bool(a.pacote_cliente_id), "forma_pagamento": _txt(a.forma_pagamento),
                          "status": _txt(a.status), "observacoes": a.observacoes,
                          "motivo_cancelamento": a.motivo_cancelamento} for a in agendamentos],
        "pacotes": [{"id": p.id, "nome": p.nome, "tipo": p.tipo, "sessoes": p.quantidade_sessoes,
                     "preco": _txt(p.preco), "validade_dias": p.validade_dias, "ativo": p.ativo} for p in pacotes],
        "pacotes_vendidos": [{"id": v.id, "pacote": v.pacote.nome if v.pacote else "", "cliente_id": v.cliente_id,
                              "sessoes_total": v.sessoes_total, "sessoes_usadas": v.sessoes_usadas,
                              "valor_pago": _txt(v.valor_pago), "inicio": _txt(v.inicio), "validade": _txt(v.validade),
                              "status": v.status} for v in vendidos],
        "avaliacoes": [{"agendamento_id": av.agendamento_id, "nota": av.nota, "comentario": av.comentario,
                        "respondido_em": _txt(av.respondido_em)} for av in avaliacoes],
    }


def exportar_zip(db: Session, salao: Salao) -> bytes:
    """Todos os dados do salão: dados.json (completo) + um CSV por tabela (abre no Excel)."""
    tabelas = _tabelas(db, salao)
    a = salao.assinatura
    cabecalho = {
        "gerado_em": _agora().isoformat(),
        "sistema": settings.APP_NAME,
        "salao": {"nome": salao.nome, "endereco_publico": f"/{salao.slug}", "email": salao.email_principal,
                  "telefone": salao.telefone, "whatsapp": salao.whatsapp, "instagram": salao.instagram,
                  "endereco": salao.endereco, "cidade": salao.cidade, "estado": salao.estado, "cep": salao.cep,
                  "documento": salao.documento, "tipo_documento": salao.tipo_documento,
                  "descricao": salao.descricao, "sobre": salao.sobre, "criado_em": _txt(salao.criado_em)},
        "assinatura": {"plano": a.plano.nome if a and a.plano else None, "status": _txt(a.status) if a else None,
                       "inicio": _txt(a.data_inicio) if a else None, "vencimento": _txt(a.data_fim) if a else None},
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("dados.json", json.dumps({**cabecalho, **tabelas}, ensure_ascii=False, indent=2))
        for nome, linhas in tabelas.items():
            if not linhas:
                continue
            saida = io.StringIO()
            escritor = csv.DictWriter(saida, fieldnames=list(linhas[0].keys()), delimiter=";")
            escritor.writeheader()
            for linha in linhas:
                escritor.writerow({k: _txt(v) for k, v in linha.items()})
            # BOM para o Excel reconhecer os acentos
            z.writestr(f"{nome}.csv", "﻿" + saida.getvalue())
        z.writestr("LEIA-ME.txt",
                   f"Exportação dos dados do {salao.nome} — {settings.APP_NAME}\n\n"
                   "dados.json  — tudo, em formato aberto (pode ser importado em outro sistema)\n"
                   "*.csv       — uma planilha por assunto (separador ;), abre no Excel/Google Planilhas\n")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Encerramento e anonimização
# ---------------------------------------------------------------------------
def encerrar_conta(db: Session, salao: Salao, usuario: Usuario, request=None, motivo: str = "") -> None:
    from app.services import cobranca  # evita import circular

    agora = _agora()
    if salao.assinatura and salao.assinatura.status.value != "CANCELADO":
        cobranca.cancelar(db, salao.assinatura, "Conta encerrada pelo contratante", usuario=usuario, request=request)
    salao.ativo = False
    salao.encerrado_em = agora
    salao.exclusao_prevista_em = agora + timedelta(days=settings.PRAZO_EXCLUSAO_CONTA_DIAS)
    db.commit()

    registrar_evento(db, EventoSeguranca.CONTA_ENCERRADA, request, usuario_id=usuario.id, salao_id=salao.id,
                     descricao=("Motivo: " + motivo[:300]) if motivo else "Encerrada pelo dono")
    email_sistema(salao.email_principal, f"Conta encerrada — {settings.APP_NAME}", "Sua conta foi encerrada",
                  [f"A conta do {salao.nome} foi encerrada e a página de agendamento saiu do ar.",
                   f"Os dados ficam guardados até {salao.exclusao_prevista_em:%d/%m/%Y} caso você mude de ideia "
                   "— basta responder este e-mail. Depois disso, os dados pessoais de clientes e equipe são apagados "
                   "definitivamente (ficam só os valores financeiros, sem identificação, pelo prazo exigido em lei).",
                   "Antes disso, você ainda pode entrar no painel e baixar uma cópia de todos os dados."],
                  tipo="CONTA_ENCERRADA")
    notificar_admin(db, "conta", "Conta encerrada", f"{salao.nome}" + (f" — {motivo[:120]}" if motivo else ""),
                    link=f"/admin/saloes/{salao.id}", salao_id=salao.id)


def reabrir_conta(db: Session, salao: Salao, admin, request=None) -> None:
    """Admin desfaz o encerramento (antes da anonimização). A assinatura volta a aguardar pagamento."""
    from app.models.assinatura import StatusAssinatura
    salao.encerrado_em = None
    salao.exclusao_prevista_em = None
    if salao.assinatura:
        salao.assinatura.status = StatusAssinatura.AGUARDANDO_PAGAMENTO
        salao.assinatura.cancelada_em = None
    db.commit()
    registrar_evento(db, EventoSeguranca.SALAO_ALTERADO, request, usuario_id=admin.id, salao_id=salao.id,
                     descricao="Encerramento desfeito pelo admin")


def _anonimizar_cliente(c: Cliente) -> None:
    c.nome = "Cliente anônimo"
    c.telefone = f"{PREFIXO_ANONIMO}{c.id}"
    c.email = None
    c.observacoes = None
    c.ativo = False


def anonimizar_salao(db: Session, salao: Salao) -> None:
    sid = salao.id
    for c in db.query(Cliente).filter(Cliente.salao_id == sid):
        _anonimizar_cliente(c)
    db.query(Agendamento).filter(Agendamento.salao_id == sid).update(
        {Agendamento.observacoes: None, Agendamento.motivo_cancelamento: None}, synchronize_session=False)
    db.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.salao_id == sid).update(
        {AvaliacaoAtendimento.comentario: None}, synchronize_session=False)
    db.query(ListaEspera).filter(ListaEspera.salao_id == sid).delete(synchronize_session=False)
    db.query(ConviteEquipe).filter(ConviteEquipe.salao_id == sid).delete(synchronize_session=False)
    db.query(Notificacao).filter(Notificacao.salao_id == sid).delete(synchronize_session=False)
    db.query(NotificacaoPainel).filter(NotificacaoPainel.salao_id == sid).delete(synchronize_session=False)

    for u in db.query(Usuario).filter(Usuario.salao_id == sid):
        uploads.apagar(u.foto)
        u.nome = "Usuário removido"
        u.email = f"removido-{u.id}@anonimo.invalid"
        u.senha_hash = hash_senha(secrets.token_urlsafe(32))
        u.ativo = False
        u.foto = None
        u.telefone = None
        u.especialidade = None
        u.mfa_ativo = False
        u.mfa_secret = None
        u.calendario_token = None
        u.token_recuperacao = None

    for f in db.query(FotoSalao).filter(FotoSalao.salao_id == sid):
        uploads.apagar(f.caminho)
        db.delete(f)
    uploads.apagar(salao.logo)

    salao.nome = f"Salão removido #{sid}"
    salao.slug = f"removido-{sid}"
    salao.email_principal = f"removido-{sid}@anonimo.invalid"
    for campo in ("email_secundario", "telefone", "whatsapp", "instagram", "endereco", "cep", "descricao",
                  "sobre", "logo", "documento", "link_avaliacao_google"):
        setattr(salao, campo, None)
    salao.ativo = False
    salao.anonimizado_em = _agora()
    db.commit()
    registrar_evento(db, EventoSeguranca.DADOS_ANONIMIZADOS, None, salao_id=sid,
                     descricao="Dados pessoais do salão anonimizados após o prazo de encerramento")


# ---------------------------------------------------------------------------
# Retenção automática
# ---------------------------------------------------------------------------
def tarefa_retencao(db: Session) -> int:
    from app.services.envios import primeira_vez

    agora = _agora()
    hoje = date.today()
    if not primeira_vez(db, f"retencao:{hoje.isoformat()}"):
        return 0  # já rodou hoje
    total = 0

    def apagar_antigos(model, coluna, dias, *filtros):
        return db.query(model).filter(coluna < agora - timedelta(days=dias), *filtros).delete(synchronize_session=False)

    total += apagar_antigos(LogSeguranca, LogSeguranca.criado_em, settings.RETENCAO_LOGS_DIAS)
    total += apagar_antigos(Notificacao, Notificacao.criado_em, settings.RETENCAO_LOGS_DIAS)
    total += apagar_antigos(NotificacaoPainel, NotificacaoPainel.criado_em, 90)
    total += apagar_antigos(EnvioAutomatico, EnvioAutomatico.criado_em, 120)
    total += apagar_antigos(SolicitacaoSenha, SolicitacaoSenha.criado_em, 180, SolicitacaoSenha.status != "PENDENTE")
    total += apagar_antigos(ConviteEquipe, ConviteEquipe.expira_em, 90)
    total += (db.query(ListaEspera).filter(ListaEspera.data < hoje - timedelta(days=30))
              .delete(synchronize_session=False))
    db.commit()

    # Clientes sem nenhum atendimento recente (nem futuro) e sem pacote válido → anonimizados
    limite = hoje - timedelta(days=30 * settings.RETENCAO_CLIENTE_INATIVO_MESES)
    tem_atendimento_recente = exists().where(Agendamento.cliente_id == Cliente.id, Agendamento.data >= limite)
    tem_pacote_valido = exists().where(PacoteCliente.cliente_id == Cliente.id, PacoteCliente.validade >= hoje)
    inativos = (db.query(Cliente)
                .filter(~Cliente.telefone.startswith(PREFIXO_ANONIMO),
                        Cliente.criado_em < datetime.combine(limite, datetime.min.time(), tzinfo=timezone.utc),
                        ~tem_atendimento_recente, ~tem_pacote_valido)
                .limit(500).all())
    for c in inativos:
        _anonimizar_cliente(c)
    if inativos:
        db.query(Agendamento).filter(Agendamento.cliente_id.in_([c.id for c in inativos])).update(
            {Agendamento.observacoes: None}, synchronize_session=False)
        db.commit()
        total += len(inativos)

    # Salões encerrados cujo prazo acabou
    vencidos = (db.query(Salao)
                .filter(Salao.exclusao_prevista_em.isnot(None), Salao.exclusao_prevista_em <= agora,
                        Salao.anonimizado_em.is_(None))
                .all())
    for salao in vencidos:
        anonimizar_salao(db, salao)
        total += 1
    return total
