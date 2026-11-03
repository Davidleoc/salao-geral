"""
Rotas do Painel Administrativo do SaaS (Visão Global).

Acesso restrito ao dono do SaaS (RoleUsuario.ADMIN). NÃO é multi-tenant.
Toda ação que muda algo fica na auditoria (registrar_evento) — ver /admin/auditoria.
Abrir os detalhes de um salão registra ACESSO_SUPORTE (o salão vê isso em "Assinatura e dados").

Outras telas do admin: admin_financeiro.py (/admin/financeiro) e admin_seguranca.py (/admin/senhas, /admin/auditoria).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.deps import exigir_admin
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.assinatura import Assinatura, Periodicidade, StatusAssinatura
from app.models.cliente import Cliente
from app.models.log_seguranca import EventoSeguranca
from app.models.pagamento_assinatura import PagamentoAssinatura
from app.models.plano import Plano
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.solicitacao_senha import SolicitacaoSenha
from app.models.usuario import Usuario
from app.services import cobranca, lgpd
from app.services import equipe as svc_equipe
from app.services.auditoria import registrar_evento
from app.services.email_service import email_sistema
from app.services.envios import primeira_vez
from app.services.financeiro import mrr
from app.templates_compat import templates
from app.validacao import formatar_documento

router = APIRouter(prefix="/admin")

# Ordem das abas de assinatura (o rótulo vem do filtro status_assinatura no template)
FILTROS_ASSINATURA = ["TESTE", "AGUARDANDO_PAGAMENTO", "ATIVO", "EM_ATRASO", "SUSPENSO", "CANCELADO"]


def _ir(url: str, **params) -> RedirectResponse:
    if params:
        url += ("&" if "?" in url else "?") + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _voltar(voltar: str, padrao: str) -> str:
    return voltar if voltar.startswith("/admin") else padrao


def _ctx(request, usuario, pagina, **extra):
    return {"request": request, "usuario": usuario, "active_page": pagina,
            "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""), **extra}


def _salao(db: Session, salao_id: int) -> Salao:
    salao = db.get(Salao, salao_id)
    if not salao:
        raise HTTPException(status_code=404, detail="Salão não encontrado.")
    return salao


def _assinatura(db: Session, assinatura_id: int) -> Assinatura:
    a = db.get(Assinatura, assinatura_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
    return a


# ===========================================================================
# 1. Dashboard
# ===========================================================================
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    contar = lambda *st: db.query(Assinatura).filter(Assinatura.status.in_(st)).count()  # noqa: E731
    return templates.TemplateResponse("admin/dashboard.html", _ctx(
        request, usuario, "dashboard",
        total_saloes_ativos=db.query(Salao).filter(Salao.ativo == True).count(),  # noqa: E712
        total_saloes=db.query(Salao).count(),
        total_assinaturas=db.query(Assinatura).count(),
        assinaturas_ativas=contar(StatusAssinatura.ATIVO, StatusAssinatura.PAGO),
        aguardando_pagamento=contar(StatusAssinatura.AGUARDANDO_PAGAMENTO),
        em_teste=contar(StatusAssinatura.TESTE),
        em_atraso=contar(StatusAssinatura.EM_ATRASO),
        pedidos_senha=db.query(SolicitacaoSenha).filter(SolicitacaoSenha.status == "PENDENTE").count(),
        mrr=float(mrr(db)),
        recentes_assinaturas=db.query(Assinatura).order_by(Assinatura.criado_em.desc()).limit(8).all(),
        recentes_saloes=db.query(Salao).order_by(Salao.criado_em.desc()).limit(6).all(),
    ))


# ===========================================================================
# 2. Salões
# ===========================================================================
@router.get("/saloes", response_class=HTMLResponse)
def listar_saloes(request: Request, busca: Optional[str] = None, status_filtro: Optional[str] = None,
                  db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    query = db.query(Salao).options(joinedload(Salao.assinatura))
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        digitos = "".join(c for c in busca if c.isdigit())
        condicoes = [Salao.nome.ilike(termo), Salao.slug.ilike(termo), Salao.email_principal.ilike(termo)]
        if len(digitos) >= 5:
            condicoes.append(Salao.documento.like(f"%{digitos}%"))
        query = query.filter(or_(*condicoes))
    if status_filtro == "ativo":
        query = query.filter(Salao.ativo == True)  # noqa: E712
    elif status_filtro == "inativo":
        query = query.filter(Salao.ativo == False)  # noqa: E712
    elif status_filtro == "teste":
        query = query.join(Assinatura).filter(Assinatura.status == StatusAssinatura.TESTE)
    return templates.TemplateResponse("admin/saloes.html", _ctx(
        request, usuario, "saloes", saloes=query.order_by(Salao.criado_em.desc()).all(),
        busca=busca or "", status_filtro=status_filtro or ""))


@router.get("/saloes/{salao_id}", response_class=HTMLResponse)
def detalhe_salao(salao_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    salao = _salao(db, salao_id)
    # Transparência: o salão vê quando o suporte abriu seus dados (no máximo 1 registro por hora)
    if primeira_vez(db, f"suporte:{usuario.id}:{salao.id}:{datetime.now():%Y%m%d%H}"):
        registrar_evento(db, EventoSeguranca.ACESSO_SUPORTE, request, usuario_id=usuario.id, salao_id=salao.id,
                         descricao="Suporte consultou os dados da conta")

    assinatura = salao.assinatura
    usuarios = db.query(Usuario).filter(Usuario.salao_id == salao_id).order_by(Usuario.criado_em.asc()).all()
    faturamento = (db.query(func.sum(Agendamento.valor))
                   .filter(Agendamento.salao_id == salao_id, Agendamento.status == StatusAgendamento.CONCLUIDO,
                           Agendamento.pacote_cliente_id.is_(None)).scalar() or Decimal("0"))
    mesmo_documento = (db.query(Salao).filter(Salao.documento == salao.documento, Salao.id != salao.id).all()
                       if salao.documento else [])
    info_vagas = svc_equipe.vagas(db, salao.id)
    return templates.TemplateResponse("admin/salao_detalhe.html", _ctx(
        request, usuario, "saloes", salao=salao, assinatura=assinatura, plano=assinatura.plano if assinatura else None,
        usuarios=usuarios, total_usuarios=len([u for u in usuarios if u.ativo]),
        total_servicos=db.query(Servico).filter(Servico.salao_id == salao_id).count(),
        total_clientes=db.query(Cliente).filter(Cliente.salao_id == salao_id).count(),
        total_agendamentos=db.query(Agendamento).filter(Agendamento.salao_id == salao_id).count(),
        faturamento_total=float(faturamento),
        documento=formatar_documento(salao.tipo_documento, salao.documento), mesmo_documento=mesmo_documento,
        convites=svc_equipe.convites_pendentes(db, salao.id), vagas=info_vagas,
        pagamentos=(db.query(PagamentoAssinatura).filter(PagamentoAssinatura.salao_id == salao.id)
                    .order_by(PagamentoAssinatura.pago_em.desc()).limit(10).all()),
        dias_teste=settings.DIAS_TESTE, url_base=settings.URL_BASE,
    ))


@router.post("/saloes/{salao_id}/ativar")
def ativar_salao(salao_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    """Libera o acesso sem registrar pagamento (cortesia/correção). Para pagamento, use Confirmar pagamento."""
    salao = _salao(db, salao_id)
    a = salao.assinatura
    salao.ativo = True
    if a and a.status in (StatusAssinatura.SUSPENSO, StatusAssinatura.AGUARDANDO_PAGAMENTO, StatusAssinatura.EM_ATRASO):
        a.status = StatusAssinatura.ATIVO
        a.data_inicio = a.data_inicio or date.today()
        if not a.data_fim or a.data_fim < date.today():
            a.data_fim = date.today() + timedelta(days=cobranca.dias_do_ciclo(a))
    db.commit()
    registrar_evento(db, EventoSeguranca.SALAO_ALTERADO, request, usuario_id=usuario.id, salao_id=salao.id,
                     descricao="Salão ativado manualmente (sem pagamento registrado)")
    return _ir(f"/admin/saloes/{salao_id}", mensagem="Salão ativado.")


@router.post("/saloes/{salao_id}/suspender")
def suspender_salao(salao_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    salao = _salao(db, salao_id)
    if salao.assinatura:
        cobranca.suspender(db, salao.assinatura, "Acesso suspenso pela administração.", usuario, request)
    else:
        salao.ativo = False
        db.commit()
        registrar_evento(db, EventoSeguranca.SALAO_ALTERADO, request, usuario_id=usuario.id, salao_id=salao.id,
                         descricao="Salão suspenso")
    return _ir(f"/admin/saloes/{salao_id}", mensagem="Salão suspenso e contratante avisado por e-mail.")


@router.post("/saloes/{salao_id}/reabrir")
def reabrir_salao(salao_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    salao = _salao(db, salao_id)
    if salao.anonimizado_em:
        return _ir(f"/admin/saloes/{salao_id}", erro="Os dados já foram anonimizados — não é possível reabrir.")
    lgpd.reabrir_conta(db, salao, usuario, request)
    return _ir(f"/admin/saloes/{salao_id}", mensagem="Encerramento desfeito. A assinatura aguarda pagamento.")


@router.post("/saloes/{salao_id}/convidar")
def convidar_para_salao(salao_id: int, request: Request, email: str = Form(...), papel: str = Form("FUNCIONARIO"),
                        db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    salao = _salao(db, salao_id)
    try:
        svc_equipe.convidar(db, salao, email, papel, usuario, request)
    except svc_equipe.ErroConvite as e:
        return _ir(f"/admin/saloes/{salao_id}#equipe", erro=str(e))
    return _ir(f"/admin/saloes/{salao_id}", mensagem="Convite enviado. O link vale só para esse e-mail e uma única vez.")


# ===========================================================================
# 3. Planos
# ===========================================================================
@router.get("/planos", response_class=HTMLResponse)
def listar_planos(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    contagens = db.query(Assinatura.plano_id, func.count(Assinatura.id)).group_by(Assinatura.plano_id).all()
    return templates.TemplateResponse("admin/planos.html", _ctx(
        request, usuario, "planos", planos=db.query(Plano).order_by(Plano.preco_mensal.asc()).all(),
        count_por_plano=dict(contagens)))


@router.get("/planos/novo", response_class=HTMLResponse)
def novo_plano_form(request: Request, usuario: Usuario = Depends(exigir_admin)):
    return templates.TemplateResponse("admin/plano_form.html", _ctx(request, usuario, "planos", plano=None, is_edit=False))


@router.get("/planos/{plano_id}/editar", response_class=HTMLResponse)
def editar_plano_form(plano_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    plano = db.get(Plano, plano_id)
    if not plano:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    return templates.TemplateResponse("admin/plano_form.html", _ctx(request, usuario, "planos", plano=plano, is_edit=True))


def _aplicar_plano(plano: Plano, dados: dict) -> None:
    max_servicos = dados.pop("max_servicos")
    plano.max_servicos = int(max_servicos) if max_servicos and max_servicos.strip().isdigit() else None
    plano.nome = dados.pop("nome").strip()
    plano.descricao = dados.pop("descricao").strip() or None
    plano.max_fotos = max(0, dados.pop("max_fotos"))
    for campo, valor in dados.items():
        setattr(plano, campo, valor)


def _form_plano(
    nome: str = Form(...), descricao: str = Form(""), preco_mensal: Decimal = Form(...), preco_anual: Decimal = Form(...),
    max_usuarios: int = Form(2), max_servicos: Optional[str] = Form(None), max_emails: int = Form(2),
    historico_meses: int = Form(2), max_fotos: int = Form(0), exportacao: bool = Form(False), lembretes: bool = Form(False),
    personalizacao_avancada: bool = Form(False), relatorios_avancados: bool = Form(False),
    dominio_personalizado: bool = Form(False), permite_gerente: bool = Form(False),
    sincronizacao_agenda: bool = Form(False), ativo: bool = Form(False),
) -> dict:
    return dict(locals())


@router.post("/planos")
def criar_plano(request: Request, dados: dict = Depends(_form_plano), db: Session = Depends(get_db),
                usuario: Usuario = Depends(exigir_admin)):
    plano = Plano()
    _aplicar_plano(plano, dados)
    db.add(plano)
    db.commit()
    registrar_evento(db, EventoSeguranca.PLANO_ALTERADO, request, usuario_id=usuario.id, descricao=f"Plano criado: {plano.nome}")
    return _ir("/admin/planos", mensagem="Plano criado com sucesso!")


@router.post("/planos/{plano_id}")
def atualizar_plano(plano_id: int, request: Request, dados: dict = Depends(_form_plano), db: Session = Depends(get_db),
                    usuario: Usuario = Depends(exigir_admin)):
    plano = db.get(Plano, plano_id)
    if not plano:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    _aplicar_plano(plano, dados)
    db.commit()
    registrar_evento(db, EventoSeguranca.PLANO_ALTERADO, request, usuario_id=usuario.id,
                     descricao=f"Plano alterado: {plano.nome} (R$ {plano.preco_mensal}/mês)")
    return _ir("/admin/planos", mensagem="Plano atualizado com sucesso!")


# ===========================================================================
# 4. Assinaturas, teste grátis e cobrança (regras em services/cobranca.py)
# ===========================================================================
@router.get("/assinaturas", response_class=HTMLResponse)
def listar_assinaturas(request: Request, status_filtro: Optional[str] = None, db: Session = Depends(get_db),
                       usuario: Usuario = Depends(exigir_admin)):
    contagens = dict(db.query(Assinatura.status, func.count(Assinatura.id)).group_by(Assinatura.status).all())
    query = db.query(Assinatura).options(joinedload(Assinatura.salao), joinedload(Assinatura.plano))
    if status_filtro in FILTROS_ASSINATURA:
        query = query.filter(Assinatura.status == StatusAssinatura(status_filtro))
    return templates.TemplateResponse("admin/assinaturas.html", _ctx(
        request, usuario, "assinaturas", assinaturas=query.order_by(Assinatura.criado_em.desc()).all(),
        status_filtro=status_filtro or "", total_count=sum(contagens.values()),
        contagens={s.value: n for s, n in contagens.items()}, filtros=FILTROS_ASSINATURA,
        dias_teste=settings.DIAS_TESTE, hoje=date.today()))


@router.post("/assinaturas/{assinatura_id}/confirmar-pagamento")
def confirmar_pagamento(assinatura_id: int, request: Request, forma: str = Form("PIX"), voltar: str = Form(""),
                        db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    a = _assinatura(db, assinatura_id)
    pagamento = cobranca.confirmar_pagamento(db, a, usuario, request, forma=forma[:20] or "PIX")
    return _ir(_voltar(voltar, "/admin/assinaturas"),
               mensagem=f"Pagamento confirmado. Assinatura ativa até {pagamento.periodo_fim:%d/%m/%Y}.")


@router.post("/assinaturas/{assinatura_id}/suspender")
def suspender_assinatura(assinatura_id: int, request: Request, voltar: str = Form(""), db: Session = Depends(get_db),
                         usuario: Usuario = Depends(exigir_admin)):
    a = _assinatura(db, assinatura_id)
    cobranca.suspender(db, a, "Assinatura suspensa pela administração.", usuario, request)
    return _ir(_voltar(voltar, "/admin/assinaturas"), mensagem="Assinatura suspensa e contratante avisado.")


@router.post("/assinaturas/{assinatura_id}/cancelar")
def cancelar_assinatura(assinatura_id: int, request: Request, voltar: str = Form(""), db: Session = Depends(get_db),
                        usuario: Usuario = Depends(exigir_admin)):
    a = _assinatura(db, assinatura_id)
    cobranca.cancelar(db, a, "Cancelada pela administração", usuario, request)
    email_sistema(a.salao.email_principal, f"Assinatura cancelada — {settings.APP_NAME}", "Sua assinatura foi cancelada",
                  [f"A assinatura do {a.salao.nome} foi cancelada e a página de agendamento saiu do ar.",
                   "Se isso foi um engano, responda este e-mail."], tipo="ASSINATURA_CANCELADA")
    return _ir(_voltar(voltar, "/admin/assinaturas"), mensagem="Assinatura cancelada e contratante avisado.")


@router.post("/assinaturas/{assinatura_id}/encerrar-teste")
def encerrar_teste(assinatura_id: int, request: Request, voltar: str = Form(""), db: Session = Depends(get_db),
                   usuario: Usuario = Depends(exigir_admin)):
    a = _assinatura(db, assinatura_id)
    if a.status != StatusAssinatura.TESTE:
        return _ir(_voltar(voltar, "/admin/assinaturas"), erro="Esta assinatura não está em teste.")
    cobranca.encerrar_teste(db, a, usuario, request)
    return _ir(_voltar(voltar, "/admin/assinaturas"), mensagem="Teste encerrado. O contratante recebeu o Pix por e-mail.")


@router.post("/assinaturas/{assinatura_id}/renovar-teste")
def renovar_teste(assinatura_id: int, request: Request, dias: int = Form(7), voltar: str = Form(""),
                  db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    a = _assinatura(db, assinatura_id)
    if a.status not in (StatusAssinatura.TESTE, StatusAssinatura.AGUARDANDO_PAGAMENTO):
        return _ir(_voltar(voltar, "/admin/assinaturas"), erro="Só dá para estender teste de quem ainda não pagou.")
    cobranca.renovar_teste(db, a, usuario, request, dias=max(1, min(dias, 60)))
    return _ir(_voltar(voltar, "/admin/assinaturas"), mensagem=f"Teste estendido até {a.data_fim:%d/%m/%Y}. Contratante avisado.")
