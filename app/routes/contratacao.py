"""
Rotas: Contratação Pública — Fluxo de Auto-Cadastro de Salões.

SEM autenticação (público):
  GET  /contratar                → Página de apresentação, planos e avaliações
  POST /contratar/avaliar        → Avaliação de um contratante (cliente ativo ou ex-cliente)
  GET  /contratar/sucesso        → "Confirme seu e-mail" (o teste grátis começa na confirmação)
  GET  /contratar/{plano_id}     → Formulário de contratação
  POST /contratar/{plano_id}     → Cria Salao + Usuario (DONO, e-mail a confirmar) + Assinatura (TESTE;
                                   AGUARDANDO_PAGAMENTO se o CPF/CNPJ já foi usado em outra conta)
  GET  /termos                   → Termos de Uso e Política de Privacidade (LGPD)

Atenção à ordem: rotas fixas (/contratar/sucesso, /contratar/avaliar) vêm antes de
/contratar/{plano_id}, e plano_id usa o conversor :int para não capturar texto.
"""

import re
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_compat import templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.plano import Plano
from app.models.salao import Salao
from app.models.usuario import Usuario, RoleUsuario
from app.models.assinatura import Assinatura, StatusAssinatura, Periodicidade
from app.models.avaliacao import Avaliacao
from app.paletas import PALETAS
from app.deps import obter_usuario_opcional
from app.security import hash_senha
from app.validacao import (
    SLUGS_RESERVADOS, normalizar_email, normalizar_telefone,
    nome_pessoa_valido, senha_forte, normalizar_documento,
)
from app.config import settings
from app.services import cobranca
from app.services.contas import enviar_email_verificacao
from app.services.limite_taxa import verificar_limite
from app.services.notificacoes import notificar_admin

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_COMENTARIO = 800

_assinador_sucesso = URLSafeTimedSerializer(settings.SECRET_KEY, salt="contratacao-sucesso")


def _gerar_slug(nome: str) -> str:
    """Converte nome do salão em slug URL-safe."""
    slug = nome.lower().strip()
    slug = re.sub(r"[àáâãäå]", "a", slug)
    slug = re.sub(r"[èéêë]", "e", slug)
    slug = re.sub(r"[ìíîï]", "i", slug)
    slug = re.sub(r"[òóôõö]", "o", slug)
    slug = re.sub(r"[ùúûü]", "u", slug)
    slug = re.sub(r"[ç]", "c", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:100]


def _ja_foi_cliente(assinatura: Assinatura | None) -> bool:
    """Cliente ativo ou que já pagou alguma vez (suspenso/cancelado depois de ativo)."""
    if not assinatura:
        return False
    if assinatura.status in (StatusAssinatura.ATIVO, StatusAssinatura.PAGO):
        return True
    return assinatura.data_pagamento is not None


# ---------------------------------------------------------------------------
# GET /contratar — landing page
# ---------------------------------------------------------------------------
@router.get("/contratar", response_class=HTMLResponse)
def pagina_planos(
    request: Request,
    db: Session = Depends(get_db),
):
    """Página pública de apresentação — recursos, planos e avaliações."""
    planos = (
        db.query(Plano)
        .filter(Plano.ativo == True)
        .order_by(Plano.preco_mensal.asc())
        .all()
    )

    avaliacoes = (
        db.query(Avaliacao)
        .options(joinedload(Avaliacao.salao))
        .order_by(Avaliacao.nota.desc(), Avaliacao.criado_em.desc())
        .limit(30)
        .all()
    )
    total_avaliacoes = db.query(Avaliacao).count()
    media = None
    if avaliacoes:
        media = sum(float(a.nota) for a in avaliacoes) / len(avaliacoes)

    # Quem pode avaliar: contratante (DONO/FUNCIONARIO) logado de um salão que já pagou
    pode_avaliar = False
    u = obter_usuario_opcional(request, db)
    if u and u.role != RoleUsuario.ADMIN and u.salao_id:
        ass = db.query(Assinatura).filter(Assinatura.salao_id == u.salao_id).first()
        pode_avaliar = _ja_foi_cliente(ass)

    return templates.TemplateResponse("contratacao/planos.html", {
        "request": request,
        "planos": planos,
        "avaliacoes": avaliacoes,
        "total_avaliacoes": total_avaliacoes,
        "media_avaliacoes": media,
        "pode_avaliar": pode_avaliar,
        "aval_msg": request.query_params.get("aval_msg", ""),
        "aval_erro": request.query_params.get("aval_erro", ""),
        "paletas": PALETAS,
    })


# ---------------------------------------------------------------------------
# POST /contratar/avaliar — avaliação de contratantes
# ---------------------------------------------------------------------------
@router.post("/contratar/avaliar")
def enviar_avaliacao(
    request: Request,
    nota: str = Form(...),
    comentario: str = Form(...),
    db: Session = Depends(get_db),
):
    def erro(msg: str):
        return RedirectResponse(
            f"/contratar?aval_erro={quote(msg)}#avaliacoes",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Só um contratante AUTENTICADO pode avaliar — evita avaliação forjada
    # em nome de outro negócio só conhecendo o e-mail dele.
    usuario = obter_usuario_opcional(request, db)
    if not usuario:
        return erro("Faça login no painel do seu salão para avaliar o sistema.")
    if usuario.role == RoleUsuario.ADMIN or not usuario.salao_id:
        return erro("Apenas o responsável por um salão contratante pode avaliar.")

    salao = db.query(Salao).filter(Salao.id == usuario.salao_id).first()
    assinatura = (
        db.query(Assinatura).filter(Assinatura.salao_id == salao.id).first()
        if salao else None
    )
    if not salao or not _ja_foi_cliente(assinatura):
        return erro("Sua avaliação será liberada após a confirmação do pagamento da assinatura.")

    try:
        nota_dec = Decimal(nota.replace(",", "."))
    except InvalidOperation:
        return erro("Selecione uma nota de 0,5 a 5 estrelas.")
    if nota_dec < Decimal("0.5") or nota_dec > 5 or (nota_dec * 2) % 1 != 0:
        return erro("Selecione uma nota de 0,5 a 5 estrelas.")

    comentario = (comentario or "").strip()
    if len(comentario) < 10:
        return erro("Escreva um comentário com pelo menos 10 caracteres.")
    if len(comentario) > MAX_COMENTARIO:
        return erro(f"O comentário pode ter no máximo {MAX_COMENTARIO} caracteres.")

    avaliacao = db.query(Avaliacao).filter(Avaliacao.salao_id == salao.id).first()
    if avaliacao:
        avaliacao.nota = nota_dec
        avaliacao.comentario = comentario
        msg = "Sua avaliação foi atualizada. Obrigado!"
    else:
        db.add(Avaliacao(salao_id=salao.id, nota=nota_dec, comentario=comentario))
        msg = "Avaliação publicada. Obrigado por avaliar!"
    db.commit()

    return RedirectResponse(
        f"/contratar?aval_msg={quote(msg)}#avaliacoes",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# GET /contratar/sucesso
# ---------------------------------------------------------------------------
@router.get("/contratar/sucesso", response_class=HTMLResponse)
def sucesso_contratacao(
    request: Request,
    c: str = "",
    db: Session = Depends(get_db),
):
    """'Confirme seu e-mail'. O código assinado (válido 1 dia) impede ver dados de outro cadastro pelo slug."""
    try:
        salao_id = _assinador_sucesso.loads(c, max_age=86400)
    except (BadSignature, SignatureExpired):
        return RedirectResponse("/contratar", status_code=status.HTTP_303_SEE_OTHER)
    salao_obj = db.get(Salao, salao_id)
    if not salao_obj or not salao_obj.assinatura:
        return RedirectResponse("/contratar", status_code=status.HTTP_303_SEE_OTHER)

    assinatura = salao_obj.assinatura
    return templates.TemplateResponse("contratacao/sucesso.html", {
        "request": request,
        "salao": salao_obj,
        "plano": assinatura.plano,
        "assinatura": assinatura,
        "com_teste": assinatura.status == StatusAssinatura.TESTE,
        "dias_teste": settings.DIAS_TESTE,
        "valor_cobrado": float(assinatura.valor_cobrado or 0),
    })


# ---------------------------------------------------------------------------
# GET/POST /contratar/{plano_id}
# ---------------------------------------------------------------------------
def _render_form(request: Request, plano: Plano, erro: str = "", form_data: dict | None = None,
                 periodicidade: str = "MENSAL", status_code: int = 200):
    return templates.TemplateResponse("contratacao/form.html", {
        "request": request,
        "plano": plano,
        "erro": erro,
        "form_data": form_data or {},
        "periodicidade_selecionada": periodicidade,
        "dias_teste": settings.DIAS_TESTE,
        "dias_aviso": settings.DIAS_AVISO_VENCIMENTO,
    }, status_code=status_code)


@router.get("/contratar/{plano_id:int}", response_class=HTMLResponse)
def formulario_contratacao(
    plano_id: int,
    request: Request,
    periodicidade: str = "MENSAL",
    db: Session = Depends(get_db),
):
    """Formulário para contratar um plano específico."""
    plano = db.query(Plano).filter(Plano.id == plano_id, Plano.ativo == True).first()
    if not plano:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")

    return _render_form(request, plano, periodicidade="ANUAL" if periodicidade == "ANUAL" else "MENSAL")


@router.post("/contratar/{plano_id:int}")
def processar_contratacao(
    plano_id: int,
    request: Request,
    nome_salao: str = Form(...),
    slug: str = Form(""),
    nome_responsavel: str = Form(...),
    email: str = Form(...),
    confirmar_email: str = Form(...),
    telefone: str = Form(...),
    documento: str = Form(""),
    senha: str = Form(...),
    confirmar_senha: str = Form(...),
    periodicidade: str = Form(...),
    aceite_termos: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Processa a contratação:
    1. Valida e normaliza todos os dados (no servidor — o JS é só conforto)
    2. Cria Salao (ativo=False)
    3. Cria Usuario (DONO) com aceite dos termos registrado
    4. Cria Assinatura (AGUARDANDO_PAGAMENTO)
    5. Redireciona para página de sucesso
    """
    plano = db.query(Plano).filter(Plano.id == plano_id, Plano.ativo == True).first()
    if not plano:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")

    form_data = {
        "nome_salao": nome_salao, "slug": slug, "nome_responsavel": nome_responsavel,
        "email": email, "confirmar_email": confirmar_email, "telefone": telefone,
        "documento": documento,
    }

    def falha(msg: str):
        return _render_form(request, plano, msg, form_data, periodicidade, status_code=400)

    nome_salao = nome_salao.strip()
    if not (2 <= len(nome_salao) <= 200):
        return falha("Informe o nome do seu negócio (mínimo 2 caracteres).")

    slug_limpo = _gerar_slug(slug) or _gerar_slug(nome_salao)
    if len(slug_limpo) < 3:
        return falha("O endereço (slug) deve ter pelo menos 3 letras ou números.")
    if slug_limpo in SLUGS_RESERVADOS:
        return falha("Esse endereço é reservado pelo sistema. Escolha outro.")

    telefone_ok = normalizar_telefone(telefone)
    if not telefone_ok:
        return falha("Telefone inválido. Use apenas números com DDD, ex: (11) 98888-7777.")

    nome_responsavel = " ".join(nome_responsavel.split())
    if not nome_pessoa_valido(nome_responsavel) or len(nome_responsavel.split()) < 2:
        return falha("Informe seu nome completo (nome e sobrenome, apenas letras).")

    email_ok = normalizar_email(email)
    if not email_ok:
        return falha("E-mail inválido. Confira se digitou corretamente, ex: nome@gmail.com.")
    if email_ok != (confirmar_email or "").strip().lower():
        return falha("Os e-mails informados não são iguais.")

    if not senha_forte(senha):
        return falha("A senha deve ter no mínimo 8 caracteres, com letras e números.")
    if senha != confirmar_senha:
        return falha("As senhas não coincidem.")

    try:
        periodicidade_enum = Periodicidade(periodicidade)
    except ValueError:
        return falha("Periodicidade inválida.")

    documento_ok = normalizar_documento(documento)
    if not documento_ok:
        return falha("CPF ou CNPJ inválido. Confira os números digitados.")
    doc_tipo, doc_numero = documento_ok

    if aceite_termos != "on":
        return falha("Para continuar, leia e aceite os Termos de Uso e a Política de Privacidade.")

    if db.query(Salao).filter(Salao.slug == slug_limpo).first():
        return falha("Esse endereço (slug) já está em uso. Escolha outro.")

    if db.query(Usuario).filter(Usuario.email == email_ok).first():
        return falha("Já existe uma conta com este e-mail. Faça login ou use outro e-mail.")

    # Conta só cadastros que passaram na validação: erro de digitação não bloqueia ninguém,
    # mas um robô não cria dezenas de contas pelo mesmo IP.
    verificar_limite(request, "contratar")

    # O teste grátis é um por CPF/CNPJ: documento repetido contrata direto, sem teste.
    documento_repetido = db.query(Salao.id).filter(Salao.documento == doc_numero).first() is not None

    # 1. Salão fica inativo até o e-mail ser confirmado (teste) ou o pagamento (sem teste)
    salao = Salao(
        nome=nome_salao,
        slug=slug_limpo,
        email_principal=email_ok,
        telefone=telefone_ok,
        whatsapp=telefone_ok,
        documento=doc_numero,
        tipo_documento=doc_tipo,
        ativo=False,
    )
    db.add(salao)
    db.flush()

    # 2. Usuário DONO — só entra depois de confirmar o e-mail
    usuario = Usuario(
        salao_id=salao.id,
        nome=nome_responsavel,
        email=email_ok,
        senha_hash=hash_senha(senha),
        role=RoleUsuario.DONO,
        ativo=True,
        email_verificado=False,
        termos_aceitos_em=datetime.now(timezone.utc),
    )
    db.add(usuario)

    # 3. Assinatura: TESTE (os dias começam a contar na confirmação do e-mail)
    valor = plano.preco_anual if periodicidade_enum == Periodicidade.ANUAL else plano.preco_mensal
    assinatura = Assinatura(
        salao_id=salao.id,
        plano_id=plano.id,
        periodicidade=periodicidade_enum,
        status=StatusAssinatura.AGUARDANDO_PAGAMENTO if documento_repetido else StatusAssinatura.TESTE,
        valor_cobrado=valor,
    )
    db.add(assinatura)
    db.commit()

    logger.info("Nova contratação: %s (slug: %s) — Plano %s (%s)%s",
                nome_salao, slug_limpo, plano.nome, periodicidade,
                " — documento já usado, sem teste" if documento_repetido else "")

    enviar_email_verificacao(usuario)
    if documento_repetido:
        cobranca.enviar_cobranca_inicial(
            salao, assinatura,
            f"Recebemos a contratação do {salao.nome} no plano {plano.nome}. Como este CPF/CNPJ já "
            "foi usado em outra conta, o teste grátis não se aplica — a assinatura começa com o pagamento.")
    notificar_admin(
        db, "contratacao", "Nova contratação" + (" (documento repetido)" if documento_repetido else ""),
        f"{salao.nome} — plano {plano.nome}" + (" — CPF/CNPJ já usado em outra conta" if documento_repetido else ""),
        link=f"/admin/saloes/{salao.id}", salao_id=salao.id)

    return RedirectResponse(
        f"/contratar/sucesso?c={_assinador_sucesso.dumps(salao.id)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# GET /termos — Termos de Uso e Política de Privacidade (LGPD)
# ---------------------------------------------------------------------------
@router.get("/termos", response_class=HTMLResponse)
def termos_de_uso(request: Request):
    return templates.TemplateResponse("contratacao/termos.html", {"request": request})
