"""
Ponto de entrada da aplicação FastAPI.

Liga: rotas (app/routes), arquivos estáticos, proteção CSRF, limite de tentativas,
cabeçalhos de segurança e as tarefas automáticas (lembretes, cobrança, LGPD).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import CSRFInvalido, CSRFMiddleware, verificar_csrf
from app.database import get_db
from app.permissoes import SemPermissao
from app.routes import (
    admin as admin_router,
    admin_financeiro as admin_financeiro_router,
    admin_seguranca as admin_seguranca_router,
    agenda as agenda_router,
    auth as auth_router,
    clientes as clientes_router,
    configuracoes as configuracoes_router,
    conta as conta_router,
    contratacao as contratacao_router,
    dashboard as dashboard_router,
    equipe as equipe_router,
    extras as extras_router,
    notificacoes as notificacoes_router,
    public as public_router,
    relatorios as relatorios_router,
    servicos as servicos_router,
)
from app.services import tarefas
from app.services.limite_taxa import LimiteExcedido
from app.templates_compat import templates

logger = logging.getLogger(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    tarefa = tarefas.iniciar()
    yield
    if tarefa:
        tarefa.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    lifespan=ciclo_de_vida,
    dependencies=[Depends(verificar_csrf)],
)

app.add_middleware(CSRFMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")



@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.is_production:
        resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resposta


# ---------------------------------------------------------------------------
# Páginas de erro amigáveis
# ---------------------------------------------------------------------------
def _quer_json(request: Request) -> bool:
    return "/api/" in request.url.path or "application/json" in request.headers.get("accept", "")


@app.exception_handler(CSRFInvalido)
async def erro_csrf(request: Request, exc: CSRFInvalido):
    if _quer_json(request):
        return JSONResponse({"erro": "Sessão do formulário expirada. Recarregue a página."}, status_code=403)
    return templates.TemplateResponse(request, "erro.html", {
        "titulo": "Formulário expirado",
        "mensagem": "Por segurança, este formulário precisa ser enviado a partir da própria página. Volte, recarregue a página e tente de novo.",
    }, status_code=403)


@app.exception_handler(SemPermissao)
async def erro_permissao(request: Request, exc: SemPermissao):
    if _quer_json(request):
        return JSONResponse({"erro": exc.mensagem}, status_code=403)
    return templates.TemplateResponse(request, "erro.html", {"titulo": "Acesso restrito", "mensagem": exc.mensagem}, status_code=403)


@app.exception_handler(LimiteExcedido)
async def erro_limite(request: Request, exc: LimiteExcedido):
    try:
        from app.database import SessionLocal
        from app.models.log_seguranca import EventoSeguranca
        from app.services.auditoria import registrar_evento
        from app.services.envios import primeira_vez
        from app.services.limite_taxa import ip_do_cliente
        with SessionLocal() as db:  # registra no máximo uma vez por hora por IP e ação
            from datetime import datetime
            if primeira_vez(db, f"limite:{exc.acao}:{ip_do_cliente(request)}:{datetime.now():%Y%m%d%H}"):
                registrar_evento(db, EventoSeguranca.LIMITE_EXCEDIDO, request, descricao=f"Ação: {exc.acao}")
            db.commit()
    except Exception:
        logger.exception("Falha ao registrar limite excedido")
    if _quer_json(request):
        return JSONResponse({"erro": exc.mensagem}, status_code=429)
    return templates.TemplateResponse(request, "erro.html", {"titulo": "Calma aí 🙂", "mensagem": exc.mensagem}, status_code=429)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
for modulo in (auth_router, dashboard_router, configuracoes_router, servicos_router, clientes_router,
               agenda_router, equipe_router, extras_router, conta_router, notificacoes_router,
               admin_router, admin_financeiro_router, admin_seguranca_router, contratacao_router, relatorios_router):
    app.include_router(modulo.router)

# Endpoints de teste (/dev) — NUNCA em produção
if not settings.is_production:
    from app.routes import dev as dev_router
    app.include_router(dev_router.router)


@app.get("/")
def raiz():
    return RedirectResponse("/contratar")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("app/static/img/favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
    except Exception:
        logger.exception("Health check falhou")
        return JSONResponse({"status": "error"}, status_code=503)


# public router fica no final absoluto para /{slug} não capturar rotas fixas
app.include_router(public_router.router)
