"""
Tarefas automáticas — rodam dentro do próprio servidor, a cada TAREFAS_INTERVALO_MINUTOS.

  lembretes        → e-mail ao cliente LEMBRETE_HORAS_ANTES do atendimento (plano com lembretes)
  cobranca         → teste grátis, avisos de vencimento, atraso e suspensão (services/cobranca.py)
  lista_espera     → expira pedidos de dias que já passaram (services/lista_espera.py)
  retencao_lgpd    → apaga/anonimiza dados vencidos (services/lgpd.py)

Cada tarefa é "idempotente": usa services/envios.primeira_vez() para não repetir envios,
então rodar duas vezes (ou em dois servidores) não manda e-mail em dobro.

Para rodar na hora (ex: testes, /dev, /admin): executar_tarefas()
Para desligar: TAREFAS_AUTOMATICAS=false no .env
"""

import asyncio
import logging
from datetime import datetime, timedelta

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def tarefa_lembretes(db) -> int:
    """Envia lembrete aos clientes com atendimento nas próximas LEMBRETE_HORAS_ANTES horas."""
    from app.models.agendamento import Agendamento, StatusAgendamento
    from app.models.cliente import Cliente
    from app.models.assinatura import Assinatura, StatusAssinatura
    from app.models.plano import Plano
    from app.services.email_service import enviar_lembrete_agendamento
    from app.services.envios import primeira_vez

    agora = datetime.now()
    limite = agora + timedelta(hours=settings.LEMBRETE_HORAS_ANTES)
    candidatos = (
        db.query(Agendamento)
        .join(Cliente, Cliente.id == Agendamento.cliente_id)
        .join(Assinatura, Assinatura.salao_id == Agendamento.salao_id)
        .join(Plano, Plano.id == Assinatura.plano_id)
        .filter(
            Agendamento.data >= agora.date(), Agendamento.data <= limite.date(),
            Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO]),
            Cliente.email.isnot(None), Cliente.email != "",
            Plano.lembretes == True,  # noqa: E712
            Assinatura.status.in_([StatusAssinatura.ATIVO, StatusAssinatura.TESTE, StatusAssinatura.EM_ATRASO]),
        )
        .all()
    )
    enviados = 0
    for ag in candidatos:
        inicio = datetime.combine(ag.data, ag.hora_inicio)
        if not (agora < inicio <= limite):
            continue
        if primeira_vez(db, f"lembrete:{ag.id}"):
            enviar_lembrete_agendamento(db, ag)
            enviados += 1
    db.commit()
    return enviados


def executar_tarefas(db=None) -> dict:
    """Roda todas as tarefas uma vez. Uma falha não impede as outras."""
    from app.services import cobranca, lgpd, lista_espera

    tarefas = [
        ("lembretes", tarefa_lembretes),
        ("cobranca", cobranca.tarefa_cobranca),
        ("lista_espera", lista_espera.tarefa_expirar),
        ("retencao_lgpd", lgpd.tarefa_retencao),
    ]
    resultado = {}
    sessao_propria = db is None
    db = db or SessionLocal()
    try:
        for nome, func in tarefas:
            try:
                resultado[nome] = func(db)
            except Exception:
                db.rollback()
                logger.exception("Tarefa automática '%s' falhou", nome)
                resultado[nome] = "erro"
    finally:
        if sessao_propria:
            db.close()
    logger.info("Tarefas automáticas: %s", resultado)
    return resultado


async def _laco():
    await asyncio.sleep(15)  # deixa o servidor terminar de subir
    while True:
        try:
            await run_in_threadpool(executar_tarefas)
        except Exception:
            logger.exception("Erro no laço de tarefas automáticas")
        await asyncio.sleep(max(1, settings.TAREFAS_INTERVALO_MINUTOS) * 60)


def iniciar() -> "asyncio.Task | None":
    if not settings.TAREFAS_AUTOMATICAS:
        logger.info("Tarefas automáticas desligadas (TAREFAS_AUTOMATICAS=false)")
        return None
    return asyncio.create_task(_laco())
