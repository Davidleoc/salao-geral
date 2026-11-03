"""
Dependências de autenticação (FastAPI Depends).

    usuario: Usuario = Depends(obter_usuario_atual)   # qualquer pessoa logada
    admin:   Usuario = Depends(exigir_admin)          # administrador do SaaS
    obter_usuario_opcional(request, db)               # páginas públicas: usuário ou None

Permissões dentro do salão (dono, gerente, funcionário): veja app/permissoes.py
e TenantContext.exigir() em app/tenant.py.

Multi-tenancy: o salao_id vem SEMPRE do usuário autenticado — nunca da URL.
A sessão deixa de valer quando a senha muda (campo "pv" do token).
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.usuario import RoleUsuario, Usuario
from app.security import verificar_token, versao_senha


def _extrair_token(request: Request) -> Optional[str]:
    return request.cookies.get("access_token")


def _ir_para_login():
    return HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/minhaagenda/login"})


def _usuario_do_token(request: Request, db: Session) -> Optional[Usuario]:
    token = _extrair_token(request)
    payload = verificar_token(token) if token else None
    if not payload or payload.get("role") in (None, "MFA_PENDENTE"):
        return None
    try:
        usuario_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        return None
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.ativo == True).first()  # noqa: E712
    if not usuario or payload.get("pv") != versao_senha(usuario.senha_hash):
        return None
    return usuario


def obter_usuario_atual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Exige usuário logado (redireciona para o login se não estiver)."""
    if request.cookies.get("mfa_token") and not request.cookies.get("access_token"):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/minhaagenda/login/mfa"})
    usuario = _usuario_do_token(request, db)
    if not usuario:
        token = _extrair_token(request)
        payload = verificar_token(token) if token else None
        if payload and payload.get("role") == "MFA_PENDENTE":
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/minhaagenda/login/mfa"})
        raise _ir_para_login()
    return usuario


def obter_usuario_opcional(request: Request, db: Session) -> Optional[Usuario]:
    """Para páginas públicas: usuário logado ou None. Nunca redireciona."""
    return _usuario_do_token(request, db)


def exigir_admin(usuario: Usuario = Depends(obter_usuario_atual)) -> Usuario:
    """Administrador do SaaS. Com MFA obrigatório ligado, exige o segundo fator configurado."""
    if usuario.role != RoleUsuario.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    if settings.MFA_ENABLED and settings.MFA_ADMIN_OBRIGATORIO and not usuario.mfa_ativo:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/minhaagenda/mfa?obrigatorio=1"})
    return usuario


def exigir_dono_ou_admin(usuario: Usuario = Depends(obter_usuario_atual)) -> Usuario:
    """Legado: prefira tenant.exigir("permissao") (app/permissoes.py)."""
    if usuario.role not in (RoleUsuario.DONO, RoleUsuario.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return usuario
