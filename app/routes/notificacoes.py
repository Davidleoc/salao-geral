"""
Rotas: notificações na tela (sininho + balões), usadas por static/js/notificacoes.js.

  GET  /api/notificacoes?desde=<id>  → contador de não lidas, últimas da lista e as novas desde <id>
  POST /api/notificacoes/lidas       → marca todas como lidas

Funciona para usuários do salão e para o administrador do SaaS (cada um vê as suas).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.usuario import Usuario
from app.services import notificacoes as svc

router = APIRouter()


@router.get("/api/notificacoes")
def listar(desde: int = 0, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    lida_ate = usuario.ultima_notificacao_vista or 0
    novas = svc.novas_desde(db, usuario, desde) if desde else []
    return {
        "nao_lidas": svc.contar_nao_lidas(db, usuario),
        "ultimo_id": svc.ultimo_id(db, usuario),
        "novas": [svc.para_json(n, lida_ate) for n in novas],
        "lista": [svc.para_json(n, lida_ate) for n in svc.ultimas(db, usuario)],
    }


@router.post("/api/notificacoes/lidas")
def marcar_lidas(db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    usuario.ultima_notificacao_vista = svc.ultimo_id(db, usuario)
    db.commit()
    return {"ok": True}
