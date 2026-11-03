"""
Rotas: Dashboard principal do salão
  GET /minhaagenda/dashboard

Exibe:
  - KPIs de hoje, semana e mês (agendamentos, faturamento, clientes)
  - Próximos agendamentos do dia
  - Serviço mais procurado
"""

from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.templates_compat import templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.deps import obter_usuario_atual
from app.tenant import obter_tenant, TenantContext
from app.models.usuario import Usuario
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.cliente import Cliente

router = APIRouter()


@router.get("/minhaagenda/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    hoje = date.today()

    # Funcionário: painel só com a própria agenda e os próprios ganhos
    if not tenant.pode("painel.financeiro"):
        return _dashboard_profissional(request, db, tenant, usuario, hoje)
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    inicio_mes = hoje.replace(day=1)

    # ── Agendamentos de hoje ──────────────────────────────────────
    agendamentos_hoje = tenant.query(Agendamento).filter(
        Agendamento.data == hoje,
        Agendamento.status.notin_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO,
        ])
    ).order_by(Agendamento.hora_inicio).all()

    # ── KPIs do mês ──────────────────────────────────────────────
    base_mes = tenant.query(Agendamento).filter(Agendamento.data >= inicio_mes)

    total_mes = base_mes.count()
    cancelados_mes = base_mes.filter(
        Agendamento.status.in_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO,
        ])
    ).count()

    # ── Faturamento Realizado e Previsto ─────────────────────────
    faturamento_realizado = base_mes.filter(
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).with_entities(func.sum(Agendamento.valor)).scalar() or 0

    faturamento_previsto = base_mes.filter(
        Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO])
    ).with_entities(func.sum(Agendamento.valor)).scalar() or 0

    atendimentos_concluidos = base_mes.filter(
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).count()

    ticket_medio = (float(faturamento_realizado) / atendimentos_concluidos) if atendimentos_concluidos > 0 else 0.0

    # ── Clientes novos vs recorrentes ────────────────────────────
    clientes_novos = tenant.query(Cliente).filter(
        func.date(Cliente.criado_em) >= inicio_mes
    ).count()

    # Clientes com mais de 1 agendamento concluído
    from app.models.servico import Servico
    subq_recorrentes = tenant.query(Agendamento).with_entities(
        Agendamento.cliente_id
    ).filter(
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).group_by(Agendamento.cliente_id).having(func.count(Agendamento.id) > 1).all()
    clientes_recorrentes_count = len(subq_recorrentes)

    # ── Serviço mais contratado no mês ───────────────────────────
    top_servico_row = tenant.query(Servico).with_entities(
        Servico.nome, func.count(Agendamento.id).label("total_vendas"), func.sum(Agendamento.valor).label("total_fat")
    ).join(Agendamento, Agendamento.servico_id == Servico.id).filter(
        Agendamento.data >= inicio_mes,
        Agendamento.status.notin_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO
        ])
    ).group_by(Servico.id).order_by(func.count(Agendamento.id).desc()).first()

    servico_top_nome = top_servico_row[0] if top_servico_row else "Nenhum ainda"
    servico_top_qtd = top_servico_row[1] if top_servico_row else 0

    # ── Ranking de Serviços ──────────────────────────────────────
    ranking_servicos = tenant.query(Servico).with_entities(
        Servico.nome, func.count(Agendamento.id).label("qtd"), func.sum(Agendamento.valor).label("total")
    ).join(Agendamento, Agendamento.servico_id == Servico.id).filter(
        Agendamento.data >= inicio_mes,
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).group_by(Servico.id).order_by(func.count(Agendamento.id).desc()).limit(5).all()

    # Permissões do plano
    pode_relatorios_avancados = tenant.pode_usar("relatorios_avancados")
    pode_exportar = tenant.pode_usar("exportacao")

    ctx = {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "hoje": hoje,
        "agendamentos_hoje": agendamentos_hoje,
        "total_mes": total_mes,
        "cancelados_mes": cancelados_mes,
        "atendimentos_concluidos": atendimentos_concluidos,
        "faturamento_realizado": float(faturamento_realizado),
        "faturamento_previsto": float(faturamento_previsto),
        "ticket_medio": ticket_medio,
        "clientes_novos": clientes_novos,
        "clientes_recorrentes_count": clientes_recorrentes_count,
        "servico_top_nome": servico_top_nome,
        "servico_top_qtd": servico_top_qtd,
        "ranking_servicos": ranking_servicos,
        "pode_relatorios_avancados": pode_relatorios_avancados,
        "pode_exportar": pode_exportar,
        "active_page": "dashboard",
    }
    return templates.TemplateResponse("painel/dashboard.html", ctx)


def _dashboard_profissional(request, db, tenant, usuario, hoje):
    from app.services.comissoes import ganhos_profissional
    meus_hoje = tenant.query(Agendamento).filter(
        Agendamento.data == hoje, Agendamento.profissional_id == usuario.id,
        Agendamento.status.notin_([StatusAgendamento.CANCELADO_PELO_CLIENTE, StatusAgendamento.CANCELADO_PELO_SALAO]),
    ).order_by(Agendamento.hora_inicio).all()
    proximos = tenant.query(Agendamento).filter(
        Agendamento.data > hoje, Agendamento.profissional_id == usuario.id,
        Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO]),
    ).order_by(Agendamento.data, Agendamento.hora_inicio).limit(8).all()
    ganhos_mes = ganhos_profissional(db, tenant.salao_id, usuario.id, hoje.replace(day=1), hoje)
    return templates.TemplateResponse(request, "painel/dashboard_profissional.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "dashboard",
        "agendamentos_hoje": meus_hoje, "proximos": proximos, "ganhos_mes": ganhos_mes, "hoje": hoje,
    })
