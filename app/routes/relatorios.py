"""
Rotas: Relatórios Analíticos e Exportação (Fase 12 & 13)

GET /minhaagenda/relatorios            → Painel de relatórios analíticos
GET /minhaagenda/relatorios/exportar   → Download de arquivo CSV (se o plano permitir)
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from app.templates_compat import templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.cliente import Cliente
from app.models.pacote import PacoteCliente
from app.models.servico import Servico
from app.services.comissoes import total_comissoes
from app.models.usuario import Usuario
from app.tenant import obter_tenant

router = APIRouter()


@router.get("/minhaagenda/relatorios", response_class=HTMLResponse)
def painel_relatorios(
    request: Request,
    meses_filtro: int = 1,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    """
    Exibe relatórios detalhados com isolamento multi-tenant:
    - Faturamento por Status (Concluído, Agendado, Cancelado)
    - Desempenho por Serviço (Quantidade e Receita)
    - Clientes mais fiéis (recorrentes)
    - Verificação de limites de histórico do plano
    """
    tenant = obter_tenant(db, usuario)
    tenant.exigir("relatorios.ver")
    plano = tenant.plano

    # Verifica limite de histórico permitido pelo plano
    max_meses_permitido = plano.historico_meses if plano else 2
    if meses_filtro > max_meses_permitido:
        meses_filtro = max_meses_permitido

    hoje = date.today()
    data_limite = hoje - timedelta(days=30 * meses_filtro)

    # Base filtrada pelo histórico permitido
    query_base = tenant.query(Agendamento).filter(Agendamento.data >= data_limite)

    # Métricas de faturamento. Atendimento pago com pacote não entra de novo:
    # o dinheiro do pacote conta no dia da venda (receita_pacotes).
    fat_concluido = query_base.filter(
        Agendamento.status == StatusAgendamento.CONCLUIDO, Agendamento.pacote_cliente_id.is_(None)
    ).with_entities(func.sum(Agendamento.valor)).scalar() or Decimal("0.00")
    receita_pacotes = tenant.query(PacoteCliente).filter(PacoteCliente.inicio >= data_limite).with_entities(
        func.sum(PacoteCliente.valor_pago)).scalar() or Decimal("0.00")
    comissoes = total_comissoes(db, tenant.salao_id, data_limite, hoje)

    fat_previsto = query_base.filter(
        Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO])
    ).with_entities(func.sum(Agendamento.valor)).scalar() or Decimal("0.00")

    fat_cancelado = query_base.filter(
        Agendamento.status.in_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO
        ])
    ).with_entities(func.sum(Agendamento.valor)).scalar() or Decimal("0.00")

    total_concluidos = query_base.filter(Agendamento.status == StatusAgendamento.CONCLUIDO).count()
    total_cancelados = query_base.filter(
        Agendamento.status.in_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO
        ])
    ).count()
    total_nao_compareceu = query_base.filter(Agendamento.status == StatusAgendamento.NAO_COMPARECEU).count()

    ticket_medio = (float(fat_concluido) / total_concluidos) if total_concluidos > 0 else 0.0

    # Custo de cada atendimento: o custo gravado no agendamento (histórico);
    # para agendamentos antigos, sem custo gravado, usa o custo atual do serviço.
    custo_atendimento = func.coalesce(Agendamento.custo, Servico.custo, 0)

    custo_concluido = query_base.join(Servico, Agendamento.servico_id == Servico.id).filter(
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).with_entities(func.sum(custo_atendimento)).scalar() or Decimal("0.00")

    lucro_concluido = float(fat_concluido) - float(custo_concluido)
    margem_lucro = (lucro_concluido / float(fat_concluido) * 100) if fat_concluido else 0.0
    entrada_total = float(fat_concluido) + float(receita_pacotes)
    lucro_salao = entrada_total - float(custo_concluido) - comissoes
    margem_salao = (lucro_salao / entrada_total * 100) if entrada_total else 0.0

    # Desempenho por Serviço: faturamento, custo e lucro (preço − custo)
    linhas_servicos = tenant.query(Servico).with_entities(
        Servico.nome,
        func.count(Agendamento.id).label("total_agendamentos"),
        func.sum(Agendamento.valor).label("faturamento_total"),
        func.sum(custo_atendimento).label("custo_total"),
    ).join(Agendamento, Agendamento.servico_id == Servico.id).filter(
        Agendamento.salao_id == tenant.salao_id,
        Agendamento.data >= data_limite,
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).group_by(Servico.id).all()

    desempenho_servicos = []
    for nome, qtd, faturado, custo in linhas_servicos:
        faturado = float(faturado or 0)
        custo = float(custo or 0)
        lucro = faturado - custo
        desempenho_servicos.append({
            "nome": nome,
            "qtd": qtd,
            "faturado": faturado,
            "custo": custo,
            "lucro": lucro,
            "margem": (lucro / faturado * 100) if faturado else 0.0,
        })
    desempenho_servicos.sort(key=lambda s: s["lucro"], reverse=True)
    maior_faturamento = max((s["faturado"] for s in desempenho_servicos), default=0)

    # Clientes mais frequentes
    clientes_fieis = tenant.query(Cliente).with_entities(
        Cliente.nome,
        Cliente.telefone,
        func.count(Agendamento.id).label("total_visitas"),
        func.sum(Agendamento.valor).label("gasto_total")
    ).join(Agendamento, Agendamento.cliente_id == Cliente.id).filter(
        Agendamento.data >= data_limite,
        Agendamento.status == StatusAgendamento.CONCLUIDO
    ).group_by(Cliente.id).order_by(func.count(Agendamento.id).desc()).limit(10).all()

    pode_exportar = tenant.pode_usar("exportacao")
    pode_relatorios_avancados = tenant.pode_usar("relatorios_avancados")

    return templates.TemplateResponse("painel/relatorios.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "plano": plano,
        "meses_filtro": meses_filtro,
        "max_meses_permitido": max_meses_permitido,
        "fat_concluido": float(fat_concluido),
        "fat_previsto": float(fat_previsto),
        "fat_cancelado": float(fat_cancelado),
        "custo_concluido": float(custo_concluido),
        "lucro_concluido": lucro_concluido,
        "margem_lucro": margem_lucro,
        "receita_pacotes": float(receita_pacotes),
        "comissoes": comissoes,
        "lucro_salao": lucro_salao,
        "margem_salao": margem_salao,
        "maior_faturamento": maior_faturamento,
        "total_concluidos": total_concluidos,
        "total_cancelados": total_cancelados,
        "total_nao_compareceu": total_nao_compareceu,
        "ticket_medio": ticket_medio,
        "desempenho_servicos": desempenho_servicos,
        "clientes_fieis": clientes_fieis,
        "pode_exportar": pode_exportar,
        "pode_relatorios_avancados": pode_relatorios_avancados,
        "active_page": "relatorios",
    })


@router.get("/minhaagenda/relatorios/exportar")
def exportar_dados_csv(
    tipo: str = "agendamentos",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    """
    Gera e exporta relatório em formato CSV para análise externa.
    Recurso exclusivo para planos com 'exportacao = True'.
    """
    tenant = obter_tenant(db, usuario)
    tenant.exigir("relatorios.exportar")
    if not tenant.pode_usar("exportacao"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu plano atual não inclui a exportação de dados. Faça um upgrade para o plano Premium."
        )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    if tipo == "clientes":
        # Exporta clientes
        writer.writerow(["ID", "Nome", "WhatsApp/Telefone", "Email", "Observações", "Cadastrado Em"])
        clientes = tenant.query(Cliente).order_by(Cliente.nome).all()
        for c in clientes:
            writer.writerow([
                c.id,
                c.nome,
                c.telefone,
                c.email or "",
                c.observacoes or "",
                c.criado_em.strftime("%d/%m/%Y") if c.criado_em else ""
            ])
        filename = f"clientes_{tenant.salao.slug}.csv"
    else:
        # Exporta agendamentos
        writer.writerow([
            "ID", "Data", "Início", "Fim", "Cliente", "WhatsApp",
            "Serviço", "Valor (R$)", "Custo (R$)", "Lucro (R$)", "Forma Pagamento", "Status",
            "Observações", "Motivo Cancelamento"
        ])
        agendamentos = tenant.query(Agendamento).order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc()).all()
        for a in agendamentos:
            custo = a.custo if a.custo is not None else (a.servico.custo if a.servico and a.servico.custo is not None else Decimal("0"))
            writer.writerow([
                a.id,
                a.data.strftime("%d/%m/%Y"),
                a.hora_inicio.strftime("%H:%M"),
                a.hora_fim.strftime("%H:%M") if a.hora_fim else "",
                a.cliente.nome if a.cliente else "",
                a.cliente.telefone if a.cliente else "",
                a.servico.nome if a.servico else "",
                f"{a.valor:.2f}".replace(".", ","),
                f"{custo:.2f}".replace(".", ","),
                f"{a.valor - custo:.2f}".replace(".", ","),
                a.forma_pagamento.value if a.forma_pagamento else "",
                a.status.value,
                a.observacoes or "",
                a.motivo_cancelamento or ""
            ])
        filename = f"agendamentos_{tenant.salao.slug}.csv"

    output.seek(0)
    # Codificação utf-8-sig para compatibilidade com Microsoft Excel no Windows
    csv_bytes = output.getvalue().encode("utf-8-sig")

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return Response(content=csv_bytes, media_type="text/csv", headers=headers)
