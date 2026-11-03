"""
Rotas de TESTE — só existem quando APP_ENV != "production" (ver app/main.py).

  GET  /dev                              → painel de testes: endpoints, logins, salões e ações
  POST /dev/login/{usuario_id}           → entra direto como um usuário (sem senha)
  POST /dev/tarefas                      → roda as tarefas automáticas agora (lembretes, cobrança, LGPD…)
  POST /dev/saloes/{salao_id}/ativar     → simula o pagamento confirmado (assinatura ATIVA)
  POST /dev/saloes/{salao_id}/suspender  → suspende a assinatura e desativa o salão
  POST /dev/saloes/{salao_id}/dados-exemplo → cria serviços com custo e atendimentos concluídos
  GET  /dev/emails                       → caixa de saída: e-mails que o sistema "enviou"
  GET  /dev/emails/{notificacao_id}      → visualiza o HTML de um e-mail registrado

Nunca habilite em produção: /dev/login entra em qualquer conta sem senha.
"""

import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.agendamento import Agendamento, StatusAgendamento, FormaPagamento
from app.models.assinatura import Assinatura, StatusAssinatura, Periodicidade
from app.models.cliente import Cliente
from app.models.notificacao import Notificacao
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.usuario import Usuario, RoleUsuario
from app.security import criar_token_acesso
from app.services.email_service import caixa_saida_dev
from app.templates_compat import templates

router = APIRouter(prefix="/dev", include_in_schema=True, tags=["Testes (somente desenvolvimento)"])


def _voltar(msg: str, ancora: str = "") -> RedirectResponse:
    return RedirectResponse(f"/dev?mensagem={quote(msg)}{ancora}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
def painel_testes(request: Request, db: Session = Depends(get_db)):
    saloes = db.query(Salao).order_by(Salao.id).all()
    assinaturas = {a.salao_id: a for a in db.query(Assinatura).all()}
    usuarios = db.query(Usuario).order_by(Usuario.role, Usuario.id).all()
    return templates.TemplateResponse("dev/index.html", {
        "request": request,
        "saloes": saloes,
        "assinaturas": assinaturas,
        "usuarios": usuarios,
        "total_emails": db.query(Notificacao).count() + len(caixa_saida_dev),
        "mensagem": request.query_params.get("mensagem", ""),
        "app_env": settings.APP_ENV,
    })


@router.post("/login/{usuario_id}")
def entrar_como(usuario_id: int, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.ativo == True).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    token = criar_token_acesso(usuario.id, usuario.salao_id, usuario.role.value, usuario.senha_hash)
    destino = "/admin" if usuario.role == RoleUsuario.ADMIN else "/minhaagenda/dashboard"
    resp = RedirectResponse(destino, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=settings.SESSION_EXPIRE_MINUTES * 60)
    return resp


@router.post("/tarefas")
def rodar_tarefas(db: Session = Depends(get_db)):
    """Roda agora lembretes, cobrança, lista de espera e retenção LGPD (normalmente a cada 10 min)."""
    from app.services.tarefas import executar_tarefas
    resultado = executar_tarefas(db)
    return _voltar("Tarefas executadas: " + ", ".join(f"{k}={v}" for k, v in resultado.items()))


@router.post("/saloes/{salao_id}/ativar")
def ativar_salao(salao_id: int, db: Session = Depends(get_db)):
    salao = db.query(Salao).filter(Salao.id == salao_id).first()
    assinatura = db.query(Assinatura).filter(Assinatura.salao_id == salao_id).first()
    if not salao or not assinatura:
        raise HTTPException(status_code=404, detail="Salão ou assinatura não encontrados.")
    hoje = date.today()
    assinatura.status = StatusAssinatura.ATIVO
    assinatura.data_pagamento = datetime.now(timezone.utc)
    assinatura.data_inicio = assinatura.data_inicio or hoje
    assinatura.data_fim = hoje + timedelta(days=365 if assinatura.periodicidade == Periodicidade.ANUAL else 30)
    salao.ativo = True
    db.commit()
    return _voltar(f"Pagamento simulado: {salao.nome} está ATIVO.", "#saloes")


@router.post("/saloes/{salao_id}/suspender")
def suspender_salao(salao_id: int, db: Session = Depends(get_db)):
    salao = db.query(Salao).filter(Salao.id == salao_id).first()
    assinatura = db.query(Assinatura).filter(Assinatura.salao_id == salao_id).first()
    if not salao or not assinatura:
        raise HTTPException(status_code=404, detail="Salão ou assinatura não encontrados.")
    assinatura.status = StatusAssinatura.SUSPENSO
    salao.ativo = False
    db.commit()
    return _voltar(f"{salao.nome} foi suspenso.", "#saloes")


@router.post("/saloes/{salao_id}/dados-exemplo")
def criar_dados_exemplo(salao_id: int, db: Session = Depends(get_db)):
    """Cria serviços com custo, clientes e ~40 atendimentos nos últimos 60 dias para testar os relatórios."""
    salao = db.query(Salao).filter(Salao.id == salao_id).first()
    if not salao:
        raise HTTPException(status_code=404, detail="Salão não encontrado.")

    modelos = [
        ("Corte Feminino", Decimal("90.00"), Decimal("18.00"), 60),
        ("Coloração", Decimal("180.00"), Decimal("55.00"), 120),
        ("Manicure", Decimal("40.00"), Decimal("8.00"), 45),
        ("Barba", Decimal("35.00"), Decimal("5.00"), 30),
    ]
    servicos = []
    for nome, preco, custo, duracao in modelos:
        srv = db.query(Servico).filter(Servico.salao_id == salao.id, Servico.nome == nome).first()
        if not srv:
            srv = Servico(salao_id=salao.id, nome=nome, preco=preco, custo=custo, duracao_minutos=duracao, ativo=True)
            db.add(srv)
        elif srv.custo is None:
            srv.custo = custo
        servicos.append(srv)
    for srv in db.query(Servico).filter(Servico.salao_id == salao.id, Servico.custo == None).all():  # noqa: E711
        srv.custo = (srv.preco * Decimal("0.25")).quantize(Decimal("0.01"))
    db.flush()

    nomes = ["Ana Souza", "Bruno Lima", "Carla Dias", "Daniel Rocha", "Eduarda Melo", "Felipe Costa"]
    clientes = []
    for i, nome in enumerate(nomes):
        tel = f"(11) 9{8000 + i:04d}-{1000 + i:04d}"
        cli = db.query(Cliente).filter(Cliente.salao_id == salao.id, Cliente.telefone == tel).first()
        if not cli:
            cli = Cliente(salao_id=salao.id, nome=nome, telefone=tel, email=f"{nome.split()[0].lower()}@exemplo.com")
            db.add(cli)
        clientes.append(cli)
    db.flush()

    rnd = random.Random()
    criados = 0
    status_opcoes = [StatusAgendamento.CONCLUIDO] * 7 + [StatusAgendamento.CANCELADO_PELO_CLIENTE, StatusAgendamento.NAO_COMPARECEU]
    for _ in range(40):
        srv = rnd.choice(servicos)
        dia = date.today() - timedelta(days=rnd.randint(1, 60))
        inicio = time(rnd.randint(8, 18), rnd.choice([0, 30]))
        ocupado = db.query(Agendamento).filter(
            Agendamento.salao_id == salao.id, Agendamento.data == dia, Agendamento.hora_inicio == inicio
        ).first()
        if ocupado:
            continue
        fim = (datetime.combine(dia, inicio) + timedelta(minutes=srv.duracao_minutos)).time()
        db.add(Agendamento(
            salao_id=salao.id, cliente_id=rnd.choice(clientes).id, servico_id=srv.id,
            data=dia, hora_inicio=inicio, hora_fim=fim, valor=srv.preco, custo=srv.custo,
            forma_pagamento=rnd.choice(list(FormaPagamento)), status=rnd.choice(status_opcoes),
        ))
        criados += 1
    db.commit()
    return _voltar(f"{criados} atendimentos de exemplo criados em {salao.nome}. Veja em Relatórios.", "#saloes")


@router.get("/emails", response_class=HTMLResponse)
def caixa_de_saida(request: Request, db: Session = Depends(get_db)):
    registrados = db.query(Notificacao).order_by(Notificacao.id.desc()).limit(50).all()
    return templates.TemplateResponse("dev/emails.html", {
        "request": request,
        "registrados": registrados,
        "memoria": list(reversed(caixa_saida_dev)),
    })


@router.get("/emails/memoria/{indice}", response_class=HTMLResponse)
def ver_email_memoria(indice: int):
    itens = list(reversed(caixa_saida_dev))
    if indice < 0 or indice >= len(itens):
        raise HTTPException(status_code=404)
    return HTMLResponse(itens[indice]["corpo"])


@router.get("/emails/{notificacao_id}", response_class=HTMLResponse)
def ver_email(notificacao_id: int, db: Session = Depends(get_db)):
    n = db.query(Notificacao).filter(Notificacao.id == notificacao_id).first()
    if not n:
        raise HTTPException(status_code=404)
    return HTMLResponse(n.corpo)
