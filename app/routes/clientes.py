"""
Rotas: Clientes do salão
  GET  /minhaagenda/clientes         → lista clientes
  GET  /minhaagenda/clientes/novo    → formulário novo cliente
  POST /minhaagenda/clientes/novo    → cria cliente
  GET  /minhaagenda/clientes/{id}    → ficha do cliente
  POST /minhaagenda/clientes/{id}    → edita cliente
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_compat import templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_usuario_atual
from app.tenant import obter_tenant
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.pacote import PacoteCliente
from datetime import date
from app.validacao import normalizar_email, normalizar_telefone

router = APIRouter()

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


@router.get("/minhaagenda/clientes", response_class=HTMLResponse)
def listar_clientes(
    request: Request,
    busca: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.ver")
    q = tenant.query(Cliente).filter(Cliente.ativo == True)

    if busca:
        q = q.filter(
            Cliente.nome.ilike(f"%{busca}%") | Cliente.telefone.ilike(f"%{busca}%")
        )

    clientes = q.order_by(Cliente.nome).all()

    return templates.TemplateResponse("painel/clientes.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "clientes": clientes,
        "busca": busca,
        "active_page": "clientes",
        "mensagem": request.query_params.get("mensagem", ""),
    })


@router.get("/minhaagenda/clientes/novo", response_class=HTMLResponse)
def pagina_novo_cliente(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.editar")
    return templates.TemplateResponse("painel/cliente_form.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "cliente": None,
        "active_page": "clientes",
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/clientes/novo")
def criar_cliente(
    nome: str = Form(...),
    telefone: str = Form(...),
    email: str = Form(""),
    observacoes: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.editar")
    telefone_ok = normalizar_telefone(telefone)
    email_ok = normalizar_email(email) if email.strip() else None
    if not telefone_ok or (email.strip() and not email_ok):
        return RedirectResponse(
            "/minhaagenda/clientes/novo?erro=" + quote("Telefone ou e-mail inválido."),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    cliente = Cliente(
        salao_id=tenant.salao_id,
        nome=nome.strip(),
        telefone=telefone_ok,
        email=email_ok,
        observacoes=observacoes.strip() or None,
    )
    db.add(cliente)
    db.commit()
    return RedirectResponse(
        f"/minhaagenda/clientes/{cliente.id}?mensagem=Cliente+criado+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/minhaagenda/clientes/{cliente_id}", response_class=HTMLResponse)
def ficha_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.ver")
    cliente = tenant.get_or_404(Cliente, cliente_id)

    # Histórico de agendamentos deste cliente (respeitando limite do plano)
    historico = tenant.query(Agendamento).filter(
        Agendamento.cliente_id == cliente_id
    ).order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc()).limit(50).all()

    total_agendamentos = tenant.query(Agendamento).filter(
        Agendamento.cliente_id == cliente_id
    ).count()

    recorrente = total_agendamentos >= 3

    return templates.TemplateResponse("painel/cliente_ficha.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "cliente": cliente,
        "historico": historico,
        "total_agendamentos": total_agendamentos,
        "recorrente": recorrente,
        "pacotes_cliente": tenant.query(PacoteCliente).filter(
            PacoteCliente.cliente_id == cliente_id, PacoteCliente.status == "ATIVO",
            PacoteCliente.validade >= date.today()).order_by(PacoteCliente.validade).all(),
        "meses": MESES,
        "active_page": "clientes",
        "mensagem": request.query_params.get("mensagem", ""),
    })


@router.get("/minhaagenda/clientes/{cliente_id}/editar", response_class=HTMLResponse)
def pagina_editar_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.editar")
    cliente = tenant.get_or_404(Cliente, cliente_id)
    return templates.TemplateResponse("painel/cliente_form.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "cliente": cliente,
        "active_page": "clientes",
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/clientes/{cliente_id}")
def editar_cliente(
    cliente_id: int,
    nome: str = Form(...),
    telefone: str = Form(...),
    email: str = Form(""),
    observacoes: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("clientes.editar")
    cliente = tenant.get_or_404(Cliente, cliente_id)

    telefone_ok = normalizar_telefone(telefone)
    email_ok = normalizar_email(email) if email.strip() else None
    if not telefone_ok or (email.strip() and not email_ok):
        return RedirectResponse(
            f"/minhaagenda/clientes/{cliente_id}/editar?erro=" + quote("Telefone ou e-mail inválido."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    cliente.nome = nome.strip()
    cliente.telefone = telefone_ok
    cliente.email = email_ok
    cliente.observacoes = observacoes.strip() or None
    db.commit()

    return RedirectResponse(
        f"/minhaagenda/clientes/{cliente_id}?mensagem=Cliente+atualizado",
        status_code=status.HTTP_303_SEE_OTHER,
    )
