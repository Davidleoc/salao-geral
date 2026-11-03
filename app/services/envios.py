"""
Controle de "já foi feito" para tarefas automáticas (e-mails diários, lembretes…).

    if primeira_vez(db, f"lembrete:{agendamento.id}"):
        enviar_lembrete(...)

Funciona mesmo com mais de um servidor rodando: a chave é única no banco,
então só um deles consegue registrar.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.envio_automatico import EnvioAutomatico


def primeira_vez(db: Session, chave: str) -> bool:
    """Registra a chave e retorna True; se ela já existia, retorna False."""
    if db.query(EnvioAutomatico.id).filter(EnvioAutomatico.chave == chave).first():
        return False
    try:
        with db.begin_nested():
            db.add(EnvioAutomatico(chave=chave[:200]))
        return True
    except IntegrityError:
        return False
