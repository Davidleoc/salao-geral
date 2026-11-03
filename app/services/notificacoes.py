"""
Notificações na tela (sininho + balão que aparece no canto).

Criar:
    notificar_salao(db, salao_id, "agendamento", "Novo agendamento", "Ana — Corte, 14/10 às 10h",
                    link="/minhaagenda/agenda/12", papeis=["DONO", "GERENTE"], autor_id=usuario.id)
    notificar_admin(db, "senha", "Pedido de nova senha", "maria@...", link="/admin/senhas")

A tela consulta /minhaagenda/api/notificacoes (ou /admin/api/notificacoes) a cada ~20s
— veja static/js/notificacoes.js. Quem causou a ação (autor_id) não recebe o aviso.
"""

from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.notificacao_painel import NotificacaoPainel
from app.models.usuario import RoleUsuario, Usuario


def notificar_salao(db: Session, salao_id: int, tipo: str, titulo: str, mensagem: str = "",
                    link: Optional[str] = None, papeis: Optional[Iterable[str]] = None,
                    usuario_id: Optional[int] = None, autor_id: Optional[int] = None,
                    commit: bool = True) -> NotificacaoPainel:
    n = NotificacaoPainel(
        destino="SALAO", salao_id=salao_id, tipo=tipo, titulo=titulo[:150], mensagem=(mensagem or "")[:500],
        link=link, para_papeis=",".join(papeis) if papeis else None, usuario_id=usuario_id, autor_id=autor_id,
    )
    db.add(n)
    if commit:
        db.commit()
    return n


def notificar_admin(db: Session, tipo: str, titulo: str, mensagem: str = "", link: Optional[str] = None,
                    salao_id: Optional[int] = None, autor_id: Optional[int] = None, commit: bool = True) -> NotificacaoPainel:
    n = NotificacaoPainel(destino="ADMIN", salao_id=salao_id, tipo=tipo, titulo=titulo[:150],
                          mensagem=(mensagem or "")[:500], link=link, autor_id=autor_id)
    db.add(n)
    if commit:
        db.commit()
    return n


def _consulta_do_usuario(db: Session, usuario: Usuario):
    q = db.query(NotificacaoPainel).filter(
        or_(NotificacaoPainel.autor_id.is_(None), NotificacaoPainel.autor_id != usuario.id)
    )
    if usuario.role == RoleUsuario.ADMIN:
        return q.filter(NotificacaoPainel.destino == "ADMIN")
    papel = usuario.role.value
    return q.filter(
        NotificacaoPainel.destino == "SALAO",
        NotificacaoPainel.salao_id == usuario.salao_id,
        or_(NotificacaoPainel.usuario_id.is_(None), NotificacaoPainel.usuario_id == usuario.id),
        or_(NotificacaoPainel.para_papeis.is_(None), NotificacaoPainel.para_papeis.contains(papel)),
    )


def ultimas(db: Session, usuario: Usuario, limite: int = 15):
    return _consulta_do_usuario(db, usuario).order_by(NotificacaoPainel.id.desc()).limit(limite).all()


def novas_desde(db: Session, usuario: Usuario, desde_id: int, limite: int = 5):
    return (_consulta_do_usuario(db, usuario).filter(NotificacaoPainel.id > desde_id)
            .order_by(NotificacaoPainel.id.asc()).limit(limite).all())


def contar_nao_lidas(db: Session, usuario: Usuario) -> int:
    return _consulta_do_usuario(db, usuario).filter(NotificacaoPainel.id > (usuario.ultima_notificacao_vista or 0)).count()


def ultimo_id(db: Session, usuario: Usuario) -> int:
    n = _consulta_do_usuario(db, usuario).order_by(NotificacaoPainel.id.desc()).first()
    return n.id if n else 0


def para_json(n: NotificacaoPainel, lida_ate: int = 0) -> dict:
    return {
        "id": n.id, "tipo": n.tipo, "titulo": n.titulo, "mensagem": n.mensagem or "", "link": n.link or "",
        "quando": n.criado_em.strftime("%d/%m %H:%M") if n.criado_em else "", "lida": n.id <= lida_ate,
    }
