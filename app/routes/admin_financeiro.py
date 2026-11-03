"""
Rota: Painel financeiro do admin — GET /admin/financeiro
MRR, recebido no mês, cancelamentos (churn), inadimplentes e vencimentos dos próximos 7 dias.
Cálculos em services/financeiro.py.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import exigir_admin
from app.models.usuario import Usuario
from app.services import financeiro
from app.templates_compat import templates

router = APIRouter(prefix="/admin")


@router.get("/financeiro", response_class=HTMLResponse)
def painel_financeiro(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_admin)):
    return templates.TemplateResponse("admin/financeiro.html", {
        "request": request, "usuario": usuario, "active_page": "financeiro",
        "tolerancia": settings.DIAS_TOLERANCIA_ATRASO, **financeiro.painel(db),
    })
