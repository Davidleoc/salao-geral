"""
Modelo: ListaEspera

Cliente que quer um horário num dia lotado. Quando um agendamento desse dia é
cancelado, o primeiro da fila (por ordem de chegada) é avisado.

status: AGUARDANDO → AVISADO → AGENDADO | REMOVIDO | EXPIRADO
"""

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ListaEspera(Base):
    __tablename__ = "lista_espera"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # vazio = qualquer

    data = Column(Date, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    telefone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)

    status = Column(String(12), nullable=False, default="AGUARDANDO", index=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    avisado_em = Column(DateTime(timezone=True), nullable=True)

    servico = relationship("Servico")
    profissional = relationship("Usuario")
