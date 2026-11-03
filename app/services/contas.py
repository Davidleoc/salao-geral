"""
Contas de usuário: confirmação de e-mail e redefinição de senha.

Redefinição de senha (fluxo com o administrador):
  1. A pessoa pede em /minhaagenda/recuperar-senha → solicitar_nova_senha() cria um pedido
     e avisa o admin na tela (sininho).
  2. O admin confere em /admin/senhas e clica "Enviar link" → enviar_link_redefinicao().
  3. A pessoa recebe no e-mail cadastrado um link de uso único (vale 24h e para de valer
     assim que a senha é trocada). O admin nunca vê nem escolhe a senha.
O dono do salão também pode mandar o link para alguém da equipe (tela Equipe).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.log_seguranca import EventoSeguranca
from app.models.solicitacao_senha import SolicitacaoSenha
from app.models.usuario import Usuario
from app.security import gerar_token_recuperacao, gerar_token_verificacao
from app.services.auditoria import mascarar_email, registrar_evento
from app.services.email_service import email_sistema
from app.services.notificacoes import notificar_admin


def enviar_email_verificacao(usuario: Usuario) -> None:
    link = f"/verificar-email?token={gerar_token_verificacao(usuario)}"
    email_sistema(
        usuario.email, f"Confirme seu e-mail — {settings.APP_NAME}", "Confirme seu e-mail",
        [f"Olá, {usuario.nome.split()[0]}!",
         "Para ativar sua conta e começar a usar o sistema, confirme que este e-mail é seu.",
         "O link vale por 3 dias. Se não foi você que fez o cadastro, ignore esta mensagem."],
        botao_texto="Confirmar meu e-mail", botao_url=link, tipo="VERIFICACAO_EMAIL",
    )


def enviar_link_redefinicao(usuario: Usuario, motivo: str = "") -> None:
    link = f"/minhaagenda/nova-senha?token={gerar_token_recuperacao(usuario)}"
    paragrafos = [f"Olá, {usuario.nome.split()[0]}!"]
    if motivo:
        paragrafos.append(motivo)
    paragrafos += [
        "Clique no botão abaixo para criar uma nova senha. O link vale por 24 horas e só pode ser usado uma vez.",
        "Se você não pediu isso, ignore este e-mail — sua senha atual continua valendo.",
    ]
    email_sistema(usuario.email, f"Criar nova senha — {settings.APP_NAME}", "Criar uma nova senha",
                  paragrafos, botao_texto="Criar nova senha", botao_url=link, tipo="REDEFINICAO_SENHA")


def solicitar_nova_senha(db: Session, usuario: Usuario, request) -> None:
    """Registra o pedido (sem duplicar pedidos pendentes de 24h) e avisa o admin."""
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    ja_pendente = db.query(SolicitacaoSenha).filter(
        SolicitacaoSenha.usuario_id == usuario.id,
        SolicitacaoSenha.status == "PENDENTE",
        SolicitacaoSenha.criado_em >= limite,
    ).first()
    if ja_pendente:
        return
    db.add(SolicitacaoSenha(usuario_id=usuario.id, ip=request.client.host if request.client else None))
    registrar_evento(db, EventoSeguranca.SENHA_RESET_SOLICITADO, request, usuario_id=usuario.id,
                     salao_id=usuario.salao_id, commit=False)
    salao_nome = usuario.salao.nome if usuario.salao else "Administração"
    notificar_admin(db, "senha", "Pedido de nova senha",
                    f"{usuario.nome} ({mascarar_email(usuario.email)}) — {salao_nome}",
                    link="/admin/senhas", salao_id=usuario.salao_id, commit=False)
    db.commit()
