"""
Modelo: LogSeguranca

Registra eventos de segurança para auditoria.

REGRA: nunca armazenar senhas, tokens completos ou dados sensíveis nesta tabela.

Eventos registrados:
  LOGIN, LOGIN_FALHOU, MFA_FALHOU, SENHA_ALTERADA,
  MFA_ATIVADO, MFA_DESATIVADO, AGENDAMENTO_CRIADO,
  AGENDAMENTO_CANCELADO, USUARIO_CRIADO, USUARIO_REMOVIDO,
  CONFIGURACAO_ALTERADA
"""

import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.sql import func
from app.database import Base


class EventoSeguranca(str, enum.Enum):
    LOGIN = "LOGIN"
    LOGIN_FALHOU = "LOGIN_FALHOU"
    MFA_FALHOU = "MFA_FALHOU"
    SENHA_ALTERADA = "SENHA_ALTERADA"
    MFA_ATIVADO = "MFA_ATIVADO"
    MFA_DESATIVADO = "MFA_DESATIVADO"
    AGENDAMENTO_CRIADO = "AGENDAMENTO_CRIADO"
    AGENDAMENTO_CANCELADO = "AGENDAMENTO_CANCELADO"
    USUARIO_CRIADO = "USUARIO_CRIADO"
    USUARIO_REMOVIDO = "USUARIO_REMOVIDO"
    CONFIGURACAO_ALTERADA = "CONFIGURACAO_ALTERADA"
    SESSAO_INVALIDA = "SESSAO_INVALIDA"
    # Equipe
    CONVITE_ENVIADO = "CONVITE_ENVIADO"
    PAPEL_ALTERADO = "PAPEL_ALTERADO"
    # Conta e senha
    EMAIL_VERIFICADO = "EMAIL_VERIFICADO"
    SENHA_RESET_SOLICITADO = "SENHA_RESET_SOLICITADO"
    SENHA_RESET_ENVIADO = "SENHA_RESET_ENVIADO"
    # Ações do administrador do SaaS
    PAGAMENTO_CONFIRMADO = "PAGAMENTO_CONFIRMADO"
    ASSINATURA_ALTERADA = "ASSINATURA_ALTERADA"
    SALAO_ALTERADO = "SALAO_ALTERADO"
    PLANO_ALTERADO = "PLANO_ALTERADO"
    ACESSO_SUPORTE = "ACESSO_SUPORTE"
    # LGPD
    DADOS_EXPORTADOS = "DADOS_EXPORTADOS"
    CONTA_ENCERRADA = "CONTA_ENCERRADA"
    DADOS_ANONIMIZADOS = "DADOS_ANONIMIZADOS"
    # Abuso
    LIMITE_EXCEDIDO = "LIMITE_EXCEDIDO"


class LogSeguranca(Base):
    __tablename__ = "logs_seguranca"

    id = Column(Integer, primary_key=True, index=True)

    # Quem fez (pode ser null se não estava autenticado)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=True)

    evento = Column(SAEnum(EventoSeguranca), nullable=False, index=True)
    descricao = Column(Text, nullable=True)           # detalhe do evento (sem dados sensíveis)

    # Contexto da requisição
    ip = Column(String(45), nullable=True)            # IPv4 ou IPv6
    user_agent = Column(String(500), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now(), index=True)
