"""
Equipe do salão: convites com link único.

Regras do convite:
  - O link vai só para o e-mail convidado e cria UMA conta (depois de usado, não funciona mais).
  - A conta criada usa exatamente o e-mail do convite (não dá para trocar no cadastro).
  - Vale CONVITE_VALIDADE_DIAS dias. No banco fica só o hash do link.
  - Conta no limite de usuários do plano (pessoas ativas + convites pendentes).
  - "Gerente" só em planos com permite_gerente (não existe no Básico).
Quem pode convidar quem: app/permissoes.py → PODE_CONVIDAR (o admin do SaaS pode tudo).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.assinatura import Assinatura, StatusAssinatura
from app.models.convite_equipe import ConviteEquipe
from app.models.log_seguranca import EventoSeguranca
from app.models.plano import Plano
from app.models.salao import Salao
from app.models.usuario import RoleUsuario, Usuario
from app.permissoes import PODE_CONVIDAR, ROTULOS, papel_de
from app.security import gerar_token_url, hash_token
from app.services.auditoria import registrar_evento
from app.services.email_service import email_sistema
from app.validacao import normalizar_email


class ErroConvite(Exception):
    pass


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def plano_do_salao(db: Session, salao_id: int) -> Optional[Plano]:
    a = db.query(Assinatura).filter(Assinatura.salao_id == salao_id).first()
    return db.query(Plano).filter(Plano.id == a.plano_id).first() if a else None


def membros(db: Session, salao_id: int):
    return (db.query(Usuario).filter(Usuario.salao_id == salao_id, Usuario.ativo == True)  # noqa: E712
            .order_by(Usuario.role, Usuario.nome).all())


def convites_pendentes(db: Session, salao_id: int):
    return [c for c in db.query(ConviteEquipe).filter(
        ConviteEquipe.salao_id == salao_id, ConviteEquipe.usado_em.is_(None), ConviteEquipe.cancelado_em.is_(None),
    ).order_by(ConviteEquipe.criado_em.desc()).all() if _aware(c.expira_em) > agora()]


def vagas(db: Session, salao_id: int) -> dict:
    plano = plano_do_salao(db, salao_id)
    usados = len(membros(db, salao_id)) + len(convites_pendentes(db, salao_id))
    limite = plano.max_usuarios if plano else 0
    return {"usados": usados, "limite": limite, "restam": max(0, limite - usados),
            "permite_gerente": bool(plano and plano.permite_gerente)}


def _enviar_email_convite(salao: Salao, email: str, papel: str, token: str) -> None:
    email_sistema(
        email, f"Convite para a equipe do {salao.nome}", f"Você foi convidado para a equipe do {salao.nome}",
        [f"Você foi convidado para entrar no {salao.nome} como {ROTULOS.get(papel, papel).lower()}.",
         "Clique no botão para criar seu acesso. O link é pessoal, vale só para este e-mail e pode ser usado uma única vez.",
         f"Ele expira em {settings.CONVITE_VALIDADE_DIAS} dias. Se você não esperava este convite, ignore a mensagem."],
        botao_texto="Aceitar convite", botao_url=f"/convite/{token}", tipo="CONVITE_EQUIPE",
    )


def convidar(db: Session, salao: Salao, email: str, papel: str, autor: Usuario, request=None) -> ConviteEquipe:
    email_ok = normalizar_email(email)
    if not email_ok:
        raise ErroConvite("Informe um e-mail válido.")
    if papel not in ("GERENTE", "FUNCIONARIO"):
        raise ErroConvite("Função inválida.")
    if autor.role != RoleUsuario.ADMIN and papel not in PODE_CONVIDAR.get(papel_de(autor), []):
        raise ErroConvite("Você não pode convidar alguém com essa função.")

    info = vagas(db, salao.id)
    if papel == "GERENTE" and not info["permite_gerente"]:
        raise ErroConvite("A função Gerente não está disponível no plano atual. Faça upgrade para o Pro.")
    if db.query(Usuario).filter(Usuario.email == email_ok).first():
        raise ErroConvite("Este e-mail já tem uma conta no sistema.")

    existente = next((c for c in convites_pendentes(db, salao.id) if c.email == email_ok), None)
    if not existente and info["restam"] <= 0:
        raise ErroConvite(f"Limite de {info['limite']} pessoas do plano atingido (contando convites pendentes).")

    token = gerar_token_url()
    if existente:  # reenvia o mesmo convite com um link novo (o antigo deixa de valer)
        existente.token_hash = hash_token(token)
        existente.papel = papel
        existente.expira_em = agora() + timedelta(days=settings.CONVITE_VALIDADE_DIAS)
        convite = existente
    else:
        convite = ConviteEquipe(salao_id=salao.id, email=email_ok, papel=papel, token_hash=hash_token(token),
                                criado_por_id=autor.id, expira_em=agora() + timedelta(days=settings.CONVITE_VALIDADE_DIAS))
        db.add(convite)
    db.commit()
    _enviar_email_convite(salao, email_ok, papel, token)
    registrar_evento(db, EventoSeguranca.CONVITE_ENVIADO, request, usuario_id=autor.id, salao_id=salao.id,
                     descricao=f"Convite como {ROTULOS.get(papel)} para {email_ok}")
    return convite


def reenviar(db: Session, convite: ConviteEquipe, autor: Usuario, request=None) -> None:
    convidar(db, convite.salao, convite.email, convite.papel, autor, request)


def convite_pelo_token(db: Session, token: str) -> Optional[ConviteEquipe]:
    c = db.query(ConviteEquipe).filter(ConviteEquipe.token_hash == hash_token(token)).first()
    if not c or c.usado_em or c.cancelado_em or _aware(c.expira_em) <= agora():
        return None
    return c
