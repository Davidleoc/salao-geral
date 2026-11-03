"""
Rotas: Configurações do salão
  GET  /minhaagenda/configuracoes          → página de configurações
  POST /minhaagenda/configuracoes          → salva dados do salão
  GET  /minhaagenda/configuracoes/horarios → horários de funcionamento
  POST /minhaagenda/configuracoes/horarios → salva horários
  POST /minhaagenda/configuracoes/fotos    → envia fotos da aba "Sobre" (limite do plano)
  POST /minhaagenda/configuracoes/fotos/{id}/excluir → remove uma foto
"""

import os
import re
import uuid
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_compat import templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.deps import obter_usuario_atual
from app.tenant import obter_tenant
from app.models.usuario import Usuario
from app.models.horario import HorarioFuncionamento
from app.models.log_seguranca import EventoSeguranca
from app.services.auditoria import registrar_evento
from app.models.foto_salao import FotoSalao
from app.config import settings
from app.paletas import PALETAS

router = APIRouter()

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

MAX_SOBRE = 800
_RE_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
PASTA_UPLOADS = os.path.join("app", "static", "uploads", "saloes")

# Assinaturas binárias aceitas (não confiamos no content-type enviado pelo navegador)
_TIPOS_IMAGEM = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
}


def _extensao_imagem(conteudo: bytes) -> Optional[str]:
    for assinatura, ext in _TIPOS_IMAGEM.items():
        if conteudo.startswith(assinatura):
            return ext
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return ".webp"
    return None


@router.get("/minhaagenda/configuracoes", response_class=HTMLResponse)
def pagina_configuracoes(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    plano = tenant.plano
    return templates.TemplateResponse("painel/configuracoes.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "fotos": tenant.query(FotoSalao).order_by(FotoSalao.ordem, FotoSalao.id).all(),
        "max_fotos": plano.max_fotos if plano else 0,
        "plano": plano,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "max_sobre": MAX_SOBRE,
        "paletas": PALETAS,
        "active_page": "configuracoes",
        "mensagem": request.query_params.get("mensagem", ""),
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/configuracoes")
def salvar_configuracoes(
    request: Request,
    nome: str = Form(...),
    telefone: str = Form(""),
    whatsapp: str = Form(""),
    email_secundario: str = Form(""),
    instagram: str = Form(""),
    endereco: str = Form(""),
    cidade: str = Form(""),
    estado: str = Form(""),
    cep: str = Form(""),
    descricao: str = Form(""),
    sobre: str = Form(""),
    cor_principal: str = Form("#6366f1"),
    cor_secundaria: str = Form("#a855f7"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    salao = tenant.salao

    sobre = sobre.replace("\r\n", "\n").strip()
    if len(sobre) > MAX_SOBRE:
        return RedirectResponse(
            f"/minhaagenda/configuracoes?erro={quote(f'O texto Sobre pode ter no máximo {MAX_SOBRE} caracteres.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    salao.nome = nome.strip()
    salao.telefone = telefone.strip() or None
    salao.whatsapp = whatsapp.strip() or None
    salao.email_secundario = email_secundario.strip() or None
    salao.instagram = instagram.strip() or None
    salao.endereco = endereco.strip() or None
    salao.cidade = cidade.strip() or None
    salao.estado = estado.strip()[:2].upper() if estado.strip() else None
    salao.cep = cep.strip() or None
    salao.descricao = descricao.strip() or None
    salao.sobre = sobre or None
    # Só aceita cor no formato #rrggbb (as cores vão para o CSS da página pública)
    salao.cor_principal = cor_principal.lower() if _RE_COR.match(cor_principal or "") else "#6366f1"
    salao.cor_secundaria = cor_secundaria.lower() if _RE_COR.match(cor_secundaria or "") else "#a855f7"

    db.commit()

    registrar_evento(
        db, EventoSeguranca.CONFIGURACAO_ALTERADA, request,
        usuario_id=usuario.id, salao_id=tenant.salao_id,
        descricao="Configurações do salão atualizadas",
    )

    return RedirectResponse(
        "/minhaagenda/configuracoes?mensagem=Configura%C3%A7%C3%B5es+salvas+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/minhaagenda/configuracoes/horarios", response_class=HTMLResponse)
def pagina_horarios(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    horarios = tenant.query(HorarioFuncionamento).filter(
        HorarioFuncionamento.profissional_id == None
    ).order_by(HorarioFuncionamento.dia_semana).all()

    horarios_por_dia = {h.dia_semana: h for h in horarios}

    return templates.TemplateResponse("painel/horarios.html", {
        "request": request,
        "usuario": usuario,
        "salao": tenant.salao,
        "horarios_por_dia": horarios_por_dia,
        "dias_semana": DIAS_SEMANA,
        "active_page": "configuracoes",
        "mensagem": request.query_params.get("mensagem", ""),
    })


from datetime import time

@router.post("/minhaagenda/configuracoes/horarios")
async def salvar_horarios(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    form_data = await request.form()

    def _hora(valor):
        """Converte 'HH:MM' em time; retorna None se inválido (nunca lança)."""
        if not valor or not isinstance(valor, str):
            return None
        partes = valor.strip().split(":")
        if len(partes) != 2 or not (partes[0].isdigit() and partes[1].isdigit()):
            return None
        h, m = int(partes[0]), int(partes[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return time(h, m)

    bruto = str(form_data.get("intervalo_minutos", "30")).strip()
    intervalo_minutos = int(bruto) if bruto.isdigit() else 30
    intervalo_minutos = max(5, min(intervalo_minutos, 240))  # limites sãos

    for i in range(7):
        ativo = form_data.get(f"dia_{i}_ativo") == "1"
        abertura = _hora(form_data.get(f"dia_{i}_abertura"))
        fechamento = _hora(form_data.get(f"dia_{i}_fechamento"))
        pausa_inicio = _hora(form_data.get(f"dia_{i}_pausa_inicio"))
        pausa_fim = _hora(form_data.get(f"dia_{i}_pausa_fim"))

        # Buscar registro existente ou criar novo
        horario = tenant.query(HorarioFuncionamento).filter(
            HorarioFuncionamento.dia_semana == i,
            HorarioFuncionamento.profissional_id == None
        ).first()

        if not horario:
            horario = HorarioFuncionamento(salao_id=tenant.salao_id, dia_semana=i)
            db.add(horario)

        horario.intervalo_minutos = intervalo_minutos

        # Só fica ativo se abertura/fechamento forem válidos e coerentes.
        # As colunas de hora são NOT NULL, então mantemos valores padrão
        # mesmo quando o dia está inativo.
        if ativo and abertura and fechamento and abertura < fechamento:
            horario.ativo = True
            horario.hora_abertura = abertura
            horario.hora_fechamento = fechamento
            if pausa_inicio and pausa_fim and pausa_inicio < pausa_fim:
                horario.pausa_inicio = pausa_inicio
                horario.pausa_fim = pausa_fim
            else:
                horario.pausa_inicio = None
                horario.pausa_fim = None
        else:
            horario.ativo = False
            if horario.hora_abertura is None:
                horario.hora_abertura = time(9, 0)
            if horario.hora_fechamento is None:
                horario.hora_fechamento = time(18, 0)

    db.commit()
    
    # Log de segurança
    registrar_evento(
        db, EventoSeguranca.CONFIGURACAO_ALTERADA, request,
        usuario_id=usuario.id, salao_id=tenant.salao_id,
        descricao="Grade de horários atualizada",
    )

    return RedirectResponse(
        "/minhaagenda/configuracoes/horarios?mensagem=Hor%C3%A1rios+salvos+com+sucesso",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------------------------------------------------------------------------
# Fotos da aba "Sobre"
# ---------------------------------------------------------------------------
@router.post("/minhaagenda/configuracoes/fotos")
async def enviar_fotos(
    request: Request,
    fotos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    plano = tenant.plano
    limite = plano.max_fotos if plano else 0

    def voltar(chave: str, msg: str):
        return RedirectResponse(
            f"/minhaagenda/configuracoes?{chave}={quote(msg)}#sobre",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if limite <= 0:
        return voltar("erro", "Seu plano não inclui fotos na aba Sobre. Faça upgrade para o Pro (5 fotos) ou Premium (10 fotos).")

    fotos = [f for f in fotos if f.filename]
    if not fotos:
        return voltar("erro", "Selecione pelo menos uma foto.")

    atuais = tenant.query(FotoSalao).count()
    disponiveis = limite - atuais
    if len(fotos) > disponiveis:
        return voltar("erro", f"Seu plano permite {limite} fotos. Você pode enviar mais {max(disponiveis, 0)}.")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    pasta = os.path.join(PASTA_UPLOADS, str(tenant.salao_id))
    os.makedirs(pasta, exist_ok=True)

    arquivos = []
    for foto in fotos:
        conteudo = await foto.read(max_bytes + 1)
        if len(conteudo) > max_bytes:
            return voltar("erro", f"A foto {foto.filename} passa de {settings.MAX_UPLOAD_MB} MB.")
        ext = _extensao_imagem(conteudo)
        if not ext:
            return voltar("erro", f"O arquivo {foto.filename} não é uma imagem JPG, PNG ou WEBP.")
        arquivos.append((conteudo, ext))

    ordem = atuais
    for conteudo, ext in arquivos:
        nome_arquivo = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(pasta, nome_arquivo), "wb") as fp:
            fp.write(conteudo)
        db.add(FotoSalao(
            salao_id=tenant.salao_id,
            caminho=f"/static/uploads/saloes/{tenant.salao_id}/{nome_arquivo}",
            ordem=ordem,
        ))
        ordem += 1
    db.commit()

    return voltar("mensagem", f"{len(arquivos)} foto(s) adicionada(s).")


@router.post("/minhaagenda/configuracoes/fotos/{foto_id}/excluir")
def excluir_foto(
    foto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obter_usuario_atual),
):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("configuracoes.editar")
    foto = tenant.get_or_404(FotoSalao, foto_id)

    prefixo = f"/static/uploads/saloes/{tenant.salao_id}/"
    if foto.caminho.startswith(prefixo):
        caminho_disco = os.path.join(PASTA_UPLOADS, str(tenant.salao_id), os.path.basename(foto.caminho))
        try:
            os.remove(caminho_disco)
        except FileNotFoundError:
            pass

    db.delete(foto)
    db.commit()
    return RedirectResponse(
        f"/minhaagenda/configuracoes?mensagem={quote('Foto removida.')}#sobre",
        status_code=status.HTTP_303_SEE_OTHER,
    )
