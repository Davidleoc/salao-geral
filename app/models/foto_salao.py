"""
Modelo: FotoSalao

Fotos exibidas na aba "Sobre" da página pública do salão.
O limite de fotos vem do plano (Plano.max_fotos).
Os arquivos ficam em app/static/uploads/saloes/{salao_id}/.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class FotoSalao(Base):
    __tablename__ = "fotos_salao"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    caminho = Column(String(500), nullable=False)    # URL pública: /static/uploads/saloes/1/abc.jpg
    ordem = Column(Integer, nullable=False, default=0)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    salao = relationship("Salao", back_populates="fotos")
