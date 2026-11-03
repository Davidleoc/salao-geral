"""
Lista de espera: cliente pede um horário num dia lotado; quando um agendamento
desse dia é cancelado, o PRIMEIRO da fila (ordem de chegada) é avisado.

Aviso: e-mail (se a pessoa deixou) + notificação na tela do salão com o WhatsApp
dela, para a recepção chamar. Cada cancelamento avisa só uma pessoa.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lista_espera import ListaEspera
from app.services.email_service import email_do_salao
from app.services.notificacoes import notificar_salao

MAX_POR_TELEFONE_NO_DIA = 1


def adicionar(db: Session, salao, servico, data: date, nome: str, telefone: str, email: Optional[str],
              profissional_id: Optional[int]) -> ListaEspera:
    ja = db.query(ListaEspera).filter(
        ListaEspera.salao_id == salao.id, ListaEspera.data == data, ListaEspera.telefone == telefone,
        ListaEspera.status.in_(["AGUARDANDO", "AVISADO"]),
    ).count()
    if ja >= MAX_POR_TELEFONE_NO_DIA:
        raise ValueError("Você já está na lista de espera deste dia.")
    item = ListaEspera(salao_id=salao.id, servico_id=servico.id, data=data, nome=nome, telefone=telefone,
                       email=email, profissional_id=profissional_id)
    db.add(item)
    db.commit()
    posicao = db.query(ListaEspera).filter(ListaEspera.salao_id == salao.id, ListaEspera.data == data,
                                           ListaEspera.status == "AGUARDANDO", ListaEspera.id <= item.id).count()
    notificar_salao(db, salao.id, "lista_espera", "Novo pedido na lista de espera",
                    f"{nome} — {servico.nome} em {data:%d/%m} ({posicao}º da fila)", link="/minhaagenda/lista-espera",
                    papeis=["DONO", "GERENTE"])
    return item


def avisar_proximo(db: Session, agendamento) -> Optional[ListaEspera]:
    """Chamado quando um agendamento é cancelado. Avisa o primeiro da fila daquele dia."""
    if agendamento.data < date.today():
        return None
    q = db.query(ListaEspera).filter(
        ListaEspera.salao_id == agendamento.salao_id, ListaEspera.data == agendamento.data,
        ListaEspera.status == "AGUARDANDO",
    )
    if agendamento.profissional_id:
        q = q.filter((ListaEspera.profissional_id.is_(None)) | (ListaEspera.profissional_id == agendamento.profissional_id))
    proximo = q.order_by(ListaEspera.criado_em, ListaEspera.id).first()
    if not proximo:
        return None
    proximo.status = "AVISADO"
    proximo.avisado_em = datetime.now(timezone.utc)
    db.commit()

    salao = agendamento.salao
    horario = agendamento.hora_inicio.strftime("%H:%M")
    if proximo.email:
        email_do_salao(
            salao, proximo.email, f"Abriu um horário no {salao.nome}!", "Abriu um horário para você",
            [f"Olá, {proximo.nome.split()[0]}! Você está na lista de espera do {salao.nome}.",
             f"Acabou de abrir um horário em {agendamento.data:%d/%m/%Y} às {horario}.",
             "Os horários são de quem agendar primeiro — garanta o seu:"],
            botao_texto="Agendar agora", botao_url=f"/{salao.slug}/agendar/{proximo.servico_id}", tipo="LISTA_ESPERA",
        )
    notificar_salao(db, salao.id, "lista_espera", "Vaga aberta — avise o cliente da lista",
                    f"{proximo.nome} ({proximo.telefone}) quer {proximo.servico.nome} em {agendamento.data:%d/%m}. Abriu às {horario}.",
                    link="/minhaagenda/lista-espera", papeis=["DONO", "GERENTE"])
    return proximo


def tarefa_expirar(db: Session) -> int:
    """Pedidos de dias que já passaram saem da fila."""
    n = (db.query(ListaEspera)
         .filter(ListaEspera.data < date.today(), ListaEspera.status.in_(["AGUARDANDO", "AVISADO"]))
         .update({ListaEspera.status: "EXPIRADO"}, synchronize_session=False))
    db.commit()
    return n
