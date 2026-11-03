"""
Serviço de E-mails.

  enviar_email(...)      → envio de baixo nível (SMTP se configurado; senão só registra)
  email_sistema(...)     → e-mail com a marca MeuAgendamento (cobrança, convite, senha, conta)
  email_do_salao(...)    → e-mail com a marca do salão (avaliação, lista de espera)
  enviar_*_agendamento   → e-mails do agendamento (confirmação, cancelamento, lembrete)

Envio real: preencha SMTP_HOST, SMTP_PORT, SMTP_USUARIO, SMTP_SENHA e EMAIL_FROM no .env.
Sem SMTP_HOST (desenvolvimento), nada sai do computador: o e-mail fica no log
e na caixa de saída de testes (/dev/emails).

O envio SMTP roda em segundo plano, para a tela não ficar esperando o servidor de e-mail.
IMPORTANTE: nunca coloque senhas ou tokens de sessão no corpo do e-mail.
"""

import logging
import smtplib
import threading
from collections import deque
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterable, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agendamento import Agendamento
from app.models.notificacao import Notificacao, TipoNotificacao

logger = logging.getLogger(__name__)

_email_env = Environment(loader=FileSystemLoader("app/templates"), autoescape=select_autoescape(["html"]))

# Caixa de saída em memória para o painel /dev/emails (não existe em produção)
caixa_saida_dev: deque = deque(maxlen=100)


# ---------------------------------------------------------------------------
# Envio de baixo nível
# ---------------------------------------------------------------------------
def _enviar_smtp(para: str, assunto: str, html: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = para
    msg.set_content("Abra este e-mail em um leitor que mostre HTML.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            if settings.SMTP_TLS:
                smtp.starttls()
            if settings.SMTP_USUARIO:
                smtp.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
            smtp.send_message(msg)
        logger.info("E-mail enviado para %s: %s", para, assunto)
    except Exception:
        logger.exception("Falha ao enviar e-mail para %s (%s)", para, assunto)


def enviar_email(para: str, assunto: str, html: str, tipo: str = "SISTEMA") -> None:
    """Envia (ou registra, sem SMTP) um e-mail HTML."""
    if not para:
        return
    if not settings.is_production:
        caixa_saida_dev.append({"tipo": tipo, "destinatario": para, "assunto": assunto, "corpo": html, "quando": datetime.now()})
    logger.info("📧 [%s] Para: %s | Assunto: %s", tipo, para, assunto)
    if settings.SMTP_HOST:
        threading.Thread(target=_enviar_smtp, args=(para, assunto, html), daemon=True).start()


def email_sistema(para: str, assunto: str, titulo: str, paragrafos: Iterable[str],
                  botao_texto: Optional[str] = None, botao_url: Optional[str] = None,
                  destaque: Optional[str] = None, tipo: str = "SISTEMA") -> None:
    """E-mail com a marca do sistema. `destaque` aparece numa caixa (ex: valor a pagar)."""
    html = _email_env.get_template("emails/sistema.html").render(
        app_name=settings.APP_NAME, ano_atual=datetime.now().year, titulo=titulo,
        paragrafos=list(paragrafos), botao_texto=botao_texto, botao_url=_absoluta(botao_url), destaque=destaque,
    )
    enviar_email(para, assunto, html, tipo)


def email_do_salao(salao, para: str, assunto: str, titulo: str, paragrafos: Iterable[str],
                   botao_texto: Optional[str] = None, botao_url: Optional[str] = None, tipo: str = "SALAO") -> None:
    """E-mail com as cores e o nome do salão (para os clientes do salão)."""
    html = _email_env.get_template("emails/salao_mensagem.html").render(
        app_name=settings.APP_NAME, ano_atual=datetime.now().year, salao=salao,
        cor_primaria=salao.cor_principal or "#6366f1", cor_secundaria=salao.cor_secundaria or "#a855f7",
        titulo=titulo, paragrafos=list(paragrafos), botao_texto=botao_texto, botao_url=_absoluta(botao_url),
    )
    enviar_email(para, assunto, html, tipo)


def _absoluta(url: Optional[str]) -> Optional[str]:
    if url and url.startswith("/"):
        return settings.URL_BASE.rstrip("/") + url
    return url


# ---------------------------------------------------------------------------
# E-mails do agendamento
# ---------------------------------------------------------------------------
def _preparar_contexto(agendamento: Agendamento) -> dict:
    salao = agendamento.salao
    return {
        "app_name": settings.APP_NAME,
        "ano_atual": datetime.now().year,
        "salao": salao,
        "cliente": agendamento.cliente,
        "servico": agendamento.servico,
        "profissional": agendamento.profissional,
        "agendamento": agendamento,
        "cor_primaria": salao.cor_principal or "#6366f1",
        "cor_secundaria": salao.cor_secundaria or "#a855f7",
        "data_formatada": agendamento.data.strftime("%d/%m/%Y"),
        "hora_inicio_formatada": agendamento.hora_inicio.strftime("%H:%M"),
        "hora_fim_formatada": agendamento.hora_fim.strftime("%H:%M") if agendamento.hora_fim else None,
        "valor_formatado": f"R$ {agendamento.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "motivo_cancelamento": agendamento.motivo_cancelamento,
    }


def _registrar_e_enviar(db: Session, agendamento: Agendamento, tipo: TipoNotificacao,
                        destinatario: Optional[str], assunto: str, template: str) -> Optional[Notificacao]:
    """Renderiza, envia e guarda o histórico (tabela notificacoes). Sem destinatário, não faz nada."""
    if not destinatario:
        return None
    corpo = _email_env.get_template(template).render(**_preparar_contexto(agendamento))
    notificacao = Notificacao(
        salao_id=agendamento.salao_id, agendamento_id=agendamento.id, tipo=tipo,
        destinatario_email=destinatario, assunto=assunto, corpo=corpo,
        enviado=True, enviado_em=datetime.now(timezone.utc),
    )
    db.add(notificacao)
    db.commit()
    enviar_email(destinatario, assunto, corpo, tipo.value)
    return notificacao


def enviar_confirmacao_agendamento(db: Session, agendamento: Agendamento):
    """Para o CLIENTE, se ele informou e-mail."""
    data = agendamento.data.strftime("%d/%m/%Y")
    return _registrar_e_enviar(db, agendamento, TipoNotificacao.CONFIRMACAO_AGENDAMENTO, agendamento.cliente.email,
                               f"✅ Agendamento confirmado — {agendamento.servico.nome} em {data}", "emails/confirmacao.html")


def enviar_cancelamento_agendamento(db: Session, agendamento: Agendamento):
    """Para o CLIENTE, quando o salão cancela."""
    data = agendamento.data.strftime("%d/%m/%Y")
    return _registrar_e_enviar(db, agendamento, TipoNotificacao.CANCELAMENTO_AGENDAMENTO, agendamento.cliente.email,
                               f"Agendamento cancelado — {agendamento.servico.nome} em {data}", "emails/cancelamento.html")


def enviar_novo_agendamento_salao(db: Session, agendamento: Agendamento):
    """Para o SALÃO (e-mail principal), avisando de um agendamento feito pelo cliente."""
    return _registrar_e_enviar(db, agendamento, TipoNotificacao.NOVO_AGENDAMENTO_SALAO, agendamento.salao.email_principal,
                               f"📅 Novo agendamento: {agendamento.cliente.nome} — {agendamento.servico.nome}", "emails/novo_agendamento.html")


def enviar_lembrete_agendamento(db: Session, agendamento: Agendamento):
    """Para o CLIENTE, na véspera. Chamado pelas tarefas automáticas (services/tarefas.py)."""
    return _registrar_e_enviar(db, agendamento, TipoNotificacao.LEMBRETE_AGENDAMENTO, agendamento.cliente.email,
                               f"⏰ Lembrete: seu horário de {agendamento.servico.nome} está chegando", "emails/lembrete.html")
