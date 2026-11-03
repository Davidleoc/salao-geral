"""
Pacotes e assinaturas vendidos aos clientes do salão.

  vender(...)            → registra a venda (a receita conta no dia da venda)
  validos_para(ag)       → pacotes do cliente que podem pagar este atendimento
  usar_sessao(ag, pc)    → desconta uma sessão e liga o atendimento ao pacote
  renovar_assinatura(pc) → assinatura mensal: novo ciclo com as sessões do mês

Um pacote vale para o serviço escolhido nele ou, se ficou em branco, para qualquer serviço.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.pacote import Pacote, PacoteCliente


def vender(db: Session, salao_id: int, pacote: Pacote, cliente_id: int, valor: Decimal,
           forma: Optional[str], vendedor_id: int) -> PacoteCliente:
    hoje = date.today()
    pc = PacoteCliente(
        salao_id=salao_id, pacote_id=pacote.id, cliente_id=cliente_id, sessoes_total=pacote.quantidade_sessoes,
        valor_pago=valor, forma_pagamento=forma, inicio=hoje,
        validade=hoje + timedelta(days=30 if pacote.tipo == "ASSINATURA" else pacote.validade_dias),
        vendido_por_id=vendedor_id,
    )
    db.add(pc)
    db.commit()
    return pc


def validos_para(db: Session, agendamento) -> list[PacoteCliente]:
    hoje = date.today()
    candidatos = (db.query(PacoteCliente).join(Pacote, Pacote.id == PacoteCliente.pacote_id)
                  .filter(PacoteCliente.salao_id == agendamento.salao_id, PacoteCliente.cliente_id == agendamento.cliente_id,
                          PacoteCliente.status == "ATIVO", PacoteCliente.validade >= hoje,
                          (Pacote.servico_id.is_(None)) | (Pacote.servico_id == agendamento.servico_id))
                  .order_by(PacoteCliente.validade).all())
    return [p for p in candidatos if p.sessoes_restantes > 0]


def usar_sessao(db: Session, agendamento, pacote_cliente: PacoteCliente) -> None:
    if agendamento.pacote_cliente_id or pacote_cliente.sessoes_restantes <= 0:
        return
    pacote_cliente.sessoes_usadas += 1
    agendamento.pacote_cliente_id = pacote_cliente.id
    if pacote_cliente.sessoes_restantes == 0 and pacote_cliente.pacote.tipo == "PACOTE":
        pacote_cliente.status = "ENCERRADO"
    db.commit()


def devolver_sessao(db: Session, agendamento) -> None:
    """Se um atendimento pago com pacote deixa de ser concluído, a sessão volta para o cliente."""
    pc = db.get(PacoteCliente, agendamento.pacote_cliente_id) if agendamento.pacote_cliente_id else None
    if pc:
        pc.sessoes_usadas = max(0, pc.sessoes_usadas - 1)
        if pc.status == "ENCERRADO" and pc.validade >= date.today():
            pc.status = "ATIVO"
    agendamento.pacote_cliente_id = None
    db.commit()


def renovar_assinatura(db: Session, pc: PacoteCliente, valor: Decimal, forma: Optional[str], vendedor_id: int) -> PacoteCliente:
    """Clube/assinatura do cliente: encerra o ciclo atual e abre o próximo."""
    pc.status = "ENCERRADO"
    db.commit()
    return vender(db, pc.salao_id, pc.pacote, pc.cliente_id, valor, forma, vendedor_id)
