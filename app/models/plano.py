"""
Modelo: Plano

Define os planos de assinatura do SaaS.
Todos os limites e recursos ficam no banco — nunca hardcoded no código.
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Plano(Base):
    __tablename__ = "planos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)                  # Básico, Pro, Premium
    descricao = Column(Text, nullable=True)

    # Preços
    preco_mensal = Column(Numeric(10, 2), nullable=False)
    preco_anual = Column(Numeric(10, 2), nullable=False)

    # Limites operacionais
    max_usuarios = Column(Integer, nullable=False, default=2)   # Funcionários/usuários
    max_servicos = Column(Integer, nullable=True)               # None = ilimitado
    max_emails = Column(Integer, nullable=False, default=2)     # E-mails de notificação
    historico_meses = Column(Integer, nullable=False, default=2) # Meses de histórico acessível
    max_fotos = Column(Integer, nullable=False, default=0)      # Fotos na aba "Sobre" da página pública

    # Recursos disponíveis (True/False por plano)
    exportacao = Column(Boolean, default=False)                 # Exportação CSV/Excel
    lembretes = Column(Boolean, default=False)                  # Lembretes automáticos por e-mail
    personalizacao_avancada = Column(Boolean, default=False)    # Cores, logo, etc.
    relatorios_avancados = Column(Boolean, default=False)       # Relatórios detalhados
    dominio_personalizado = Column(Boolean, default=False)      # Domínio próprio do salão
    permite_gerente = Column(Boolean, default=False)            # Função "Gerente" na equipe
    sincronizacao_agenda = Column(Boolean, default=False)       # Link para Google Agenda / calendários

    ativo = Column(Boolean, default=True)

    # Relacionamentos
    assinaturas = relationship("Assinatura", back_populates="plano")
