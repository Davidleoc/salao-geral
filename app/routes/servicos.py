"""
Rotas: Serviços do salão
  GET  /minhaagenda/servicos          → lista serviços
  GET  /minhaagenda/servicos/novo     → formulário novo serviço
  POST /minhaagenda/servicos/novo     → cria serviço
  GET  /minhaagenda/servicos/{id}     → editar serviço
  POST /minhaagenda/servicos/{id}     → salva edição
  POST /minhaagenda/servicos/{id}/toggle → ativa/desativa

Limites por plano:
  Básico  → 10 serviços
  Pro     → 30 serviços
  Premium → ilimitado (None)
"""

from decimal import Decimal
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_compat import templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_usuario_atual
from app.tenant import obter_tenant
from app.models.usuario import Usuario
from app.models.servico import Servico
from app.validacao import converter_dinheiro
from app.services.notificacoes import notificar_salao

router = APIRouter()


@router.get("/minhaagenda/servicos", response_class=HTMLResponse)
def listar_servicos(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    servicos = tenant.query(Servico).order_by(Servico.nome).all()
    total_ativos = sum(1 for s in servicos if s.ativo)

    return templates.TemplateResponse("painel/servicos.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "servicos": servicos,
        "total_ativos": total_ativos,
        "pode_criar": tenant.verificar_limite("max_servicos", total_ativos),
        "active_page": "servicos",
        "mensagem": request.query_params.get("mensagem", ""),
        "erro": request.query_params.get("erro", ""),
    })


@router.get("/minhaagenda/servicos/novo", response_class=HTMLResponse)
def pagina_novo_servico(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    total_ativos = tenant.query(Servico).filter(Servico.ativo == True).count()

    if not tenant.verificar_limite("max_servicos", total_ativos):
        return RedirectResponse(
            "/minhaagenda/servicos?erro=Limite+de+servi%C3%A7os+do+plano+atingido",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse("painel/servico_form.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "servico": None,
        "active_page": "servicos",
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/servicos/novo")
def criar_servico(
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(""),
    preco: str = Form(...),
    custo: str = Form(""),
    duracao_minutos: int = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    total_ativos = tenant.query(Servico).filter(Servico.ativo == True).count()

    if not tenant.verificar_limite("max_servicos", total_ativos):
        return RedirectResponse(
            "/minhaagenda/servicos?erro=Limite+de+servi%C3%A7os+do+plano+atingido",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        preco_decimal = converter_dinheiro(preco)
        custo_decimal = converter_dinheiro(custo, obrigatorio=False)
    except ValueError:
        return RedirectResponse(
            "/minhaagenda/servicos/novo?erro=Pre%C3%A7o+ou+custo+inv%C3%A1lido",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    servico = Servico(
        salao_id=tenant.salao_id,
        nome=nome.strip(),
        descricao=descricao.strip() or None,
        preco=preco_decimal,
        custo=custo_decimal,
        duracao_minutos=duracao_minutos,
        ativo=True,
    )
    db.add(servico)
    db.commit()
    notificar_salao(db, tenant.salao_id, "servico", "Novo serviço cadastrado",
                    f"{servico.nome} — R$ {servico.preco:.2f}".replace(".", ","), link=f"/minhaagenda/servicos/{servico.id}",
                    papeis=["DONO", "GERENTE"], autor_id=usuario.id)

    return RedirectResponse(
        "/minhaagenda/servicos?mensagem=Servi%C3%A7o+criado+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/minhaagenda/servicos/{servico_id}", response_class=HTMLResponse)
def pagina_editar_servico(
    servico_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    servico = tenant.get_or_404(Servico, servico_id)

    return templates.TemplateResponse("painel/servico_form.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "servico": servico,
        "active_page": "servicos",
        "mensagem": request.query_params.get("mensagem", ""),
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/servicos/{servico_id}")
def salvar_servico(
    servico_id: int,
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(""),
    preco: str = Form(...),
    custo: str = Form(""),
    duracao_minutos: int = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    servico = tenant.get_or_404(Servico, servico_id)

    try:
        preco_decimal = converter_dinheiro(preco)
        custo_decimal = converter_dinheiro(custo, obrigatorio=False)
    except ValueError:
        return RedirectResponse(
            f"/minhaagenda/servicos/{servico_id}?erro=Pre%C3%A7o+ou+custo+inv%C3%A1lido",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    servico.nome = nome.strip()
    servico.descricao = descricao.strip() or None
    servico.preco = preco_decimal
    servico.custo = custo_decimal
    servico.duracao_minutos = duracao_minutos
    db.commit()

    return RedirectResponse(
        f"/minhaagenda/servicos/{servico_id}?mensagem=Servi%C3%A7o+atualizado",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/minhaagenda/servicos/{servico_id}/toggle")
def toggle_servico(
    servico_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")
    servico = tenant.get_or_404(Servico, servico_id)
    servico.ativo = not servico.ativo
    db.commit()

    estado = "ativado" if servico.ativo else "desativado"
    return RedirectResponse(
        f"/minhaagenda/servicos?mensagem=Servi%C3%A7o+{estado}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
