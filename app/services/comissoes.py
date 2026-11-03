"""
Comissões e ganhos por profissional.

Cada pessoa da equipe tem a SUA regra (tela Comissões, quem tem comissoes.gerenciar):
  - percentual (Usuario.comissao_percentual)
  - base   (Usuario.comissao_base):   "VALOR" = sobre o valor do serviço
                                      "LUCRO" = sobre o lucro do serviço (valor − custo, nunca negativo)
  - escopo (Usuario.comissao_escopo): "PROPRIOS" = só os atendimentos que ela fez
                                      "SALAO"    = sobre todos os atendimentos do salão no período

Só atendimentos CONCLUÍDOS contam.
No escopo PROPRIOS, o % é o gravado no agendamento quando ele foi criado (Agendamento.comissao_percentual),
então mudar o % não altera o que já foi feito; agendamentos antigos sem % gravado usam o % atual.
No escopo SALAO vale o % atual da pessoa (é uma participação no resultado do salão no período).

Lucro do salão = faturado − custos − comissões de todos.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.usuario import Usuario

BASES = {"VALOR": "valor do serviço", "LUCRO": "lucro do serviço (valor − custo)"}
ESCOPOS = {"PROPRIOS": "só o que atendeu", "SALAO": "todos os atendimentos do salão"}
ZERO = Decimal("0")


def base_de(pessoa: Optional[Usuario]) -> str:
    return getattr(pessoa, "comissao_base", None) or "VALOR"


def escopo_de(pessoa: Optional[Usuario]) -> str:
    return getattr(pessoa, "comissao_escopo", None) or "PROPRIOS"


def descrever_regra(pessoa: Optional[Usuario]) -> str:
    """'40% sobre o valor do serviço · só o que atendeu'"""
    if not pessoa or pessoa.comissao_percentual is None:
        return "Sem comissão definida"
    pct = f"{Decimal(pessoa.comissao_percentual).normalize():f}".replace(".", ",")
    return f"{pct}% sobre o {BASES[base_de(pessoa)]} · {ESCOPOS[escopo_de(pessoa)]}"


def custo_de(ag: Agendamento) -> Decimal:
    if ag.custo is not None:
        return Decimal(ag.custo)
    if ag.servico and ag.servico.custo is not None:
        return Decimal(ag.servico.custo)
    return ZERO


def valor_base(ag: Agendamento, base: str) -> Decimal:
    valor = Decimal(ag.valor or 0)
    return max(valor - custo_de(ag), ZERO) if base == "LUCRO" else valor


def _pct(ag: Agendamento) -> Decimal:
    if ag.comissao_percentual is not None:
        return Decimal(ag.comissao_percentual)
    if ag.profissional and ag.profissional.comissao_percentual is not None:
        return Decimal(ag.profissional.comissao_percentual)
    return ZERO


def comissao_de(ag: Agendamento) -> Decimal:
    """Comissão de UM atendimento para quem o fez (só faz sentido no escopo PROPRIOS)."""
    pessoa = ag.profissional
    if pessoa and escopo_de(pessoa) == "SALAO":
        return ZERO  # quem ganha sobre o salão todo não ganha de novo por atendimento
    return (valor_base(ag, base_de(pessoa)) * _pct(ag) / 100).quantize(Decimal("0.01"))


def _concluidos(db: Session, salao_id: int, inicio: date, fim: date) -> list[Agendamento]:
    return (db.query(Agendamento)
            .options(joinedload(Agendamento.profissional), joinedload(Agendamento.servico))
            .filter(Agendamento.salao_id == salao_id, Agendamento.status == StatusAgendamento.CONCLUIDO,
                    Agendamento.data >= inicio, Agendamento.data <= fim)
            .all())


def comissao_da_pessoa(pessoa: Usuario, ags: list[Agendamento]) -> Decimal:
    """Comissão total de uma pessoa no período, segundo a regra dela. `ags` = concluídos do salão no período."""
    if pessoa.comissao_percentual is None:
        return ZERO
    if escopo_de(pessoa) == "SALAO":
        total = sum((valor_base(a, base_de(pessoa)) for a in ags), ZERO)
        return (total * Decimal(pessoa.comissao_percentual) / 100).quantize(Decimal("0.01"))
    return sum((comissao_de(a) for a in ags if a.profissional_id == pessoa.id), ZERO)


def ganhos_profissional(db: Session, salao_id: int, usuario_id: int, inicio: date, fim: date) -> dict:
    """Ganhos de uma pessoa. Não devolve totais do salão (o funcionário não vê o lucro geral)."""
    pessoa = db.get(Usuario, usuario_id)
    ags = _concluidos(db, salao_id, inicio, fim)
    proprios = [a for a in ags if a.profissional_id == usuario_id]
    return {
        "atendimentos": len(proprios),
        "faturado": float(sum((Decimal(a.valor or 0) for a in proprios), ZERO)),
        "comissao": float(comissao_da_pessoa(pessoa, ags)) if pessoa else 0.0,
        "lista": proprios,
        "escopo": escopo_de(pessoa),
        "regra": descrever_regra(pessoa),
    }


def relatorio_comissoes(db: Session, salao_id: int, inicio: date, fim: date) -> dict:
    """
    {"linhas": [...uma por pessoa com atendimento ou comissão...], "totais": {...}}
    Linha: nome, regra, atendimentos, faturado (do que a pessoa atendeu), comissao.
    Totais do salão: atendimentos, faturado, custo, comissao (soma de todos), lucro_salao.
    """
    ags = _concluidos(db, salao_id, inicio, fim)
    equipe = db.query(Usuario).filter(Usuario.salao_id == salao_id).all()

    linhas = []
    for pessoa in equipe:
        proprios = [a for a in ags if a.profissional_id == pessoa.id]
        comissao = comissao_da_pessoa(pessoa, ags)
        if not proprios and not comissao:
            continue
        linhas.append({
            "profissional": pessoa, "nome": pessoa.nome, "regra": descrever_regra(pessoa),
            "escopo": escopo_de(pessoa), "atendimentos": len(proprios),
            "faturado": float(sum((Decimal(a.valor or 0) for a in proprios), ZERO)), "comissao": float(comissao),
        })
    sem_prof = [a for a in ags if not a.profissional_id]
    if sem_prof:
        linhas.append({"profissional": None, "nome": "Sem profissional definido", "regra": "Sem comissão",
                       "escopo": "", "atendimentos": len(sem_prof),
                       "faturado": float(sum((Decimal(a.valor or 0) for a in sem_prof), ZERO)), "comissao": 0.0})

    faturado = sum((Decimal(a.valor or 0) for a in ags), ZERO)
    custo = sum((custo_de(a) for a in ags), ZERO)
    comissao_total = sum((Decimal(str(l["comissao"])) for l in linhas), ZERO)
    totais = {"atendimentos": len(ags), "faturado": float(faturado), "custo": float(custo),
              "comissao": float(comissao_total), "lucro_salao": float(faturado - custo - comissao_total)}
    return {"linhas": sorted(linhas, key=lambda l: (l["faturado"], l["comissao"]), reverse=True), "totais": totais}


def total_comissoes(db: Session, salao_id: int, inicio: date, fim: date) -> float:
    return relatorio_comissoes(db, salao_id, inicio, fim)["totais"]["comissao"]
