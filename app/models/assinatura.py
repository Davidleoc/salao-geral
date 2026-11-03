"""
Modelo: Assinatura

Liga um Salão ao seu Plano.

Fluxo de status:
  AGUARDANDO_PAGAMENTO → PAGO → ATIVO → SUSPENSO / CANCELADO

O SaaS owner confirma o pagamento manualmente pelo /admin
e o sistema ativa o salão.

periodicidade: MENSAL ou ANUAL
"""

import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Numeric, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class StatusAssinatura(str, enum.Enum):
    TESTE = "TESTE"                          # teste grátis (data_fim = fim do teste)
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    PAGO = "PAGO"
    ATIVO = "ATIVO"
    EM_ATRASO = "EM_ATRASO"                  # venceu, ainda dentro da tolerância
    SUSPENSO = "SUSPENSO"
    CANCELADO = "CANCELADO"


class Periodicidade(str, enum.Enum):
    MENSAL = "MENSAL"
    ANUAL = "ANUAL"


class Assinatura(Base):
    __tablename__ = "assinaturas"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, unique=True)
    plano_id = Column(Integer, ForeignKey("planos.id"), nullable=False)

    periodicidade = Column(SAEnum(Periodicidade), nullable=False)
    status = Column(SAEnum(StatusAssinatura), nullable=False, default=StatusAssinatura.AGUARDANDO_PAGAMENTO)

    # Datas
    data_inicio = Column(Date, nullable=True)
    data_fim = Column(Date, nullable=True)            # vencimento da cobrança
    data_pagamento = Column(DateTime(timezone=True), nullable=True)

    # Valor cobrado no momento da contratação (histórico)
    valor_cobrado = Column(Numeric(10, 2), nullable=True)

    cancelada_em = Column(DateTime(timezone=True), nullable=True)

    # Observações administrativas (quem confirmou, etc.)
    observacoes = Column(String(500), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="assinatura")
    plano = relationship("Plano", back_populates="assinaturas")
