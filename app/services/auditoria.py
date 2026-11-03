"""
Auditoria — registro de eventos de segurança (tabela logs_seguranca).

Use sempre `registrar_evento` para gravar logins, alterações de configuração,
cancelamentos etc. Assim todos os registros ficam no mesmo formato
(IP, navegador, data) e é fácil consultá-los no futuro.

LGPD: nunca grave senhas, tokens ou dados desnecessários na descrição.
Para e-mails digitados por terceiros, use `mascarar_email`.
"""

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.log_seguranca import LogSeguranca, EventoSeguranca


def registrar_evento(
    db: Session,
    evento: EventoSeguranca,
    request: Optional[Request] = None,
    usuario_id: Optional[int] = None,
    salao_id: Optional[int] = None,
    descricao: Optional[str] = None,
    commit: bool = True,
) -> LogSeguranca:
    """Grava um evento de auditoria. Por padrão já faz o commit."""
    log = LogSeguranca(
        usuario_id=usuario_id,
        salao_id=salao_id,
        evento=evento,
        descricao=(descricao or None) and descricao[:1000],
        ip=request.client.host if request is not None and request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:500] if request is not None else None,
    )
    db.add(log)
    if commit:
        db.commit()
    return log


def mascarar_email(email: str) -> str:
    """'maria.silva@gmail.com' -> 'ma***@gmail.com' (o suficiente para investigar, sem expor o dado)."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return "***"
    usuario, dominio = email.split("@", 1)
    return f"{usuario[:2]}***@{dominio[:60]}"
