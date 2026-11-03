"""
Modelo: NotificacaoPainel

Avisos que aparecem na tela (sininho + balão) para quem está usando o sistema:
novo agendamento, serviço cadastrado, pedido de senha, vencimento etc.

destino:
  "SALAO" → usuários do salão (salao_id); dá para restringir por papéis ou a uma pessoa
  "ADMIN" → administradores do SaaS

"Lida" é controlado por usuário em Usuario.ultima_notificacao_vista (id da última vista).
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class NotificacaoPainel(Base):
    __tablename__ = "notificacoes_painel"

    id = Column(Integer, primary_key=True, index=True)
    destino = Column(String(10), nullable=False, default="SALAO", index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=True, index=True)

    para_papeis = Column(String(60), nullable=True)      # ex: "DONO,GERENTE" (vazio = todos)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # só para esta pessoa
    autor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)     # quem causou (não recebe)

    tipo = Column(String(40), nullable=False)            # ex: "agendamento", "servico", "senha"
    titulo = Column(String(150), nullable=False)
    mensagem = Column(String(500), nullable=True)
    link = Column(String(300), nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now(), index=True)
