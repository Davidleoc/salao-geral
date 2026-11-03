"""
Modelo: Avaliacao

Avaliação do sistema feita por um contratante (salão cliente ou ex-cliente).
Exibida na página pública /contratar, ordenada pela nota (maior primeiro).

Regras:
  - Uma avaliação por salão (se avaliar de novo, a anterior é atualizada)
  - nota de 0.5 a 5.0, em passos de 0.5
  - comentário de até 800 caracteres
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Avaliacao(Base):
    __tablename__ = "avaliacoes"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, unique=True)

    nota = Column(Numeric(2, 1), nullable=False)
    comentario = Column(String(800), nullable=False)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    salao = relationship("Salao", back_populates="avaliacao")
