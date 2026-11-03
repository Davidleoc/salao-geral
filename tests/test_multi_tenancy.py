import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.database import Base
from app.models.salao import Salao
from app.models.usuario import Usuario, RoleUsuario
from app.models.cliente import Cliente
from app.models.servico import Servico
from app.tenant import TenantContext
from app.security import hash_senha

# Banco em memória para os testes
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_isolamento_de_dados_por_tenant(db):
    """
    Testa se o TenantContext garante o isolamento entre dois salões.
    """
    # 1. Cria dois salões
    salao_A = Salao(nome="Salão A", slug="salao-a", email_principal="a@a.com")
    salao_B = Salao(nome="Salão B", slug="salao-b", email_principal="b@b.com")
    db.add_all([salao_A, salao_B])
    db.commit()
    
    # 2. Cria os donos
    dono_A = Usuario(
        salao_id=salao_A.id, 
        nome="Dono A", 
        email="donoa@a.com", 
        senha_hash=hash_senha("123456"),
        role=RoleUsuario.DONO
    )
    dono_B = Usuario(
        salao_id=salao_B.id, 
        nome="Dono B", 
        email="donob@b.com", 
        senha_hash=hash_senha("123456"),
        role=RoleUsuario.DONO
    )
    db.add_all([dono_A, dono_B])
    db.commit()

    # 3. Cria dados para o Salão A
    cliente_A = Cliente(salao_id=salao_A.id, nome="Cliente A", telefone="111")
    servico_A = Servico(salao_id=salao_A.id, nome="Corte A", preco=Decimal("50.0"), duracao_minutos=30)
    db.add_all([cliente_A, servico_A])
    
    # 4. Cria dados para o Salão B
    cliente_B = Cliente(salao_id=salao_B.id, nome="Cliente B", telefone="222")
    servico_B = Servico(salao_id=salao_B.id, nome="Corte B", preco=Decimal("60.0"), duracao_minutos=45)
    db.add_all([cliente_B, servico_B])
    db.commit()

    # ---------------------------------------------------------
    # TESTE: Contexto do Salão A
    # ---------------------------------------------------------
    tenant_A = TenantContext(db=db, salao=salao_A, usuario=dono_A)
    
    # Busca todos os clientes no contexto A
    clientes_vistos_por_a = tenant_A.query(Cliente).all()
    assert len(clientes_vistos_por_a) == 1
    assert clientes_vistos_por_a[0].nome == "Cliente A"
    
    # Busca um serviço de outro salão (deve falhar via get_or_404)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        tenant_A.get_or_404(Servico, servico_B.id)
    assert exc.value.status_code == 404  # Não 403, para não revelar que existe

    # ---------------------------------------------------------
    # TESTE: Contexto do Salão B
    # ---------------------------------------------------------
    tenant_B = TenantContext(db=db, salao=salao_B, usuario=dono_B)
    
    servicos_vistos_por_b = tenant_B.query(Servico).all()
    assert len(servicos_vistos_por_b) == 1
    assert servicos_vistos_por_b[0].nome == "Corte B"

    with pytest.raises(HTTPException):
        tenant_B.get_or_404(Cliente, cliente_A.id)
