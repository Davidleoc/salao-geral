"""
Modelo: Salao

Representa um salão de beleza cadastrado no sistema.
Todos os dados específicos do salão ficam aqui — nunca no código.

Cada salão tem um slug único que define sua URL pública:
  seudominio.com/{slug}
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Salao(Base):
    __tablename__ = "saloes"

    id = Column(Integer, primary_key=True, index=True)

    # Identidade
    nome = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)  # /studio-bella

    # Contato
    email_principal = Column(String(255), nullable=False)
    email_secundario = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    whatsapp = Column(String(20), nullable=True)
    instagram = Column(String(100), nullable=True)

    # Endereço
    endereco = Column(String(500), nullable=True)
    cidade = Column(String(100), nullable=True)
    estado = Column(String(2), nullable=True)
    cep = Column(String(10), nullable=True)

    # Aparência e identidade visual
    descricao = Column(Text, nullable=True)
    sobre = Column(Text, nullable=True)              # aba "Sobre" da página pública (até 800 caracteres)
    logo = Column(String(500), nullable=True)        # caminho do arquivo
    cor_principal = Column(String(7), default="#6366f1")   # hex
    cor_secundaria = Column(String(7), default="#a855f7")  # hex

    # Documento do contratante (CPF ou CNPJ, só números) — nota fiscal e prevenção de fraude
    documento = Column(String(14), nullable=True, index=True)
    tipo_documento = Column(String(4), nullable=True)   # "CPF" ou "CNPJ"

    # Avaliação do atendimento pelo cliente final
    pedir_avaliacao = Column(Boolean, default=False)    # envia convite após atendimento concluído
    link_avaliacao_google = Column(String(500), nullable=True)

    # Encerramento de conta (LGPD): dados anonimizados após o prazo
    encerrado_em = Column(DateTime(timezone=True), nullable=True)
    exclusao_prevista_em = Column(DateTime(timezone=True), nullable=True)
    anonimizado_em = Column(DateTime(timezone=True), nullable=True)

    # Status
    ativo = Column(Boolean, default=False)           # ativo após pagamento confirmado
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    usuarios = relationship("Usuario", back_populates="salao")
    clientes = relationship("Cliente", back_populates="salao")
    servicos = relationship("Servico", back_populates="salao")
    agendamentos = relationship("Agendamento", back_populates="salao")
    horarios = relationship("HorarioFuncionamento", back_populates="salao")
    bloqueios = relationship("BloqueioHorario", back_populates="salao")
    assinatura = relationship("Assinatura", back_populates="salao", uselist=False)
    notificacoes = relationship("Notificacao", back_populates="salao")
    fotos = relationship("FotoSalao", back_populates="salao", order_by="FotoSalao.ordem")
    avaliacao = relationship("Avaliacao", back_populates="salao", uselist=False)
