"""
Modelos: Pacote e PacoteCliente

Pacote = o que o salão vende (ex: "10 sessões de massagem", "Clube da barba: 4 cortes/mês").
  tipo "PACOTE"     → N sessões, válidas por X dias
  tipo "ASSINATURA" → N sessões por mês (renovação mensal registrada pelo salão)

PacoteCliente = um pacote vendido a um cliente, com o saldo de sessões.
Cada atendimento pago com o pacote fica ligado a ele (Agendamento.pacote_cliente_id)
e não entra de novo no faturamento (a receita conta na venda do pacote).
"""

from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Pacote(Base):
    __tablename__ = "pacotes"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    nome = Column(String(150), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(String(12), nullable=False, default="PACOTE")     # PACOTE | ASSINATURA
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=True)  # vazio = vale para qualquer serviço
    quantidade_sessoes = Column(Integer, nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    validade_dias = Column(Integer, nullable=False, default=90)      # assinatura: 30
    publico = Column(Boolean, default=True)                          # aparece na página do salão
    ativo = Column(Boolean, default=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    servico = relationship("Servico")


class PacoteCliente(Base):
    __tablename__ = "pacotes_clientes"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    pacote_id = Column(Integer, ForeignKey("pacotes.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)

    sessoes_total = Column(Integer, nullable=False)
    sessoes_usadas = Column(Integer, nullable=False, default=0)
    valor_pago = Column(Numeric(10, 2), nullable=False)
    forma_pagamento = Column(String(12), nullable=True)
    inicio = Column(Date, nullable=False)
    validade = Column(Date, nullable=False)
    status = Column(String(12), nullable=False, default="ATIVO")   # ATIVO | ENCERRADO | CANCELADO

    vendido_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    pacote = relationship("Pacote")
    cliente = relationship("Cliente")

    @property
    def sessoes_restantes(self) -> int:
        return max(0, (self.sessoes_total or 0) - (self.sessoes_usadas or 0))
