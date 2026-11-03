"""
Modelo: SolicitacaoSenha

Pedido de "esqueci a senha". Gera um alerta para o administrador do SaaS,
que confere o pedido e envia um link de redefinição para o e-mail cadastrado.
O administrador nunca vê nem define a senha da pessoa.

status: PENDENTE → ENVIADO (link enviado) ou DESCARTADO
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class SolicitacaoSenha(Base):
    __tablename__ = "solicitacoes_senha"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    status = Column(String(12), nullable=False, default="PENDENTE", index=True)
    ip = Column(String(45), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atendido_em = Column(DateTime(timezone=True), nullable=True)
    atendido_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    usuario = relationship("Usuario", foreign_keys=[usuario_id])
