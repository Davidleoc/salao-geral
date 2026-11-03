"""
Rotas: Conta do salão — assinatura, pagamento, dados (LGPD) e encerramento.

  GET  /minhaagenda/conta-bloqueada          → explica por que o painel está bloqueado (pagamento, suspensão, encerramento)
  GET  /minhaagenda/assinatura               → plano, vencimento, Pix, histórico, CPF/CNPJ, dados e encerramento (dono)
  POST /minhaagenda/assinatura/documento     → atualiza CPF/CNPJ de quem contrata
  GET  /minhaagenda/assinatura/meus-dados.zip→ baixa todos os dados (JSON + CSV) — todos os planos
  POST /minhaagenda/assinatura/encerrar      → encerra a conta (senha + digitar ENCERRAR)

Essas telas funcionam mesmo com o salão inativo (permitir_inativo=True): é por elas que o dono regulariza.
"""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.assinatura import StatusAssinatura
from app.models.log_seguranca import EventoSeguranca, LogSeguranca
from app.models.pagamento_assinatura import PagamentoAssinatura
from app.models.salao import Salao
from app.models.usuario import Usuario
from app.security import verificar_senha
from app.services import lgpd
from app.services.auditoria import registrar_evento
from app.services.cobranca import pix_copia_e_cola
from app.services.limite_taxa import verificar_limite
from app.templates_compat import templates
from app.tenant import obter_tenant
from app.validacao import formatar_documento, normalizar_documento

router = APIRouter()

_STATUS_COM_PIX = {StatusAssinatura.AGUARDANDO_PAGAMENTO, StatusAssinatura.EM_ATRASO,
                   StatusAssinatura.SUSPENSO, StatusAssinatura.TESTE, StatusAssinatura.ATIVO}


def _ir(url: str, **params) -> RedirectResponse:
    if params:
        url += "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _pix(salao: Salao):
    a = salao.assinatura
    if not a or a.status not in _STATUS_COM_PIX or not a.valor_cobrado:
        return None
    return pix_copia_e_cola(a.valor_cobrado, f"SALAO{salao.id}A{a.id}")


def _hora_de_pagar(a) -> bool:
    """Mostra o Pix quando há algo a pagar ou o vencimento/fim do teste está perto."""
    if not a:
        return False
    if a.status in (StatusAssinatura.AGUARDANDO_PAGAMENTO, StatusAssinatura.EM_ATRASO, StatusAssinatura.SUSPENSO):
        return True
    return bool(a.data_fim and (a.data_fim - date.today()).days <= settings.DIAS_AVISO_VENCIMENTO)


@router.get("/minhaagenda/conta-bloqueada", response_class=HTMLResponse)
def conta_bloqueada(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario, permitir_inativo=True)
    salao = tenant.salao
    if salao.ativo and not salao.encerrado_em:
        return _ir("/minhaagenda/dashboard")
    a = tenant.assinatura
    return templates.TemplateResponse("painel/conta_bloqueada.html", {
        "request": request, "usuario": usuario, "salao": salao, "assinatura": a,
        "plano": a.plano if a else None, "eh_dono": tenant.pode("assinatura.gerenciar"),
        "pix": _pix(salao) if tenant.pode("assinatura.gerenciar") else None,
        "bloqueado": True,
    })


@router.get("/minhaagenda/assinatura", response_class=HTMLResponse)
def pagina_assinatura(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario, permitir_inativo=True)
    tenant.exigir("assinatura.gerenciar")
    salao = tenant.salao
    a = tenant.assinatura

    pagamentos = (db.query(PagamentoAssinatura).filter(PagamentoAssinatura.salao_id == salao.id)
                  .order_by(PagamentoAssinatura.pago_em.desc()).limit(12).all())
    # Transparência: quando o suporte abriu os dados do salão (últimos 90 dias)
    acessos_suporte = (db.query(LogSeguranca)
                       .filter(LogSeguranca.salao_id == salao.id, LogSeguranca.evento == EventoSeguranca.ACESSO_SUPORTE,
                               LogSeguranca.criado_em >= datetime.now(timezone.utc) - timedelta(days=90))
                       .order_by(LogSeguranca.criado_em.desc()).limit(20).all())

    return templates.TemplateResponse("painel/assinatura.html", {
        "request": request, "usuario": usuario, "salao": salao, "assinatura": a,
        "plano": a.plano if a else None,
        "pix": _pix(salao) if _hora_de_pagar(a) else None,
        "pagamentos": pagamentos,
        "acessos_suporte": acessos_suporte,
        "documento_formatado": formatar_documento(salao.tipo_documento, salao.documento),
        "prazo_exclusao": settings.PRAZO_EXCLUSAO_CONTA_DIAS,
        "bloqueado": not salao.ativo or bool(salao.encerrado_em),
        "active_page": "assinatura",
        "mensagem": request.query_params.get("mensagem", ""),
        "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/assinatura/documento")
def salvar_documento(request: Request, documento: str = Form(...), db: Session = Depends(get_db),
                     usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario, permitir_inativo=True)
    tenant.exigir("assinatura.gerenciar")
    doc = normalizar_documento(documento)
    if not doc:
        return _ir("/minhaagenda/assinatura", erro="CPF ou CNPJ inválido. Confira os números.")
    salao = tenant.salao
    salao.tipo_documento, salao.documento = doc
    db.commit()
    registrar_evento(db, EventoSeguranca.SALAO_ALTERADO, request, usuario_id=usuario.id, salao_id=salao.id,
                     descricao=f"{doc[0]} de quem contrata atualizado")
    return _ir("/minhaagenda/assinatura", mensagem="CPF/CNPJ atualizado.")


@router.get("/minhaagenda/assinatura/meus-dados.zip")
def baixar_meus_dados(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario, permitir_inativo=True)
    tenant.exigir("assinatura.gerenciar")
    verificar_limite(request, "exportar_dados")
    salao = tenant.salao
    if salao.anonimizado_em:
        return _ir("/minhaagenda/assinatura", erro="Os dados desta conta já foram apagados.")
    conteudo = lgpd.exportar_zip(db, salao)
    registrar_evento(db, EventoSeguranca.DADOS_EXPORTADOS, request, usuario_id=usuario.id, salao_id=salao.id,
                     descricao="Cópia completa dos dados baixada (JSON + CSV)")
    nome = f"meus-dados-{salao.slug}-{datetime.now():%Y%m%d}.zip"
    return Response(conteudo, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})


@router.post("/minhaagenda/assinatura/encerrar")
def encerrar_conta(request: Request, senha: str = Form(...), confirmacao: str = Form(...), motivo: str = Form(""),
                   db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario, permitir_inativo=True)
    tenant.exigir("assinatura.gerenciar")
    verificar_limite(request, "login")  # mesma proteção contra adivinhar senha
    salao = tenant.salao
    if salao.encerrado_em:
        return _ir("/minhaagenda/assinatura", erro="Esta conta já está encerrada.")
    if confirmacao.strip().upper() != "ENCERRAR":
        return _ir("/minhaagenda/assinatura", erro="Digite ENCERRAR para confirmar.")
    if not verificar_senha(senha, usuario.senha_hash):
        return _ir("/minhaagenda/assinatura", erro="Senha incorreta.")
    lgpd.encerrar_conta(db, salao, usuario, request, motivo.strip())
    return _ir("/minhaagenda/conta-bloqueada")
