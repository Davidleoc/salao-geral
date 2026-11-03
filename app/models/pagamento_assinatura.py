"""
Modelo: PagamentoAssinatura

Histórico de pagamentos da assinatura do salão (cada confirmação feita pelo admin).
Usado no painel financeiro (receita do mês) e na auditoria.
"""

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PagamentoAssinatura(Base):
    __tablename__ = "pagamentos_assinatura"

    id = Column(Integer, primary_key=True, index=True)
    assinatura_id = Column(Integer, ForeignKey("assinaturas.id"), nullable=False, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    valor = Column(Numeric(10, 2), nullable=False)
    periodo_inicio = Column(Date, nullable=False)
    periodo_fim = Column(Date, nullable=False)
    forma = Column(String(20), nullable=True, default="PIX")

    confirmado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    pago_em = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    assinatura = relationship("Assinatura")
