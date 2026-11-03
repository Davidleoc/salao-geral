"""
Multi-tenancy — isolamento por salão + permissões da equipe.

REGRA: toda consulta de dados de um salão passa por tenant.query(...) / tenant.get_or_404(...),
que já filtram pelo salao_id do usuário logado. Nunca use salao_id vindo da URL ou do formulário.

    tenant = obter_tenant(db, usuario)
    tenant.exigir("servicos.editar")           # 403 amigável se a função não permitir
    servicos = tenant.query(Servico).all()
    if tenant.pode_usar("exportacao"): ...     # recurso do plano
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assinatura import Assinatura, StatusAssinatura
from app.models.plano import Plano
from app.models.salao import Salao
from app.models.usuario import RoleUsuario, Usuario
from app.permissoes import ROTULOS, SemPermissao, papel_de, pode

# Assinaturas que dão direito de usar os recursos do plano
_STATUS_COM_PLANO = (StatusAssinatura.ATIVO, StatusAssinatura.TESTE, StatusAssinatura.EM_ATRASO, StatusAssinatura.PAGO)


class TenantContext:
    def __init__(self, db: Session, salao: Salao, usuario: Usuario):
        self.db = db
        self.salao = salao
        self.salao_id = salao.id
        self.usuario = usuario
        self.papel = papel_de(usuario)
        self.papel_rotulo = ROTULOS.get(self.papel, self.papel)
        self._assinatura = None
        self._plano_carregado = False
        self._plano = None

    # ---- consultas isoladas por salão
    def query(self, model):
        return self.db.query(model).filter(model.salao_id == self.salao_id)

    def get_or_404(self, model, record_id: int):
        """Registro deste salão ou 404 (nunca 403, para não revelar que existe em outro salão)."""
        obj = self.query(model).filter(model.id == record_id).first()
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado.")
        return obj

    # ---- permissões da equipe (app/permissoes.py)
    def pode(self, permissao: str) -> bool:
        return pode(self.usuario, permissao)

    def exigir(self, permissao: str) -> None:
        if not self.pode(permissao):
            raise SemPermissao()

    @property
    def ve_todos(self) -> bool:
        """Dono/gerente veem a agenda de todos; funcionário só a própria."""
        return self.pode("agenda.todos")

    # ---- assinatura e plano
    @property
    def assinatura(self) -> Assinatura | None:
        if self._assinatura is None:
            self._assinatura = self.db.query(Assinatura).filter(Assinatura.salao_id == self.salao_id).first()
        return self._assinatura

    @property
    def plano(self) -> Plano | None:
        if not self._plano_carregado:
            a = self.assinatura
            self._plano = (self.db.query(Plano).filter(Plano.id == a.plano_id).first()
                           if a and a.status in _STATUS_COM_PLANO else None)
            self._plano_carregado = True
        return self._plano

    def verificar_limite(self, recurso: str, atual: int) -> bool:
        """True se ainda cabe mais um (ex: 'max_servicos', 'max_usuarios'). None no plano = ilimitado."""
        plano = self.plano
        if not plano:
            return False
        limite = getattr(plano, recurso, None)
        return True if limite is None else atual < limite

    def pode_usar(self, recurso: str) -> bool:
        """Recurso liga/desliga do plano (ex: 'exportacao', 'lembretes', 'permite_gerente')."""
        plano = self.plano
        return bool(plano and getattr(plano, recurso, False))


def obter_tenant(db: Session, usuario: Usuario, permitir_inativo: bool = False) -> TenantContext:
    """
    Contexto do salão do usuário logado.
    - Administrador do SaaS não tem salão → usa o /admin.
    - Salão suspenso/aguardando pagamento/encerrado → página explicativa (/minhaagenda/conta-bloqueada),
      exceto nas telas que precisam funcionar mesmo assim (permitir_inativo=True).
    """
    if usuario.role == RoleUsuario.ADMIN:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin"})
    if not usuario.salao_id:
        raise SemPermissao("Usuário não está vinculado a nenhum salão.")

    salao = db.query(Salao).filter(Salao.id == usuario.salao_id).first()
    if not salao:
        raise SemPermissao("Salão não encontrado.")
    if (not salao.ativo or salao.encerrado_em) and not permitir_inativo:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/minhaagenda/conta-bloqueada"})
    return TenantContext(db=db, salao=salao, usuario=usuario)
