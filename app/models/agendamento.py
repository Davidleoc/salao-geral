"""
Modelo: Agendamento

Núcleo do sistema — representa um agendamento de um cliente em um salão.
Multi-tenancy: salao_id em todas as queries.

Status do agendamento:
  AGENDADO       → recém criado
  CONFIRMADO     → confirmado pelo salão ou cliente
  CONCLUIDO      → atendimento realizado (conta no faturamento realizado)
  CANCELADO_PELO_CLIENTE
  CANCELADO_PELO_SALAO
  NAO_COMPARECEU → cliente não apareceu

Formas de pagamento:
  PIX, DINHEIRO, CREDITO, DEBITO

Concorrência: a combinação (salao_id, profissional_id, data, hora_inicio)
deve ser única no banco para evitar agendamento duplo.
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time,
    ForeignKey, Numeric, Text, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "AGENDADO"
    CONFIRMADO = "CONFIRMADO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO_PELO_CLIENTE = "CANCELADO_PELO_CLIENTE"
    CANCELADO_PELO_SALAO = "CANCELADO_PELO_SALAO"
    NAO_COMPARECEU = "NAO_COMPARECEU"


class FormaPagamento(str, enum.Enum):
    PIX = "PIX"
    DINHEIRO = "DINHEIRO"
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"


class Agendamento(Base):
    __tablename__ = "agendamentos"

    # Constraint de unicidade para evitar conflito de horário
    __table_args__ = (
        UniqueConstraint(
            "salao_id", "profissional_id", "data", "hora_inicio",
            name="uq_agendamento_profissional_horario"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=False)

    # Profissional (usuário do salão) — nullable: cliente sem preferência
    profissional_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Data e horário
    data = Column(Date, nullable=False, index=True)
    hora_inicio = Column(Time, nullable=False)
    hora_fim = Column(Time, nullable=False)          # calculado: hora_inicio + duracao

    # Valor e pagamento
    valor = Column(Numeric(10, 2), nullable=False)
    custo = Column(Numeric(10, 2), nullable=True)    # custo do serviço no momento do agendamento (histórico)
    comissao_percentual = Column(Numeric(5, 2), nullable=True)  # % do profissional no momento do agendamento

    # Sessão paga com pacote do cliente (não entra de novo no faturamento)
    pacote_cliente_id = Column(Integer, ForeignKey("pacotes_clientes.id"), nullable=True)
    forma_pagamento = Column(SAEnum(FormaPagamento), nullable=True)

    # Status
    status = Column(
        SAEnum(StatusAgendamento),
        nullable=False,
        default=StatusAgendamento.AGENDADO
    )

    # Cancelamento
    cancelado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    cancelado_em = Column(DateTime(timezone=True), nullable=True)
    motivo_cancelamento = Column(Text, nullable=True)  # obrigatório ao cancelar pelo salão

    # Metadata
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="agendamentos")
    cliente = relationship("Cliente", back_populates="agendamentos")
    servico = relationship("Servico", back_populates="agendamentos")
    profissional = relationship(
        "Usuario",
        foreign_keys=[profissional_id]
    )
    cancelado_por_usuario = relationship(
        "Usuario",
        foreign_keys=[cancelado_por_id],
        back_populates="agendamentos_cancelados"
    )
