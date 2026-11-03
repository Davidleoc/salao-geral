"""
Modelo: Notificacao

Registra os e-mails enviados pelo sistema.

Tipos:
  CONFIRMACAO_AGENDAMENTO    → ao cliente após agendamento
  CANCELAMENTO_AGENDAMENTO   → ao cliente após cancelamento
  LEMBRETE_AGENDAMENTO       → ao cliente antes do horário
  NOVO_AGENDAMENTO_SALAO     → ao salão quando chega novo agendamento
  CANCELAMENTO_SALAO         → ao salão quando cliente cancela
  RECUPERACAO_SENHA          → ao usuário

Permite auditoria de notificações e reenvio em caso de falha.
"""

import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class TipoNotificacao(str, enum.Enum):
    CONFIRMACAO_AGENDAMENTO = "CONFIRMACAO_AGENDAMENTO"
    CANCELAMENTO_AGENDAMENTO = "CANCELAMENTO_AGENDAMENTO"
    LEMBRETE_AGENDAMENTO = "LEMBRETE_AGENDAMENTO"
    NOVO_AGENDAMENTO_SALAO = "NOVO_AGENDAMENTO_SALAO"
    CANCELAMENTO_SALAO = "CANCELAMENTO_SALAO"
    RECUPERACAO_SENHA = "RECUPERACAO_SENHA"


class Notificacao(Base):
    __tablename__ = "notificacoes"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    agendamento_id = Column(Integer, ForeignKey("agendamentos.id"), nullable=True)

    tipo = Column(SAEnum(TipoNotificacao), nullable=False)
    destinatario_email = Column(String(255), nullable=False)
    assunto = Column(String(500), nullable=False)
    corpo = Column(Text, nullable=False)

    enviado = Column(Boolean, default=False)
    enviado_em = Column(DateTime(timezone=True), nullable=True)
    erro = Column(Text, nullable=True)               # mensagem de erro se falhou

    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="notificacoes")
    agendamento = relationship("Agendamento", foreign_keys=[agendamento_id])
