"""
Rotas de autenticação e conta:

  GET/POST /minhaagenda/login              → entrar (limite por IP + bloqueio por conta)
  GET/POST /minhaagenda/login/mfa          → código do segundo fator (se MFA_ENABLED)
  POST     /minhaagenda/logout             → sair
  GET/POST /minhaagenda/recuperar-senha    → pedido de nova senha (vai para o admin)
  GET/POST /minhaagenda/nova-senha         → criar nova senha pelo link recebido (uso único)
  GET      /verificar-email                → confirmação do e-mail (ativa o teste grátis)
  GET/POST /reenviar-verificacao           → reenviar o link de confirmação
  GET/POST /minhaagenda/mfa                → configurar o segundo fator (com MFA_ENABLED)

Proteção: 5 senhas erradas bloqueiam a conta por 15 min; 10 tentativas por IP a cada 5 min.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.log_seguranca import EventoSeguranca
from app.models.usuario import RoleUsuario, Usuario
from app.security import (
    cifrar, criar_token_acesso, gerar_mfa_secret, gerar_mfa_uri, decifrar, hash_senha,
    ler_token_recuperacao, ler_token_verificacao, senha_precisa_rehash, verificar_codigo_mfa,
    verificar_senha, verificar_token, versao_senha,
)
from app.services import cobranca
from app.services.auditoria import mascarar_email, registrar_evento
from app.services.contas import enviar_email_verificacao, solicitar_nova_senha
from app.services.limite_taxa import verificar_limite
from app.templates_compat import templates
from app.validacao import normalizar_email, senha_forte

router = APIRouter()

MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15
# Hash de uma senha qualquer: e-mail inexistente leva o mesmo tempo que senha errada
_HASH_FALSO = hash_senha("senha-ficticia-so-para-igualar-o-tempo")


def _ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _erro_login(msg: str) -> RedirectResponse:
    return _ir("/minhaagenda/login?erro=" + quote(msg))


def _criar_sessao(usuario: Usuario, destino: str) -> RedirectResponse:
    token = criar_token_acesso(usuario.id, usuario.salao_id, usuario.role.value, usuario.senha_hash)
    resp = _ir(destino)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                    max_age=settings.SESSION_EXPIRE_MINUTES * 60)
    return resp


def _destino(usuario: Usuario) -> str:
    if usuario.role == RoleUsuario.ADMIN:
        if settings.MFA_ENABLED and settings.MFA_ADMIN_OBRIGATORIO and not usuario.mfa_ativo:
            return "/minhaagenda/mfa?obrigatorio=1"
        return "/admin"
    return "/minhaagenda/dashboard"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/login", response_class=HTMLResponse)
def pagina_login(request: Request, erro: str = "", nao_verificado: str = ""):
    return templates.TemplateResponse(request, "auth/login.html", {"erro": erro, "nao_verificado": nao_verificado})


@router.post("/minhaagenda/login")
def processar_login(request: Request, email: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    verificar_limite(request, "login")
    agora = datetime.now(timezone.utc)
    email_norm = (email or "").lower().strip()
    usuario = db.query(Usuario).filter(Usuario.email == email_norm, Usuario.ativo == True).first()  # noqa: E712

    if not usuario:
        verificar_senha(senha, _HASH_FALSO)
        registrar_evento(db, EventoSeguranca.LOGIN_FALHOU, request, descricao=f"email: {mascarar_email(email)}")
        return _erro_login("Credenciais inválidas")

    bloqueado_ate = usuario.bloqueado_ate
    if bloqueado_ate and bloqueado_ate.tzinfo is None:
        bloqueado_ate = bloqueado_ate.replace(tzinfo=timezone.utc)
    if bloqueado_ate and bloqueado_ate > agora:
        minutos = int((bloqueado_ate - agora).total_seconds() / 60) + 1
        return _erro_login(f"Conta bloqueada por {minutos} minuto(s)")

    if not verificar_senha(senha, usuario.senha_hash):
        usuario.tentativas_login = (usuario.tentativas_login or 0) + 1
        bloqueou = usuario.tentativas_login >= MAX_TENTATIVAS
        if bloqueou:
            usuario.bloqueado_ate = agora + timedelta(minutes=BLOQUEIO_MINUTOS)
            usuario.tentativas_login = 0
        db.commit()
        registrar_evento(db, EventoSeguranca.LOGIN_FALHOU, request, usuario_id=usuario.id, salao_id=usuario.salao_id,
                         descricao="Conta bloqueada por excesso de tentativas" if bloqueou else None)
        return _erro_login(f"Conta bloqueada por {BLOQUEIO_MINUTOS} minutos" if bloqueou else "Credenciais inválidas")

    if not usuario.email_verificado:
        return _ir("/minhaagenda/login?nao_verificado=1&erro=" + quote("Confirme seu e-mail antes de entrar. Enviamos um link quando você se cadastrou."))

    usuario.tentativas_login = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_login = agora
    if senha_precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = hash_senha(senha)
    db.commit()

    if settings.MFA_ENABLED and usuario.mfa_ativo:
        token_temp = criar_token_acesso(usuario.id, usuario.salao_id, "MFA_PENDENTE", usuario.senha_hash)
        resp = _ir("/minhaagenda/login/mfa")
        resp.set_cookie("mfa_token", token_temp, httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=300)
        return resp

    registrar_evento(db, EventoSeguranca.LOGIN, request, usuario_id=usuario.id, salao_id=usuario.salao_id)
    return _criar_sessao(usuario, _destino(usuario))


@router.get("/minhaagenda/login/mfa", response_class=HTMLResponse)
def pagina_mfa(request: Request, erro: str = ""):
    if not request.cookies.get("mfa_token"):
        return _ir("/minhaagenda/login")
    return templates.TemplateResponse(request, "auth/mfa.html", {"erro": erro})


@router.post("/minhaagenda/login/mfa")
def verificar_mfa(request: Request, codigo: str = Form(...), db: Session = Depends(get_db)):
    verificar_limite(request, "login")
    payload = verificar_token(request.cookies.get("mfa_token", ""))
    if not payload or payload.get("role") != "MFA_PENDENTE":
        return _ir("/minhaagenda/login")
    usuario = db.query(Usuario).filter(Usuario.id == int(payload.get("sub", 0)), Usuario.ativo == True).first()  # noqa: E712
    if not usuario or not usuario.mfa_secret or payload.get("pv") != versao_senha(usuario.senha_hash):
        return _ir("/minhaagenda/login")
    if not verificar_codigo_mfa(usuario.mfa_secret, codigo):
        registrar_evento(db, EventoSeguranca.MFA_FALHOU, request, usuario_id=usuario.id, salao_id=usuario.salao_id)
        return _ir("/minhaagenda/login/mfa?erro=" + quote("Código inválido"))
    registrar_evento(db, EventoSeguranca.LOGIN, request, usuario_id=usuario.id, salao_id=usuario.salao_id, descricao="Login com MFA")
    resp = _criar_sessao(usuario, _destino(usuario))
    resp.delete_cookie("mfa_token")
    return resp


@router.post("/minhaagenda/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    payload = verificar_token(request.cookies.get("access_token", ""))
    if payload:
        registrar_evento(db, EventoSeguranca.SESSAO_INVALIDA, request, usuario_id=int(payload.get("sub", 0)),
                         salao_id=payload.get("salao_id"), descricao="Logout")
    resp = _ir("/minhaagenda/login")
    resp.delete_cookie("access_token")
    return resp


# ---------------------------------------------------------------------------
# Esqueci a senha → pedido para o administrador
# ---------------------------------------------------------------------------
MSG_PEDIDO = ("Pedido recebido. Se o e-mail estiver cadastrado, nossa equipe vai conferir e enviar "
              "um link para criar a nova senha no seu e-mail.")


@router.get("/minhaagenda/recuperar-senha", response_class=HTMLResponse)
def pagina_recuperar_senha(request: Request, mensagem: str = "", erro: str = ""):
    return templates.TemplateResponse(request, "auth/recuperar_senha.html", {"mensagem": mensagem, "erro": erro})


@router.post("/minhaagenda/recuperar-senha")
def processar_recuperar_senha(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    verificar_limite(request, "recuperar_senha")
    email_norm = normalizar_email(email)
    usuario = db.query(Usuario).filter(Usuario.email == email_norm, Usuario.ativo == True).first() if email_norm else None  # noqa: E712
    if usuario:
        solicitar_nova_senha(db, usuario, request)
    return _ir("/minhaagenda/recuperar-senha?mensagem=" + quote(MSG_PEDIDO))


def _usuario_do_link(db: Session, token: str):
    dados = ler_token_recuperacao(token) if token else None
    if not dados:
        return None
    usuario = db.query(Usuario).filter(Usuario.id == dados["u"], Usuario.ativo == True).first()  # noqa: E712
    if not usuario or dados.get("pv") != versao_senha(usuario.senha_hash):
        return None  # senha já foi trocada com este link (uso único)
    return usuario


@router.get("/minhaagenda/nova-senha", response_class=HTMLResponse)
def pagina_nova_senha(request: Request, token: str = "", erro: str = "", db: Session = Depends(get_db)):
    if not _usuario_do_link(db, token):
        return _ir("/minhaagenda/recuperar-senha?erro=" + quote("Link inválido, expirado ou já usado. Peça um novo."))
    return templates.TemplateResponse(request, "auth/nova_senha.html", {"token": token, "erro": erro})


@router.post("/minhaagenda/nova-senha")
def processar_nova_senha(request: Request, token: str = Form(...), nova_senha: str = Form(...),
                         confirmar_senha: str = Form(...), db: Session = Depends(get_db)):
    usuario = _usuario_do_link(db, token)
    if not usuario:
        return _ir("/minhaagenda/recuperar-senha?erro=" + quote("Link inválido, expirado ou já usado. Peça um novo."))
    if nova_senha != confirmar_senha:
        return _ir(f"/minhaagenda/nova-senha?token={quote(token)}&erro=" + quote("As senhas não coincidem."))
    if not senha_forte(nova_senha):
        return _ir(f"/minhaagenda/nova-senha?token={quote(token)}&erro=" + quote("Use no mínimo 8 caracteres, com letras e números."))

    usuario.senha_hash = hash_senha(nova_senha)   # invalida o link e todas as sessões abertas
    usuario.tentativas_login = 0
    usuario.bloqueado_ate = None
    usuario.email_verificado = True                # recebeu o link no e-mail: o e-mail é dele
    db.commit()
    registrar_evento(db, EventoSeguranca.SENHA_ALTERADA, request, usuario_id=usuario.id, salao_id=usuario.salao_id,
                     descricao="Senha criada pelo link de redefinição")
    return _ir("/minhaagenda/login?mensagem=" + quote("Senha alterada. Entre com a nova senha."))


# ---------------------------------------------------------------------------
# Confirmação de e-mail
# ---------------------------------------------------------------------------
@router.get("/verificar-email", response_class=HTMLResponse)
def verificar_email(request: Request, token: str = "", db: Session = Depends(get_db)):
    dados = ler_token_verificacao(token) if token else None
    usuario = db.query(Usuario).filter(Usuario.id == dados["u"]).first() if dados else None
    if not usuario or usuario.email != dados.get("e"):
        return templates.TemplateResponse(request, "auth/verificacao.html", {
            "ok": False, "mensagem": "Este link é inválido ou expirou. Peça um novo abaixo."})
    if not usuario.email_verificado:
        usuario.email_verificado = True
        db.commit()
        registrar_evento(db, EventoSeguranca.EMAIL_VERIFICADO, request, usuario_id=usuario.id, salao_id=usuario.salao_id)
        if usuario.role == RoleUsuario.DONO and usuario.salao:
            cobranca.iniciar_teste(db, usuario.salao, request)
    salao = usuario.salao
    texto = "E-mail confirmado! Você já pode entrar."
    if salao and not salao.ativo:
        texto = "E-mail confirmado! Sua conta será liberada assim que o pagamento da assinatura for confirmado."
    return templates.TemplateResponse(request, "auth/verificacao.html", {"ok": True, "mensagem": texto})


@router.get("/reenviar-verificacao", response_class=HTMLResponse)
def pagina_reenviar(request: Request, mensagem: str = ""):
    return templates.TemplateResponse(request, "auth/verificacao.html", {"ok": None, "mensagem": mensagem})


@router.post("/reenviar-verificacao")
def reenviar_verificacao(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    verificar_limite(request, "verificacao_email")
    email_norm = normalizar_email(email)
    usuario = db.query(Usuario).filter(Usuario.email == email_norm).first() if email_norm else None
    if usuario and not usuario.email_verificado:
        enviar_email_verificacao(usuario)
    return _ir("/reenviar-verificacao?mensagem=" + quote("Se o e-mail estiver cadastrado e ainda não confirmado, enviamos um novo link."))


# ---------------------------------------------------------------------------
# Configurar o segundo fator (MFA) — só funciona com MFA_ENABLED=true
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/mfa", response_class=HTMLResponse)
def pagina_configurar_mfa(request: Request, obrigatorio: str = "", erro: str = "", mensagem: str = "",
                          db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    segredo, uri = None, None
    if settings.MFA_ENABLED and not usuario.mfa_ativo:
        if not usuario.mfa_secret:
            usuario.mfa_secret = cifrar(gerar_mfa_secret())
            db.commit()
        segredo = decifrar(usuario.mfa_secret)
        uri = gerar_mfa_uri(segredo, usuario.email)
    return templates.TemplateResponse(request, "auth/mfa_configurar.html", {
        "usuario": usuario, "habilitado": settings.MFA_ENABLED, "segredo": segredo, "uri": uri,
        "obrigatorio": bool(obrigatorio), "erro": erro, "mensagem": mensagem,
    })


@router.post("/minhaagenda/mfa")
def ativar_mfa(request: Request, codigo: str = Form(...), db: Session = Depends(get_db),
               usuario: Usuario = Depends(obter_usuario_atual)):
    if not settings.MFA_ENABLED:
        return _ir("/minhaagenda/mfa")
    if not usuario.mfa_secret or not verificar_codigo_mfa(usuario.mfa_secret, codigo):
        return _ir("/minhaagenda/mfa?erro=" + quote("Código inválido. Confira o horário do celular e tente de novo."))
    usuario.mfa_ativo = True
    db.commit()
    registrar_evento(db, EventoSeguranca.MFA_ATIVADO, request, usuario_id=usuario.id, salao_id=usuario.salao_id)
    return _ir(_destino(usuario))


@router.post("/minhaagenda/mfa/desativar")
def desativar_mfa(request: Request, senha: str = Form(...), db: Session = Depends(get_db),
                  usuario: Usuario = Depends(obter_usuario_atual)):
    if not verificar_senha(senha, usuario.senha_hash):
        return _ir("/minhaagenda/mfa?erro=" + quote("Senha incorreta."))
    if usuario.role == RoleUsuario.ADMIN and settings.MFA_ENABLED and settings.MFA_ADMIN_OBRIGATORIO:
        return _ir("/minhaagenda/mfa?erro=" + quote("O segundo fator é obrigatório para administradores."))
    usuario.mfa_ativo = False
    usuario.mfa_secret = None
    db.commit()
    registrar_evento(db, EventoSeguranca.MFA_DESATIVADO, request, usuario_id=usuario.id, salao_id=usuario.salao_id)
    return _ir("/minhaagenda/mfa?mensagem=" + quote("Segundo fator desativado."))
