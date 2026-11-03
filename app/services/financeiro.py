"""
Números do negócio (visão do admin do SaaS): MRR, cancelamentos, inadimplência, vencimentos.

MRR = soma das assinaturas pagantes convertidas para o mês (anual ÷ 12).
Testes grátis NÃO entram no MRR — aparecem separados como "potencial".
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.assinatura import Assinatura, Periodicidade, StatusAssinatura
from app.models.pagamento_assinatura import PagamentoAssinatura

PAGANTES = (StatusAssinatura.ATIVO, StatusAssinatura.PAGO, StatusAssinatura.EM_ATRASO)


def valor_mensal(a: Assinatura) -> Decimal:
    valor = a.valor_cobrado
    if valor is None and a.plano:
        valor = a.plano.preco_anual if a.periodicidade == Periodicidade.ANUAL else a.plano.preco_mensal
    valor = Decimal(str(valor or 0))
    return (valor / 12).quantize(Decimal("0.01")) if a.periodicidade == Periodicidade.ANUAL else valor


def mrr(db: Session, status=PAGANTES) -> Decimal:
    return sum((valor_mensal(a) for a in db.query(Assinatura).filter(Assinatura.status.in_(status)).all()), Decimal("0"))


def _inicio_mes(d: date) -> datetime:
    return datetime.combine(d.replace(day=1), time.min, tzinfo=timezone.utc)


def painel(db: Session) -> dict:
    hoje = date.today()
    inicio_mes = _inicio_mes(hoje)
    inicio_mes_passado = _inicio_mes((hoje.replace(day=1) - timedelta(days=1)))
    carregar = lambda q: q.options(joinedload(Assinatura.salao), joinedload(Assinatura.plano))  # noqa: E731

    pagantes = db.query(Assinatura).filter(Assinatura.status.in_(PAGANTES)).count()
    cancelados_mes = carregar(db.query(Assinatura)).filter(
        Assinatura.status == StatusAssinatura.CANCELADO, Assinatura.cancelada_em >= inicio_mes).all()
    cancelados_mes_passado = db.query(Assinatura).filter(
        Assinatura.status == StatusAssinatura.CANCELADO, Assinatura.cancelada_em >= inicio_mes_passado,
        Assinatura.cancelada_em < inicio_mes).count()
    base_churn = pagantes + len(cancelados_mes)

    recebido_mes = (db.query(func.coalesce(func.sum(PagamentoAssinatura.valor), 0))
                    .filter(PagamentoAssinatura.pago_em >= inicio_mes).scalar())
    recebido_mes_passado = (db.query(func.coalesce(func.sum(PagamentoAssinatura.valor), 0))
                            .filter(PagamentoAssinatura.pago_em >= inicio_mes_passado,
                                    PagamentoAssinatura.pago_em < inicio_mes).scalar())

    # Receita dos últimos 6 meses (pagamentos confirmados) para o gráfico de barras
    meses = []
    ref = hoje.replace(day=1)
    for _ in range(6):
        ini = _inicio_mes(ref)
        prox = _inicio_mes((ref + timedelta(days=32)).replace(day=1))
        total = (db.query(func.coalesce(func.sum(PagamentoAssinatura.valor), 0))
                 .filter(PagamentoAssinatura.pago_em >= ini, PagamentoAssinatura.pago_em < prox).scalar())
        meses.append({"mes": ref, "total": Decimal(str(total or 0))})
        ref = (ref - timedelta(days=1)).replace(day=1)
    meses.reverse()
    maior = max((m["total"] for m in meses), default=Decimal("0")) or Decimal("1")
    for m in meses:
        m["pct"] = int(m["total"] / maior * 100)

    inadimplentes = carregar(db.query(Assinatura)).filter(
        Assinatura.status.in_([StatusAssinatura.EM_ATRASO, StatusAssinatura.SUSPENSO])).order_by(Assinatura.data_fim).all()
    vencendo = carregar(db.query(Assinatura)).filter(
        Assinatura.status.in_([StatusAssinatura.ATIVO, StatusAssinatura.TESTE]),
        Assinatura.data_fim >= hoje, Assinatura.data_fim <= hoje + timedelta(days=7)).order_by(Assinatura.data_fim).all()
    aguardando = carregar(db.query(Assinatura)).filter(
        Assinatura.status == StatusAssinatura.AGUARDANDO_PAGAMENTO).order_by(Assinatura.criado_em.desc()).all()
    testes = carregar(db.query(Assinatura)).filter(Assinatura.status == StatusAssinatura.TESTE).all()

    return {
        "mrr": mrr(db),
        "potencial_testes": sum((valor_mensal(a) for a in testes), Decimal("0")),
        "pagantes": pagantes,
        "em_teste": len(testes),
        "recebido_mes": Decimal(str(recebido_mes or 0)),
        "recebido_mes_passado": Decimal(str(recebido_mes_passado or 0)),
        "cancelados_mes": cancelados_mes,
        "cancelados_mes_passado": cancelados_mes_passado,
        "churn_pct": (len(cancelados_mes) / base_churn * 100) if base_churn else 0,
        "inadimplentes": inadimplentes,
        "valor_inadimplente": sum((valor_mensal(a) for a in inadimplentes), Decimal("0")),
        "vencendo": vencendo,
        "aguardando": aguardando,
        "meses": meses,
        "hoje": hoje,
    }
