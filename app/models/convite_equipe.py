"""
Modelo: ConviteEquipe

Convite para alguém entrar na equipe de um salão.
- O link é enviado só para o e-mail convidado e vale para UM cadastro (usado_em).
- Guardamos apenas o hash do token: quem tiver acesso ao banco não consegue usar o link.
- Expira em alguns dias (expira_em).
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ConviteEquipe(Base):
    __tablename__ = "convites_equipe"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    email = Column(String(255), nullable=False, index=True)
    papel = Column(String(20), nullable=False)               # "GERENTE" ou "FUNCIONARIO"
    token_hash = Column(String(64), nullable=False, unique=True)

    criado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    expira_em = Column(DateTime(timezone=True), nullable=False)
    usado_em = Column(DateTime(timezone=True), nullable=True)
    usuario_criado_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    cancelado_em = Column(DateTime(timezone=True), nullable=True)

    salao = relationship("Salao")
