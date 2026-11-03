"""
Rotas: Pacotes, lista de espera, avaliações do atendimento e calendário (Google Agenda).

Painel
  GET  /minhaagenda/pacotes                         → catálogo + pacotes vendidos ativos
  POST /minhaagenda/pacotes                         → cria pacote/assinatura do cliente
  POST /minhaagenda/pacotes/{id}/ativo              → liga/desliga um pacote do catálogo
  POST /minhaagenda/pacotes/vender                  → registra a venda para um cliente
  POST /minhaagenda/pacotes/vendidos/{id}/renovar   → assinatura: abre o próximo ciclo
  POST /minhaagenda/pacotes/vendidos/{id}/cancelar  → encerra um pacote vendido
  GET  /minhaagenda/lista-espera                    → fila por dia
  POST /minhaagenda/lista-espera/{id}/status        → agendado / removido
  GET  /minhaagenda/avaliacoes                      → notas dos clientes + configuração (dono/gerente)
  POST /minhaagenda/avaliacoes/config               → ligar pedido de avaliação e link do Google

Público
  POST /{slug}/lista-espera                         → cliente entra na fila de um dia lotado
  GET  /avaliar/{token}  ·  POST /avaliar/{token}   → cliente avalia o atendimento (link único)
  GET  /calendario/{token}.ics                      → agenda no Google Agenda / celular (plano Pro+)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.assinatura import Assinatura
from app.models.avaliacao_atendimento import AvaliacaoAtendimento
from app.models.cliente import Cliente
from app.models.lista_espera import ListaEspera
from app.models.log_seguranca import EventoSeguranca
from app.models.pacote import Pacote, PacoteCliente
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.usuario import Usuario
from app.permissoes import pode
from app.services import avaliacoes as svc_avaliacoes
from app.services import lista_espera as svc_espera
from app.services import pacotes as svc_pacotes
from app.services.auditoria import registrar_evento
from app.services.cobranca import STATUS_COM_ACESSO
from app.services.limite_taxa import verificar_limite
from app.templates_compat import templates
from app.tenant import obter_tenant
from app.validacao import converter_dinheiro, nome_pessoa_valido, normalizar_email, normalizar_telefone

router = APIRouter()

FORMAS = {"PIX": "Pix", "DINHEIRO": "Dinheiro", "CREDITO": "Cartão de crédito", "DEBITO": "Cartão de débito"}


def _ir(url: str, **params) -> RedirectResponse:
    if params:
        url += ("&" if "?" in url else "?") + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _ctx(request, usuario, tenant, pagina, **extra):
    return {"request": request, "usuario": usuario, "salao": tenant.salao, "active_page": pagina,
            "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""), **extra}


# ===========================================================================
# Pacotes e assinaturas do cliente final
# ===========================================================================
@router.get("/minhaagenda/pacotes", response_class=HTMLResponse)
def pagina_pacotes(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    hoje = date.today()
    vendidos = (tenant.query(PacoteCliente).options(joinedload(PacoteCliente.pacote), joinedload(PacoteCliente.cliente))
                .filter(PacoteCliente.status == "ATIVO").order_by(PacoteCliente.validade).all())
    receita_mes = (tenant.query(PacoteCliente).with_entities(func.coalesce(func.sum(PacoteCliente.valor_pago), 0))
                   .filter(PacoteCliente.inicio >= hoje.replace(day=1)).scalar())
    return templates.TemplateResponse("painel/pacotes.html", _ctx(
        request, usuario, tenant, "pacotes",
        pacotes=tenant.query(Pacote).order_by(Pacote.ativo.desc(), Pacote.nome).all(),
        servicos=tenant.query(Servico).filter(Servico.ativo == True).order_by(Servico.nome).all(),  # noqa: E712
        clientes=tenant.query(Cliente).filter(~Cliente.telefone.startswith("anon-")).order_by(Cliente.nome).all(),
        vendidos=vendidos, hoje=hoje, receita_mes=receita_mes, formas=FORMAS,
        cliente_sel=request.query_params.get("cliente", ""),
    ))


@router.post("/minhaagenda/pacotes")
def criar_pacote(request: Request, nome: str = Form(...), descricao: str = Form(""), tipo: str = Form("PACOTE"),
                 servico_id: str = Form(""), quantidade_sessoes: int = Form(...), preco: str = Form(...),
                 validade_dias: int = Form(90), publico: str = Form(""),
                 db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    nome = nome.strip()
    if not (2 <= len(nome) <= 150):
        return _ir("/minhaagenda/pacotes", erro="Dê um nome ao pacote.")
    if tipo not in ("PACOTE", "ASSINATURA"):
        return _ir("/minhaagenda/pacotes", erro="Tipo inválido.")
    if not (1 <= quantidade_sessoes <= 100):
        return _ir("/minhaagenda/pacotes", erro="Quantidade de sessões entre 1 e 100.")
    try:
        valor = converter_dinheiro(preco)
    except ValueError as e:
        return _ir("/minhaagenda/pacotes", erro=f"Preço: {e}")
    servico = tenant.get_or_404(Servico, int(servico_id)) if servico_id.isdigit() else None
    pacote = Pacote(salao_id=tenant.salao_id, nome=nome, descricao=descricao.strip()[:500] or None, tipo=tipo,
                    servico_id=servico.id if servico else None, quantidade_sessoes=quantidade_sessoes, preco=valor,
                    validade_dias=30 if tipo == "ASSINATURA" else max(7, min(validade_dias, 730)),
                    publico=publico == "on")
    db.add(pacote)
    db.commit()
    return _ir("/minhaagenda/pacotes", mensagem=f"{'Assinatura' if tipo == 'ASSINATURA' else 'Pacote'} “{nome}” criado.")


@router.post("/minhaagenda/pacotes/{pacote_id}/ativo")
def alternar_pacote(pacote_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    pacote = tenant.get_or_404(Pacote, pacote_id)
    pacote.ativo = not pacote.ativo
    db.commit()
    return _ir("/minhaagenda/pacotes", mensagem="Pacote reativado." if pacote.ativo else "Pacote desativado (quem já comprou continua usando).")


@router.post("/minhaagenda/pacotes/vender")
def vender_pacote(pacote_id: int = Form(...), cliente_id: int = Form(...), valor: str = Form(""),
                  forma_pagamento: str = Form(""), voltar: str = Form(""),
                  db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    destino = voltar if voltar.startswith("/minhaagenda/") else "/minhaagenda/pacotes"
    pacote = tenant.get_or_404(Pacote, pacote_id)
    cliente = tenant.get_or_404(Cliente, cliente_id)
    if not pacote.ativo:
        return _ir(destino, erro="Este pacote está desativado.")
    try:
        valor_pago = converter_dinheiro(valor, obrigatorio=False)
    except ValueError as e:
        return _ir(destino, erro=f"Valor: {e}")
    svc_pacotes.vender(db, tenant.salao_id, pacote, cliente.id, valor_pago if valor_pago is not None else pacote.preco,
                       forma_pagamento if forma_pagamento in FORMAS else None, usuario.id)
    return _ir(destino, mensagem=f"{pacote.nome} vendido para {cliente.nome}.")


@router.post("/minhaagenda/pacotes/vendidos/{pc_id}/renovar")
def renovar_pacote(pc_id: int, valor: str = Form(""), forma_pagamento: str = Form(""),
                   db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    pc = tenant.get_or_404(PacoteCliente, pc_id)
    try:
        valor_pago = converter_dinheiro(valor, obrigatorio=False)
    except ValueError as e:
        return _ir("/minhaagenda/pacotes", erro=f"Valor: {e}")
    svc_pacotes.renovar_assinatura(db, pc, valor_pago if valor_pago is not None else pc.pacote.preco,
                                   forma_pagamento if forma_pagamento in FORMAS else None, usuario.id)
    return _ir("/minhaagenda/pacotes", mensagem=f"{pc.pacote.nome} de {pc.cliente.nome} renovado por mais um ciclo.")


@router.post("/minhaagenda/pacotes/vendidos/{pc_id}/cancelar")
def cancelar_pacote(pc_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("pacotes.gerenciar")
    pc = tenant.get_or_404(PacoteCliente, pc_id)
    pc.status = "CANCELADO"
    db.commit()
    return _ir("/minhaagenda/pacotes", mensagem="Pacote encerrado.")


# ===========================================================================
# Lista de espera
# ===========================================================================
@router.get("/minhaagenda/lista-espera", response_class=HTMLResponse)
def pagina_lista_espera(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("lista_espera.ver")
    itens = (tenant.query(ListaEspera).options(joinedload(ListaEspera.servico), joinedload(ListaEspera.profissional))
             .filter(ListaEspera.data >= date.today(), ListaEspera.status.in_(["AGUARDANDO", "AVISADO"]))
             .order_by(ListaEspera.data, ListaEspera.criado_em, ListaEspera.id).all())
    por_dia: dict = {}
    for item in itens:
        por_dia.setdefault(item.data, []).append(item)
    return templates.TemplateResponse("painel/lista_espera.html", _ctx(request, usuario, tenant, "lista_espera", por_dia=por_dia))


@router.post("/minhaagenda/lista-espera/{item_id}/status")
def mudar_status_espera(item_id: int, novo_status: str = Form(...), db: Session = Depends(get_db),
                        usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("lista_espera.ver")
    item = tenant.get_or_404(ListaEspera, item_id)
    if novo_status not in ("AGENDADO", "REMOVIDO", "AGUARDANDO"):
        return _ir("/minhaagenda/lista-espera", erro="Status inválido.")
    item.status = novo_status
    db.commit()
    return _ir("/minhaagenda/lista-espera", mensagem="Lista de espera atualizada.")


@router.post("/{slug}/lista-espera")
def entrar_lista_espera(slug: str, request: Request, servico_id: int = Form(...), data: date = Form(...),
                        nome: str = Form(...), telefone: str = Form(...), email: str = Form(""),
                        profissional_id: str = Form(""), db: Session = Depends(get_db)):
    verificar_limite(request, "lista_espera")
    salao = db.query(Salao).filter(Salao.slug == slug, Salao.ativo == True).first()  # noqa: E712
    if not salao:
        raise HTTPException(status_code=404, detail="Salão não encontrado")
    servico = db.query(Servico).filter(Servico.id == servico_id, Servico.salao_id == salao.id, Servico.ativo == True).first()  # noqa: E712
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    voltar = f"/{slug}/agendar/{servico_id}"

    nome = " ".join(nome.split())
    if not nome_pessoa_valido(nome):
        return _ir(voltar, erro="Lista de espera: informe seu nome usando apenas letras.")
    tel = normalizar_telefone(telefone)
    if not tel:
        return _ir(voltar, erro="Lista de espera: WhatsApp inválido.")
    email_ok = None
    if email.strip():
        email_ok = normalizar_email(email)
        if not email_ok:
            return _ir(voltar, erro="Lista de espera: e-mail inválido (ou deixe em branco).")
    if data < date.today() or data > date.today() + timedelta(days=180):
        return _ir(voltar, erro="Lista de espera: escolha uma data válida.")

    prof_id = None
    if profissional_id.isdigit():
        prof = db.query(Usuario).filter(Usuario.id == int(profissional_id), Usuario.salao_id == salao.id,
                                        Usuario.ativo == True).first()  # noqa: E712
        prof_id = prof.id if prof else None
    try:
        svc_espera.adicionar(db, salao, servico, data, nome, tel, email_ok, prof_id)
    except ValueError as e:
        return _ir(voltar, erro=str(e))
    return _ir(voltar, mensagem=f"Pronto! Você está na lista de espera de {data:%d/%m}. Se abrir um horário, avisamos"
                                + (" por e-mail e" if email_ok else "") + " o salão entra em contato pelo WhatsApp.")


# ===========================================================================
# Avaliações do atendimento
# ===========================================================================
@router.get("/minhaagenda/avaliacoes", response_class=HTMLResponse)
def pagina_avaliacoes(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("avaliacoes.ver")
    respondidas = (tenant.query(AvaliacaoAtendimento)
                   .options(joinedload(AvaliacaoAtendimento.agendamento).joinedload(Agendamento.cliente),
                            joinedload(AvaliacaoAtendimento.agendamento).joinedload(Agendamento.servico),
                            joinedload(AvaliacaoAtendimento.agendamento).joinedload(Agendamento.profissional))
                   .filter(AvaliacaoAtendimento.respondido_em.isnot(None))
                   .order_by(AvaliacaoAtendimento.respondido_em.desc()).limit(200).all())
    pendentes = tenant.query(AvaliacaoAtendimento).filter(AvaliacaoAtendimento.respondido_em.is_(None)).count()
    notas = [a.nota for a in respondidas]
    distribuicao = {n: notas.count(n) for n in range(5, 0, -1)}
    por_profissional: dict = {}
    for a in respondidas:
        p = a.agendamento.profissional
        if p:
            por_profissional.setdefault(p.nome, []).append(a.nota)
    return templates.TemplateResponse("painel/avaliacoes.html", _ctx(
        request, usuario, tenant, "avaliacoes", avaliacoes=respondidas, pendentes=pendentes,
        media=(sum(notas) / len(notas)) if notas else None, distribuicao=distribuicao, total=len(notas),
        por_profissional={k: (sum(v) / len(v), len(v)) for k, v in por_profissional.items()},
        pode_configurar=tenant.pode("configuracoes.editar"),
    ))


@router.post("/minhaagenda/avaliacoes/config")
def configurar_avaliacoes(request: Request, pedir_avaliacao: str = Form(""), link_avaliacao_google: str = Form(""),
                          db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    link = link_avaliacao_google.strip()
    if link:
        u = urlparse(link)
        if u.scheme != "https" or not u.netloc or len(link) > 500:
            return _ir("/minhaagenda/avaliacoes", erro="O link do Google precisa começar com https:// (copie do seu Perfil da Empresa no Google).")
    salao = tenant.salao
    salao.pedir_avaliacao = pedir_avaliacao == "on"
    salao.link_avaliacao_google = link or None
    db.commit()
    registrar_evento(db, EventoSeguranca.CONFIGURACAO_ALTERADA, request, usuario_id=usuario.id, salao_id=salao.id,
                     descricao="Configuração de avaliações alterada")
    return _ir("/minhaagenda/avaliacoes", mensagem="Configuração salva.")


def _avaliacao_publica(db: Session, token: str):
    av = svc_avaliacoes.pelo_token(db, token)
    if not av or not av.agendamento or not av.agendamento.salao or not av.agendamento.salao.ativo:
        return None
    return av


@router.get("/avaliar/{token}", response_class=HTMLResponse)
def pagina_avaliar(token: str, request: Request, db: Session = Depends(get_db)):
    av = _avaliacao_publica(db, token)
    if not av:
        return templates.TemplateResponse(request, "erro.html", {"titulo": "Link inválido",
                                          "mensagem": "Este link de avaliação não existe ou expirou."}, status_code=404)
    return templates.TemplateResponse(request, "public/avaliar.html", {
        "salao": av.agendamento.salao, "av": av, "ag": av.agendamento, "token": token,
        "enviado": av.respondido_em is not None,
    })


@router.post("/avaliar/{token}", response_class=HTMLResponse)
def enviar_avaliacao_atendimento(token: str, request: Request, nota: int = Form(...), comentario: str = Form(""),
                                 db: Session = Depends(get_db)):
    verificar_limite(request, "avaliar_atendimento")
    av = _avaliacao_publica(db, token)
    if not av:
        raise HTTPException(status_code=404)
    if not av.respondido_em:
        if not 1 <= nota <= 5:
            return RedirectResponse(f"/avaliar/{token}", status_code=status.HTTP_303_SEE_OTHER)
        svc_avaliacoes.responder(db, av, nota, comentario)
    return RedirectResponse(f"/avaliar/{token}", status_code=status.HTTP_303_SEE_OTHER)


# ===========================================================================
# Calendário (.ics) — Google Agenda, Apple, Outlook
# ===========================================================================
def _ics_texto(valor: str) -> str:
    return (valor or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _dobrar(linha: str) -> str:
    """RFC 5545: linhas de no máximo 75 caracteres (continuação começa com espaço)."""
    partes = [linha[i:i + 73] for i in range(0, len(linha), 73)] or [""]
    return "\r\n ".join(partes)


@router.get("/calendario/{token}.ics")
def calendario_ics(token: str, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.calendario_token == token, Usuario.ativo == True).first() if len(token) >= 20 else None  # noqa: E712
    salao = db.get(Salao, usuario.salao_id) if usuario and usuario.salao_id else None
    assinatura = db.query(Assinatura).filter(Assinatura.salao_id == salao.id).first() if salao else None
    if (not salao or not salao.ativo or not assinatura or assinatura.status not in STATUS_COM_ACESSO
            or not assinatura.plano or not assinatura.plano.sincronizacao_agenda):
        raise HTTPException(status_code=404)

    hoje = date.today()
    q = (db.query(Agendamento).options(joinedload(Agendamento.cliente), joinedload(Agendamento.servico),
                                       joinedload(Agendamento.profissional))
         .filter(Agendamento.salao_id == salao.id, Agendamento.data >= hoje - timedelta(days=30),
                 Agendamento.data <= hoje + timedelta(days=180),
                 Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO, StatusAgendamento.CONCLUIDO])))
    todos = pode(usuario, "agenda.todos")
    if not todos:
        q = q.filter(Agendamento.profissional_id == usuario.id)

    host = urlparse(settings.URL_BASE).netloc or "meuagendamento"
    agora = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    linhas = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{settings.APP_NAME}//Agenda//PT-BR", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", _dobrar(f"X-WR-CALNAME:{_ics_texto(salao.nome + ('' if todos else ' — ' + usuario.nome.split()[0]))}"),
        "X-WR-TIMEZONE:America/Sao_Paulo", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
        # Brasília sem horário de verão desde 2019
        "BEGIN:VTIMEZONE", "TZID:America/Sao_Paulo", "BEGIN:STANDARD", "DTSTART:19700101T000000",
        "TZOFFSETFROM:-0300", "TZOFFSETTO:-0300", "TZNAME:-03", "END:STANDARD", "END:VTIMEZONE",
    ]
    for a in q.order_by(Agendamento.data, Agendamento.hora_inicio).all():
        inicio = datetime.combine(a.data, a.hora_inicio).strftime("%Y%m%dT%H%M%S")
        fim = datetime.combine(a.data, a.hora_fim).strftime("%Y%m%dT%H%M%S")
        cliente = a.cliente.nome.split()[0] if a.cliente and a.cliente.nome else "Cliente"  # só o primeiro nome (LGPD)
        titulo = f"{a.servico.nome if a.servico else 'Atendimento'} — {cliente}"
        detalhes = [f"Cliente: {cliente}"]
        if a.profissional and todos:
            detalhes.append(f"Profissional: {a.profissional.nome}")
        detalhes.append(f"Status: {a.status.value.title()}")
        linhas += [
            "BEGIN:VEVENT", f"UID:ag-{a.id}@{host}", f"DTSTAMP:{agora}",
            f"DTSTART;TZID=America/Sao_Paulo:{inicio}", f"DTEND;TZID=America/Sao_Paulo:{fim}",
            _dobrar(f"SUMMARY:{_ics_texto(titulo)}"), _dobrar(f"DESCRIPTION:{_ics_texto(chr(10).join(detalhes))}"),
            "STATUS:CONFIRMED" if a.status != StatusAgendamento.AGENDADO else "STATUS:TENTATIVE",
            "END:VEVENT",
        ]
    linhas.append("END:VCALENDAR")
    return Response("\r\n".join(linhas) + "\r\n", media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=900"})
