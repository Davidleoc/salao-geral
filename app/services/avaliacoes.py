"""
Avaliação do atendimento pelo cliente final.

Quando um atendimento é marcado como CONCLUÍDO e o salão ligou "Pedir avaliação"
(Configurações), o cliente recebe por e-mail um link único para dar uma nota de 1 a 5.
Sem e-mail, a recepção pode copiar o link na ficha do agendamento e mandar pelo WhatsApp.
Notas 4 ou 5 recebem o convite para avaliar também no Google (se o salão cadastrou o link).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.avaliacao_atendimento import AvaliacaoAtendimento
from app.security import gerar_token_url, hash_token
from app.services.email_service import email_do_salao
from app.services.notificacoes import notificar_salao


def criar_link(db: Session, agendamento) -> str:
    """Cria (ou recria) o link de avaliação deste atendimento e devolve a URL relativa."""
    token = gerar_token_url()
    av = db.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.agendamento_id == agendamento.id).first()
    if av and av.respondido_em:
        return ""
    if av:
        av.token_hash = hash_token(token)
    else:
        db.add(AvaliacaoAtendimento(salao_id=agendamento.salao_id, agendamento_id=agendamento.id, token_hash=hash_token(token)))
    db.commit()
    return f"/avaliar/{token}"


def convidar_apos_atendimento(db: Session, agendamento) -> bool:
    salao = agendamento.salao
    cliente = agendamento.cliente
    if not salao.pedir_avaliacao or not cliente or not cliente.email:
        return False
    if db.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.agendamento_id == agendamento.id).first():
        return False
    link = criar_link(db, agendamento)
    email_do_salao(
        salao, cliente.email, f"Como foi seu atendimento no {salao.nome}?", "Como foi seu atendimento?",
        [f"Olá, {cliente.nome.split()[0]}! Obrigado pela visita.",
         f"Leva 10 segundos: dê uma nota para o seu {agendamento.servico.nome}. Sua opinião ajuda muito o {salao.nome}."],
        botao_texto="Avaliar atendimento", botao_url=link, tipo="AVALIACAO_ATENDIMENTO",
    )
    return True


def pelo_token(db: Session, token: str) -> Optional[AvaliacaoAtendimento]:
    return db.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.token_hash == hash_token(token)).first()


def responder(db: Session, av: AvaliacaoAtendimento, nota: int, comentario: str) -> None:
    av.nota = nota
    av.comentario = (comentario or "").strip()[:800] or None
    av.respondido_em = datetime.now(timezone.utc)
    db.commit()
    ag = av.agendamento
    notificar_salao(db, av.salao_id, "avaliacao", f"Nova avaliação: {'★' * nota}{'☆' * (5 - nota)}",
                    f"{ag.cliente.nome} — {ag.servico.nome}" + (f": “{av.comentario[:80]}”" if av.comentario else ""),
                    link="/minhaagenda/avaliacoes", papeis=["DONO", "GERENTE"])
    if ag.profissional_id:
        notificar_salao(db, av.salao_id, "avaliacao", f"Você recebeu {nota} estrela(s)", f"{ag.cliente.nome} — {ag.servico.nome}",
                        usuario_id=ag.profissional_id)
