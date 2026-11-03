"""
Modelo: AvaliacaoAtendimento

Avaliação que o CLIENTE FINAL faz do atendimento no salão (não confundir com
Avaliacao, que é o salão avaliando o sistema).

Fluxo: atendimento concluído → convite com link único (só o hash fica no banco)
→ cliente dá nota 1 a 5 e comenta → se a nota for alta e o salão tiver link do
Google, mostramos o convite para avaliar lá também.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AvaliacaoAtendimento(Base):
    __tablename__ = "avaliacoes_atendimento"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    agendamento_id = Column(Integer, ForeignKey("agendamentos.id"), nullable=False, unique=True)
    token_hash = Column(String(64), nullable=False, unique=True)

    nota = Column(Integer, nullable=True)            # 1 a 5
    comentario = Column(Text, nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    respondido_em = Column(DateTime(timezone=True), nullable=True)

    agendamento = relationship("Agendamento")
