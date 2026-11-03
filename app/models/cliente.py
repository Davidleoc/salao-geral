"""
Modelo: Cliente

Representa um cliente de um salão.
Multi-tenancy: cada cliente pertence a um salão (salao_id).
  Um mesmo CPF/telefone pode existir em salões diferentes — são registros distintos.

O sistema identifica clientes recorrentes pelo número de agendamentos.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    # Dados do cliente
    nome = Column(String(200), nullable=False)
    telefone = Column(String(20), nullable=False)   # WhatsApp principal
    email = Column(String(255), nullable=True)
    observacoes = Column(Text, nullable=True)

    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="clientes")
    agendamentos = relationship("Agendamento", back_populates="cliente")
