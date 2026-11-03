"""
Modelo: EnvioAutomatico

Registro de tarefas automáticas já feitas, para não repetir.
Ex.: "cobranca:aviso:12:2026-10-16" (aviso de vencimento da assinatura 12 enviado hoje)
     "lembrete:340" (lembrete do agendamento 340 enviado)
A chave é única: tentar gravar a mesma chave de novo significa "já foi feito".
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class EnvioAutomatico(Base):
    __tablename__ = "envios_automaticos"

    id = Column(Integer, primary_key=True)
    chave = Column(String(200), nullable=False, unique=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), index=True)
