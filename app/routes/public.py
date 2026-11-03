"""
Rotas: página pública do salão e agendamento pelo cliente final.

  GET  /{slug}                                → página do salão (serviços, sobre, equipe, pacotes)
  GET  /{slug}/agendar/{servico}              → escolher profissional, dia e horário
  GET  /api/public/{slug}/disponibilidade     → horários livres (JSON) — ?servico_id&data&profissional_id
  POST /{slug}/agendar/{servico}              → confirmar o agendamento
  GET  /{slug}/sucesso?c=<código assinado>    → confirmação (o código impede ver agendamentos alheios)

Proteções: limite por IP, no máximo 3 agendamentos futuros por telefone em cada salão,
não aceita datas passadas, confere de novo se o horário está livre na hora de gravar.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.agendamento import Agendamento, FormaPagamento, StatusAgendamento
from app.models.assinatura import Assinatura
from app.models.cliente import Cliente
from app.models.foto_salao import FotoSalao
from app.models.pacote import Pacote
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.usuario import Usuario
from app.services.disponibilidade_service import horarios_livres, profissionais_que_atendem
from app.services.limite_taxa import verificar_limite
from app.services.notificacoes import notificar_salao
from app.templates_compat import templates
from app.validacao import nome_pessoa_valido, normalizar_email, normalizar_telefone

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_AGENDAMENTOS_FUTUROS_POR_TELEFONE = 3
DIAS_MAXIMOS_A_FRENTE = 180
_assinador = URLSafeSerializer(settings.SECRET_KEY, salt="agendamento-sucesso")


def get_salao_by_slug(slug: str, db: Session) -> Salao:
    salao = db.query(Salao).filter(Salao.slug == slug, Salao.ativo == True).first()  # noqa: E712
    if not salao:
        raise HTTPException(status_code=404, detail="Salão não encontrado ou inativo")
    return salao


def _servico(db: Session, salao: Salao, servico_id: int) -> Servico:
    servico = db.query(Servico).filter(Servico.id == servico_id, Servico.salao_id == salao.id, Servico.ativo == True).first()  # noqa: E712
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return servico


def _profissional(db: Session, salao: Salao, profissional_id: Optional[str]) -> Optional[Usuario]:
    """'' ou 'qualquer' = sem preferência. Senão, precisa ser alguém deste salão que atende clientes."""
    if not profissional_id or not str(profissional_id).isdigit():
        return None
    return next((p for p in profissionais_que_atendem(db, salao.id) if p.id == int(profissional_id)), None)


# ---------------------------------------------------------------------------
# Página do salão
# ---------------------------------------------------------------------------
@router.get("/{slug}", response_class=HTMLResponse)
def pagina_publica_salao(slug: str, request: Request, db: Session = Depends(get_db)):
    salao = get_salao_by_slug(slug, db)
    servicos = db.query(Servico).filter(Servico.salao_id == salao.id, Servico.ativo == True).order_by(Servico.nome).all()  # noqa: E712
    assinatura = db.query(Assinatura).filter(Assinatura.salao_id == salao.id).first()
    max_fotos = assinatura.plano.max_fotos if assinatura and assinatura.plano else 0
    fotos = (db.query(FotoSalao).filter(FotoSalao.salao_id == salao.id)
             .order_by(FotoSalao.ordem, FotoSalao.id).limit(max_fotos).all()) if max_fotos else []
    pacotes = (db.query(Pacote).filter(Pacote.salao_id == salao.id, Pacote.ativo == True, Pacote.publico == True)  # noqa: E712
               .order_by(Pacote.preco).all())
    return templates.TemplateResponse(request, "public/salao.html", {
        "salao": salao, "servicos": servicos, "fotos": fotos, "pacotes": pacotes,
        "equipe": profissionais_que_atendem(db, salao.id),
    })


# ---------------------------------------------------------------------------
# Agendamento
# ---------------------------------------------------------------------------
@router.get("/{slug}/agendar/{servico_id}", response_class=HTMLResponse)
def escolher_data_horario(slug: str, servico_id: int, request: Request, db: Session = Depends(get_db)):
    salao = get_salao_by_slug(slug, db)
    servico = _servico(db, salao, servico_id)
    hoje = date.today()
    return templates.TemplateResponse(request, "public/agendar.html", {
        "salao": salao, "servico": servico, "hoje": hoje, "limite": hoje + timedelta(days=DIAS_MAXIMOS_A_FRENTE),
        "profissionais": profissionais_que_atendem(db, salao.id),
        "erro": request.query_params.get("erro"), "mensagem": request.query_params.get("mensagem"),
    })


@router.get("/api/public/{slug}/disponibilidade")
def api_disponibilidade(slug: str, servico_id: int, data: date, request: Request,
                        profissional_id: str = "", db: Session = Depends(get_db)):
    verificar_limite(request, "disponibilidade")
    salao = get_salao_by_slug(slug, db)
    servico = db.query(Servico).filter(Servico.id == servico_id, Servico.salao_id == salao.id, Servico.ativo == True).first()  # noqa: E712
    if not servico:
        return JSONResponse({"erro": "Serviço inválido"}, status_code=404)
    hoje = date.today()
    if data < hoje or data > hoje + timedelta(days=DIAS_MAXIMOS_A_FRENTE):
        return {"horarios": []}
    prof = _profissional(db, salao, profissional_id)
    if profissional_id and profissional_id != "qualquer" and not prof:
        return JSONResponse({"erro": "Profissional inválido"}, status_code=404)
    livres = horarios_livres(db, salao.id, data, servico, prof.id if prof else None)
    if data == hoje:
        agora = datetime.now().time()
        livres = [(h, p) for h, p in livres if h > agora]
    return {"horarios": [h.strftime("%H:%M") for h, _ in livres]}


@router.post("/{slug}/agendar/{servico_id}")
def confirmar_agendamento(
    slug: str, servico_id: int, request: Request,
    data: date = Form(...), hora: str = Form(...), nome: str = Form(...), telefone: str = Form(...),
    email: Optional[str] = Form(None), forma_pagamento: str = Form(...), observacoes: Optional[str] = Form(None),
    profissional_id: str = Form(""), db: Session = Depends(get_db),
):
    verificar_limite(request, "agendar")
    salao = get_salao_by_slug(slug, db)
    servico = _servico(db, salao, servico_id)

    def erro(msg: str):
        return RedirectResponse(f"/{slug}/agendar/{servico_id}?erro={quote(msg)}", status_code=status.HTTP_303_SEE_OTHER)

    # Validação dos dados (o JS da página é só conforto)
    nome = " ".join(nome.split())
    if not nome_pessoa_valido(nome):
        return erro("Informe seu nome usando apenas letras.")
    telefone_ok = normalizar_telefone(telefone)
    if not telefone_ok:
        return erro("WhatsApp inválido. Digite o DDD e o número, apenas números.")
    email_ok = None
    if email and email.strip():
        email_ok = normalizar_email(email)
        if not email_ok:
            return erro("E-mail inválido. Confira o endereço ou deixe o campo em branco.")
    try:
        forma = FormaPagamento(forma_pagamento)
        hora_obj = datetime.strptime(hora, "%H:%M").time()
    except ValueError:
        return erro("Selecione o horário e a forma de pagamento.")
    hoje = date.today()
    if data < hoje or (data == hoje and hora_obj <= datetime.now().time()):
        return erro("Escolha um horário que ainda não passou.")
    if data > hoje + timedelta(days=DIAS_MAXIMOS_A_FRENTE):
        return erro("Escolha uma data mais próxima.")

    prof = _profissional(db, salao, profissional_id)
    if profissional_id and profissional_id != "qualquer" and not prof:
        return erro("Profissional indisponível. Escolha outro.")

    # O horário precisa estar livre AGORA (e define quem atende, se o cliente não escolheu)
    livres = dict(horarios_livres(db, salao.id, data, servico, prof.id if prof else None))
    if hora_obj not in livres:
        return erro("Desculpe, este horário acabou de ser ocupado. Escolha outro.")
    profissional_final_id = livres[hora_obj]

    # Cliente (mesmo telefone = mesmo cliente)
    cliente = db.query(Cliente).filter(Cliente.salao_id == salao.id, Cliente.telefone.in_([telefone_ok, telefone.strip()])).first()
    if cliente:
        futuros = db.query(Agendamento).filter(
            Agendamento.salao_id == salao.id, Agendamento.cliente_id == cliente.id, Agendamento.data >= hoje,
            Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO]),
        ).count()
        if futuros >= MAX_AGENDAMENTOS_FUTUROS_POR_TELEFONE:
            return erro("Este telefone já tem vários horários marcados. Para agendar mais, fale com o salão.")
        if email_ok:
            cliente.email = email_ok
    else:
        cliente = Cliente(salao_id=salao.id, nome=nome, telefone=telefone_ok, email=email_ok)
        db.add(cliente)
        db.flush()

    profissional = db.get(Usuario, profissional_final_id) if profissional_final_id else None
    agendamento = Agendamento(
        salao_id=salao.id, cliente_id=cliente.id, servico_id=servico.id, profissional_id=profissional_final_id,
        data=data, hora_inicio=hora_obj,
        hora_fim=(datetime.combine(data, hora_obj) + timedelta(minutes=servico.duracao_minutos)).time(),
        valor=servico.preco, custo=servico.custo,
        comissao_percentual=profissional.comissao_percentual if profissional else None,
        forma_pagamento=forma, status=StatusAgendamento.AGENDADO,
        observacoes=observacoes.strip()[:1000] if observacoes and observacoes.strip() else None,
    )
    db.add(agendamento)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return erro("Este horário acabou de ser ocupado. Escolha outro.")

    texto = f"{cliente.nome} — {servico.nome}, {data:%d/%m} às {hora_obj:%H:%M}"
    notificar_salao(db, salao.id, "agendamento", "Novo agendamento online", texto,
                    link=f"/minhaagenda/agenda/{agendamento.id}", papeis=["DONO", "GERENTE"], commit=False)
    if profissional_final_id:
        notificar_salao(db, salao.id, "agendamento", "Novo cliente na sua agenda", texto,
                        link=f"/minhaagenda/agenda/{agendamento.id}", usuario_id=profissional_final_id, commit=False)
    db.commit()

    try:
        from app.services.email_service import enviar_confirmacao_agendamento, enviar_novo_agendamento_salao
        enviar_confirmacao_agendamento(db, agendamento)
        enviar_novo_agendamento_salao(db, agendamento)
    except Exception:
        logger.exception("Erro ao disparar e-mails do agendamento %s", agendamento.id)

    return RedirectResponse(f"/{slug}/sucesso?c={_assinador.dumps(agendamento.id)}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{slug}/sucesso", response_class=HTMLResponse)
def agendamento_sucesso(slug: str, request: Request, c: str = "", db: Session = Depends(get_db)):
    salao = get_salao_by_slug(slug, db)
    try:
        agendamento_id = int(_assinador.loads(c))
    except (BadSignature, TypeError, ValueError):
        raise HTTPException(status_code=404)
    agendamento = db.query(Agendamento).filter(Agendamento.id == agendamento_id, Agendamento.salao_id == salao.id).first()
    if not agendamento:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "public/sucesso.html", {"salao": salao, "agendamento": agendamento})
