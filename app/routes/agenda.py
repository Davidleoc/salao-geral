"""
Rotas: agenda do salão.

  GET  /minhaagenda/agenda?data=&profissional=   → agenda do dia (funcionário vê só a própria)
  GET  /minhaagenda/agenda/novo                  → agendamento manual (recepção)
  POST /minhaagenda/agenda/novo
  GET  /minhaagenda/agenda/{id}                  → ficha do agendamento
  POST /minhaagenda/agenda/{id}/status           → confirmar, concluir, não compareceu
  POST /minhaagenda/agenda/{id}/cancelar         → cancelar (motivo obrigatório; avisa a lista de espera)
  POST /minhaagenda/agenda/{id}/link-avaliacao   → gera o link de avaliação para mandar por WhatsApp

Permissões (app/permissoes.py): "agenda.todos" (dono, gerente) ou "agenda.propria" (funcionário).
Ao concluir: pode descontar sessão de pacote e convida o cliente a avaliar (services/).
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.agendamento import Agendamento, FormaPagamento, StatusAgendamento
from app.models.cliente import Cliente
from app.models.log_seguranca import EventoSeguranca
from app.models.servico import Servico
from app.models.usuario import Usuario
from app.services import avaliacoes, lista_espera, pacotes
from app.services.auditoria import registrar_evento
from app.services.disponibilidade_service import conflito, profissionais_que_atendem
from app.services.email_service import enviar_cancelamento_agendamento, enviar_confirmacao_agendamento
from app.services.notificacoes import notificar_salao
from app.templates_compat import templates
from app.tenant import obter_tenant
from app.validacao import normalizar_email, normalizar_telefone

logger = logging.getLogger(__name__)
router = APIRouter()

CANCELADOS = [StatusAgendamento.CANCELADO_PELO_CLIENTE, StatusAgendamento.CANCELADO_PELO_SALAO]


def _ir(url: str, mensagem: str = "", erro: str = "") -> RedirectResponse:
    if mensagem:
        url += ("&" if "?" in url else "?") + "mensagem=" + quote(mensagem)
    if erro:
        url += ("&" if "?" in url else "?") + "erro=" + quote(erro)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _tenant_agenda(db, usuario):
    tenant = obter_tenant(db, usuario)
    if not (tenant.pode("agenda.todos") or tenant.pode("agenda.propria")):
        from app.permissoes import SemPermissao
        raise SemPermissao()
    return tenant


def _agendamento_visivel(tenant, agendamento_id: int) -> Agendamento:
    """Funcionário só abre agendamentos dele (os outros dão 404, como se não existissem)."""
    ag = tenant.get_or_404(Agendamento, agendamento_id)
    if not tenant.ve_todos and ag.profissional_id != tenant.usuario.id:
        raise HTTPException(status_code=404, detail="Não encontrado.")
    return ag


# ---------------------------------------------------------------------------
# Agenda do dia
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/agenda", response_class=HTMLResponse)
def visualizacao_agenda(request: Request, data: Optional[date] = None, profissional: str = "",
                        db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    data_alvo = data or date.today()
    q = tenant.query(Agendamento).filter(Agendamento.data == data_alvo, Agendamento.status.notin_(CANCELADOS))
    filtro_prof = None
    if not tenant.ve_todos:
        q = q.filter(Agendamento.profissional_id == usuario.id)
    elif profissional.isdigit():
        filtro_prof = int(profissional)
        q = q.filter(Agendamento.profissional_id == filtro_prof)
    return templates.TemplateResponse(request, "painel/agenda.html", {
        "usuario": usuario, "salao": tenant.salao, "data_alvo": data_alvo,
        "agendamentos": q.order_by(Agendamento.hora_inicio).all(), "active_page": "agenda",
        "profissionais": profissionais_que_atendem(db, tenant.salao_id) if tenant.ve_todos else [],
        "filtro_prof": filtro_prof, "ve_todos": tenant.ve_todos,
        "mensagem": request.query_params.get("mensagem"), "erro": request.query_params.get("erro"),
    })


# ---------------------------------------------------------------------------
# Agendamento manual
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/agenda/novo", response_class=HTMLResponse)
def form_novo_agendamento(request: Request, cliente: Optional[int] = None, db: Session = Depends(get_db),
                          usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    cliente_obj = tenant.query(Cliente).filter(Cliente.id == cliente).first() if cliente else None
    profissionais = profissionais_que_atendem(db, tenant.salao_id) if tenant.ve_todos else [usuario]
    return templates.TemplateResponse(request, "painel/agendamento_form.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "agenda",
        "servicos": tenant.query(Servico).filter(Servico.ativo == True).order_by(Servico.nome).all(),  # noqa: E712
        "profissionais": profissionais, "cliente": cliente_obj, "hoje": date.today().isoformat(),
        "erro": request.query_params.get("erro"),
    })


@router.post("/minhaagenda/agenda/novo")
def criar_agendamento_manual(
    request: Request, servico_id: int = Form(...), data: date = Form(...), hora_inicio: str = Form(...),
    nome_cliente: str = Form(...), telefone_cliente: str = Form(...), email_cliente: Optional[str] = Form(None),
    forma_pagamento: Optional[str] = Form(None), status_inicial: str = Form("CONFIRMADO", alias="status"),
    observacoes: Optional[str] = Form(None), profissional_id: str = Form(""),
    db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = _tenant_agenda(db, usuario)
    servico = tenant.get_or_404(Servico, servico_id)

    def erro(msg):
        return _ir("/minhaagenda/agenda/novo", erro=msg)

    # Quem atende: funcionário sempre ele mesmo; dono/gerente escolhe alguém que atende clientes
    if not tenant.ve_todos:
        profissional = usuario
    elif profissional_id.isdigit():
        profissional = next((p for p in profissionais_que_atendem(db, tenant.salao_id) if p.id == int(profissional_id)), None)
        if not profissional:
            return erro("Profissional inválido.")
    else:
        profissional = None

    try:
        hora_obj = datetime.strptime(hora_inicio.strip(), "%H:%M").time()
        status_enum = StatusAgendamento(status_inicial)
        forma = FormaPagamento(forma_pagamento) if forma_pagamento else None
    except ValueError:
        return erro("Confira o horário, o status e a forma de pagamento.")
    if status_enum not in (StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO):
        return erro("Status inicial inválido.")
    telefone_ok = normalizar_telefone(telefone_cliente)
    if not telefone_ok:
        return erro("Telefone do cliente inválido.")
    email_ok = normalizar_email(email_cliente) if email_cliente and email_cliente.strip() else None
    if email_cliente and email_cliente.strip() and not email_ok:
        return erro("E-mail do cliente inválido.")

    hora_fim = (datetime.combine(data, hora_obj) + timedelta(minutes=servico.duracao_minutos)).time()
    if conflito(db, tenant.salao_id, data, hora_obj, hora_fim, profissional.id if profissional else None):
        quem = profissional.nome if profissional else "o salão"
        return erro(f"Conflito: {quem} já tem um atendimento nesse horário.")

    cliente = tenant.query(Cliente).filter(Cliente.telefone.in_([telefone_ok, telefone_cliente.strip()])).first()
    if not cliente:
        cliente = Cliente(salao_id=tenant.salao_id, nome=" ".join(nome_cliente.split())[:200], telefone=telefone_ok, email=email_ok)
        db.add(cliente)
        db.flush()
    elif email_ok and not cliente.email:
        cliente.email = email_ok

    agendamento = Agendamento(
        salao_id=tenant.salao_id, cliente_id=cliente.id, servico_id=servico.id,
        profissional_id=profissional.id if profissional else None, data=data, hora_inicio=hora_obj, hora_fim=hora_fim,
        valor=servico.preco, custo=servico.custo,
        comissao_percentual=profissional.comissao_percentual if profissional else None,
        forma_pagamento=forma, status=status_enum,
        observacoes=observacoes.strip()[:1000] if observacoes and observacoes.strip() else None,
    )
    db.add(agendamento)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return erro("Conflito: já existe agendamento neste horário.")

    if profissional and profissional.id != usuario.id:
        notificar_salao(db, tenant.salao_id, "agendamento", "Novo cliente na sua agenda",
                        f"{cliente.nome} — {servico.nome}, {data:%d/%m} às {hora_obj:%H:%M}",
                        link=f"/minhaagenda/agenda/{agendamento.id}", usuario_id=profissional.id, autor_id=usuario.id)
    try:
        enviar_confirmacao_agendamento(db, agendamento)
    except Exception:
        logger.exception("Falha ao enviar confirmação do agendamento %s", agendamento.id)
    return _ir(f"/minhaagenda/agenda?data={data}", mensagem="Agendamento criado com sucesso!")


# ---------------------------------------------------------------------------
# Ficha, status e cancelamento
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/agenda/{agendamento_id}", response_class=HTMLResponse)
def detalhes_agendamento(agendamento_id: int, request: Request, db: Session = Depends(get_db),
                         usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    ag = _agendamento_visivel(tenant, agendamento_id)
    from app.models.avaliacao_atendimento import AvaliacaoAtendimento
    return templates.TemplateResponse(request, "painel/agendamento_ficha.html", {
        "usuario": usuario, "salao": tenant.salao, "agendamento": ag, "active_page": "agenda",
        "pacotes_validos": pacotes.validos_para(db, ag) if ag.status != StatusAgendamento.CONCLUIDO else [],
        "avaliacao": db.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.agendamento_id == ag.id).first(),
        "link_avaliacao": request.query_params.get("link_avaliacao"), "url_base": settings.URL_BASE.rstrip("/"),
        "equipe": (tenant.query(Usuario).filter(Usuario.ativo == True).order_by(Usuario.nome).all()  # noqa: E712
                   if tenant.ve_todos else []),
        "mensagem": request.query_params.get("mensagem"), "erro": request.query_params.get("erro"),
    })


@router.post("/minhaagenda/agenda/{agendamento_id}/status")
def atualizar_status(agendamento_id: int, request: Request, novo_status: str = Form(...), usar_pacote: str = Form(""),
                     db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    ag = _agendamento_visivel(tenant, agendamento_id)
    url = f"/minhaagenda/agenda/{agendamento_id}"
    try:
        novo = StatusAgendamento(novo_status)
    except ValueError:
        return _ir(url, erro="Status inválido.")
    if novo in CANCELADOS:
        return _ir(url, erro="Use o botão de cancelamento.")
    if ag.status in CANCELADOS:
        return _ir(url, erro="Agendamento cancelado não pode ser reaberto. Crie um novo.")

    anterior = ag.status
    ag.status = novo
    db.commit()

    if anterior == StatusAgendamento.CONCLUIDO and novo != StatusAgendamento.CONCLUIDO and ag.pacote_cliente_id:
        pacotes.devolver_sessao(db, ag)
    if novo == StatusAgendamento.CONCLUIDO and anterior != StatusAgendamento.CONCLUIDO:
        if usar_pacote.isdigit():
            escolhido = next((p for p in pacotes.validos_para(db, ag) if p.id == int(usar_pacote)), None)
            if escolhido:
                pacotes.usar_sessao(db, ag, escolhido)
        try:
            avaliacoes.convidar_apos_atendimento(db, ag)
        except Exception:
            logger.exception("Falha ao convidar para avaliação (agendamento %s)", ag.id)
    return _ir(url, mensagem="Status atualizado.")


@router.post("/minhaagenda/agenda/{agendamento_id}/profissional")
def definir_profissional(agendamento_id: int, request: Request, profissional_id: str = Form(""),
                         db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    """Quem atendeu (ou vai atender). Opcional: vazio = sem profissional definido. A comissão segue a pessoa escolhida."""
    tenant = _tenant_agenda(db, usuario)
    tenant.exigir("agenda.todos")
    ag = _agendamento_visivel(tenant, agendamento_id)
    url = f"/minhaagenda/agenda/{agendamento_id}"
    if ag.status in CANCELADOS:
        return _ir(url, erro="Agendamento cancelado não pode ser alterado.")
    novo = None
    if profissional_id.isdigit():
        novo = tenant.query(Usuario).filter(Usuario.id == int(profissional_id), Usuario.ativo == True).first()  # noqa: E712
        if not novo:
            return _ir(url, erro="Profissional não encontrado.")
    if (novo and novo.id != ag.profissional_id and ag.status != StatusAgendamento.CONCLUIDO
            and conflito(db, tenant.salao_id, ag.data, ag.hora_inicio, ag.hora_fim, novo.id, ignorar_id=ag.id)):
        return _ir(url, erro=f"{novo.nome} já tem um atendimento nesse horário.")
    ag.profissional_id = novo.id if novo else None
    ag.comissao_percentual = novo.comissao_percentual if novo else None
    db.commit()
    registrar_evento(db, EventoSeguranca.CONFIGURACAO_ALTERADA, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"Agendamento {ag.id}: profissional → {novo.nome if novo else 'sem profissional'}")
    if novo and novo.id != usuario.id:
        notificar_salao(db, tenant.salao_id, "agendamento", "Atendimento atribuído a você",
                        f"{ag.cliente.nome} — {ag.servico.nome}, {ag.data:%d/%m} às {ag.hora_inicio:%H:%M}",
                        link=url, usuario_id=novo.id)
    return _ir(url, mensagem=f"Profissional atualizado: {novo.nome if novo else 'sem profissional definido'}.")


@router.post("/minhaagenda/agenda/{agendamento_id}/cancelar")
def cancelar_agendamento_salao(agendamento_id: int, request: Request, motivo_cancelamento: str = Form(...),
                               db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    ag = _agendamento_visivel(tenant, agendamento_id)
    url = f"/minhaagenda/agenda/{agendamento_id}"
    if not motivo_cancelamento.strip():
        return _ir(url, erro="Motivo de cancelamento é obrigatório.")
    if ag.status in CANCELADOS:
        return _ir(url, erro="Agendamento já cancelado.")

    if ag.pacote_cliente_id:
        pacotes.devolver_sessao(db, ag)
    ag.status = StatusAgendamento.CANCELADO_PELO_SALAO
    ag.motivo_cancelamento = motivo_cancelamento.strip()[:1000]
    ag.cancelado_por_id = usuario.id
    ag.cancelado_em = datetime.now(timezone.utc)
    registrar_evento(db, EventoSeguranca.AGENDAMENTO_CANCELADO, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"Agendamento {agendamento_id} cancelado: {ag.motivo_cancelamento}")

    if ag.profissional_id and ag.profissional_id != usuario.id:
        notificar_salao(db, tenant.salao_id, "cancelamento", "Atendimento cancelado",
                        f"{ag.cliente.nome} — {ag.servico.nome}, {ag.data:%d/%m} às {ag.hora_inicio:%H:%M}",
                        link=url, usuario_id=ag.profissional_id, autor_id=usuario.id)
    try:
        enviar_cancelamento_agendamento(db, ag)
    except Exception:
        logger.exception("Falha ao enviar e-mail de cancelamento %s", ag.id)
    avisado = lista_espera.avisar_proximo(db, ag)
    msg = "Agendamento cancelado e horário liberado."
    if avisado:
        msg += f" {avisado.nome}, da lista de espera, foi avisado."
    return _ir(url, mensagem=msg)


@router.post("/minhaagenda/agenda/{agendamento_id}/link-avaliacao")
def gerar_link_avaliacao(agendamento_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = _tenant_agenda(db, usuario)
    ag = _agendamento_visivel(tenant, agendamento_id)
    url = f"/minhaagenda/agenda/{agendamento_id}"
    if ag.status != StatusAgendamento.CONCLUIDO:
        return _ir(url, erro="O link de avaliação fica disponível depois que o atendimento é concluído.")
    link = avaliacoes.criar_link(db, ag)
    if not link:
        return _ir(url, erro="Este cliente já avaliou o atendimento.")
    return _ir(f"{url}?link_avaliacao={quote(link)}", mensagem="Link gerado. Copie e mande para o cliente.")
