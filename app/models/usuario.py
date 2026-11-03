"""
Modelo: Usuario

Representa um usuário autenticado do sistema.
Pode ser:
  - ADMIN: dono do SaaS (acesso a /admin)
  - DONO: dono do salão
  - FUNCIONARIO: colaborador do salão

Multi-tenancy: cada usuário pertence a um salão (salao_id).
  O sistema garante que um usuário só acessa dados do próprio salão.
"""

import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class RoleUsuario(str, enum.Enum):
    ADMIN = "ADMIN"            # Dono do SaaS
    DONO = "DONO"              # Dono do salão: pode tudo no salão, inclusive mudar funções
    GERENTE = "GERENTE"        # Organiza agenda, serviços e comissões (não disponível no plano Básico)
    FUNCIONARIO = "FUNCIONARIO"  # Vê só a própria agenda e os próprios ganhos


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=True)  # null para ADMIN

    # Identidade
    nome = Column(String(200), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Autenticação — NUNCA guardar senha em texto puro
    senha_hash = Column(String(255), nullable=False)

    # MFA — Argon2id / TOTP
    mfa_ativo = Column(Boolean, default=False)
    mfa_secret = Column(String(255), nullable=True)  # criptografado

    # Perfil e status
    role = Column(SAEnum(RoleUsuario), nullable=False, default=RoleUsuario.FUNCIONARIO)
    ativo = Column(Boolean, default=True)
    email_verificado = Column(Boolean, default=False)

    # Perfil profissional (aparece na página de agendamento do salão)
    especialidade = Column(String(100), nullable=True)          # ex: "Cabeleireira", "Barbeiro"
    foto = Column(String(500), nullable=True)                   # /static/uploads/...
    telefone = Column(String(20), nullable=True)
    atende_clientes = Column(Boolean, default=True)             # aparece para o cliente escolher
    comissao_percentual = Column(Numeric(5, 2), nullable=True)  # % de comissão (regra em services/comissoes.py)
    comissao_base = Column(String(10), nullable=False, default="VALOR", server_default="VALOR")       # VALOR | LUCRO
    comissao_escopo = Column(String(10), nullable=False, default="PROPRIOS", server_default="PROPRIOS")  # PROPRIOS | SALAO

    # Sincronização de agenda (link secreto .ics para Google Agenda)
    calendario_token = Column(String(64), nullable=True, unique=True)

    # Notificações na tela: id da última notificação que o usuário já viu
    ultima_notificacao_vista = Column(Integer, nullable=False, default=0, server_default="0")

    # Recuperação de senha
    token_recuperacao = Column(String(255), nullable=True)
    token_recuperacao_expira = Column(DateTime(timezone=True), nullable=True)

    # Controle de tentativas de login (brute force)
    tentativas_login = Column(Integer, default=0)
    bloqueado_ate = Column(DateTime(timezone=True), nullable=True)

    # LGPD — aceite dos Termos de Uso e Política de Privacidade
    termos_aceitos_em = Column(DateTime(timezone=True), nullable=True)

    # Sessão
    ultimo_login = Column(DateTime(timezone=True), nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="usuarios")
    agendamentos_cancelados = relationship(
        "Agendamento",
        foreign_keys="Agendamento.cancelado_por_id",
        back_populates="cancelado_por_usuario"
    )
