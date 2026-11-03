"""
Modelo: Servico

Representa um serviço oferecido por um salão.
Multi-tenancy: cada serviço pertence a um salão (salao_id).

A duração é em minutos e é usada pelo motor de disponibilidade para
calcular quais horários estão livres.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Servico(Base):
    __tablename__ = "servicos"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    # Dados do serviço
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    preco = Column(Numeric(10, 2), nullable=False)
    duracao_minutos = Column(Integer, nullable=False)  # Ex: 60 = 1 hora
    custo = Column(Numeric(10, 2), nullable=True)      # Custo da empresa para prestar o serviço (opcional)

    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="servicos")
    agendamentos = relationship("Agendamento", back_populates="servico")
