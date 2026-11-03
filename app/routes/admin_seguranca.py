"""
Rotas de segurança do admin.

  GET  /admin/senhas                       → pedidos de "esqueci minha senha"
  POST /admin/senhas/{id}/enviar           → envia o link de nova senha para o e-mail da pessoa
  POST /admin/senhas/{id}/descartar        → descarta o pedido (ex: suspeito)
  GET  /admin/auditoria                    → registro de eventos com filtros (inclui as ações do próprio admin)

O admin nunca vê nem escolhe a senha: só dispara o link de uso único (services/contas.py).
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import exigir_admin
from app.models.log_seguranca import EventoSeguranca, LogSeguranca
from app.models.salao import Salao
from app.models.solicitacao_senha import SolicitacaoSenha
from app.models.usuario import Usuario
from app.services.auditoria import registrar_evento
from app.services.contas import enviar_link_redefinicao
from app.templates_compat import templates

router = APIRouter(prefix="/admin")

POR_PAGINA = 50

# Eventos que representam ações do admin (filtro "Só ações do admin")
EVENTOS_ADMIN = [EventoSeguranca.PAGAMENTO_CONFIRMADO, EventoSeguranca.ASSINATURA_ALTERADA, EventoSeguranca.SALAO_ALTERADO,
                 EventoSeguranca.PLANO_ALTERADO, EventoSeguranca.ACESSO_SUPORTE, EventoSeguranca.SENHA_RESET_ENVIADO]


def _ir(url: str, **params) -> RedirectResponse:
    if params:
        url += "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Pedidos de nova senha
# ---------------------------------------------------------------------------
@router.get("/senhas", response_class=HTMLResponse)
def pedidos_senha(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    base = db.query(SolicitacaoSenha).options(joinedload(SolicitacaoSenha.usuario).joinedload(Usuario.salao))
    return templates.TemplateResponse("admin/senhas.html", {
        "request": request, "usuario": usuario, "active_page": "senhas",
        "pendentes": base.filter(SolicitacaoSenha.status == "PENDENTE").order_by(SolicitacaoSenha.criado_em).all(),
        "historico": base.filter(SolicitacaoSenha.status != "PENDENTE").order_by(SolicitacaoSenha.atendido_em.desc()).limit(30).all(),
        "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""),
    })


def _pedido(db: Session, pedido_id: int) -> SolicitacaoSenha:
    pedido = db.get(SolicitacaoSenha, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404)
    return pedido


@router.post("/senhas/{pedido_id}/enviar")
def enviar_link_senha(pedido_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    pedido = _pedido(db, pedido_id)
    pessoa = pedido.usuario
    if not pessoa or not pessoa.ativo:
        return _ir("/admin/senhas", erro="Este usuário não está mais ativo.")
    enviar_link_redefinicao(pessoa, "Você pediu para redefinir sua senha e nossa equipe liberou o acesso.")
    agora = datetime.now(timezone.utc)
    # Atende todos os pedidos pendentes desta pessoa de uma vez
    for p in db.query(SolicitacaoSenha).filter(SolicitacaoSenha.usuario_id == pessoa.id, SolicitacaoSenha.status == "PENDENTE"):
        p.status, p.atendido_em, p.atendido_por_id = "ENVIADO", agora, usuario.id
    db.commit()
    registrar_evento(db, EventoSeguranca.SENHA_RESET_ENVIADO, request, usuario_id=usuario.id, salao_id=pessoa.salao_id,
                     descricao=f"Link de nova senha enviado para {pessoa.nome}")
    return _ir("/admin/senhas", mensagem=f"Link enviado para o e-mail de {pessoa.nome}.")


@router.post("/senhas/{pedido_id}/descartar")
def descartar_pedido(pedido_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    pedido = _pedido(db, pedido_id)
    pedido.status, pedido.atendido_em, pedido.atendido_por_id = "DESCARTADO", datetime.now(timezone.utc), usuario.id
    db.commit()
    registrar_evento(db, EventoSeguranca.SENHA_RESET_ENVIADO, request, usuario_id=usuario.id,
                     salao_id=pedido.usuario.salao_id if pedido.usuario else None,
                     descricao="Pedido de nova senha descartado")
    return _ir("/admin/senhas", mensagem="Pedido descartado.")


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
@router.get("/auditoria", response_class=HTMLResponse)
def auditoria(request: Request, evento: str = "", salao_id: str = "", de: Optional[date] = None, ate: Optional[date] = None,
              so_admin: str = "", pagina: int = 1, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    q = db.query(LogSeguranca)
    if evento in EventoSeguranca.__members__:
        q = q.filter(LogSeguranca.evento == EventoSeguranca(evento))
    if salao_id.isdigit():
        q = q.filter(LogSeguranca.salao_id == int(salao_id))
    if de:
        q = q.filter(LogSeguranca.criado_em >= datetime.combine(de, time.min, tzinfo=timezone.utc))
    if ate:
        q = q.filter(LogSeguranca.criado_em < datetime.combine(ate + timedelta(days=1), time.min, tzinfo=timezone.utc))
    if so_admin:
        admins = [u.id for u in db.query(Usuario.id).filter(Usuario.salao_id.is_(None))]
        q = q.filter(LogSeguranca.usuario_id.in_(admins))

    pagina = max(1, pagina)
    total = q.count()
    logs = q.order_by(LogSeguranca.criado_em.desc(), LogSeguranca.id.desc()).offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()

    ids_usuarios = {l.usuario_id for l in logs if l.usuario_id}
    ids_saloes = {l.salao_id for l in logs if l.salao_id}
    nomes_usuarios = dict(db.query(Usuario.id, Usuario.nome).filter(Usuario.id.in_(ids_usuarios)).all()) if ids_usuarios else {}
    nomes_saloes = dict(db.query(Salao.id, Salao.nome).filter(Salao.id.in_(ids_saloes)).all()) if ids_saloes else {}

    filtros = {k: v for k, v in {"evento": evento, "salao_id": salao_id, "de": de or "", "ate": ate or "", "so_admin": so_admin}.items() if v}
    return templates.TemplateResponse("admin/auditoria.html", {
        "request": request, "usuario": usuario, "active_page": "auditoria",
        "logs": logs, "total": total, "pagina": pagina, "paginas": max(1, -(-total // POR_PAGINA)),
        "nomes_usuarios": nomes_usuarios, "nomes_saloes": nomes_saloes,
        "eventos": [e.value for e in EventoSeguranca], "saloes": db.query(Salao.id, Salao.nome).order_by(Salao.nome).all(),
        "f": {"evento": evento, "salao_id": salao_id, "de": de, "ate": ate, "so_admin": so_admin},
        "query_filtros": urlencode(filtros),
    })
