"""
Base dos testes de fluxo: cada teste roda num banco SQLite temporário e limpo,
com dados mínimos (planos, um salão ativo com dono, serviço e horários).

Rodar todos os testes:  venv\\Scripts\\python.exe -m pytest -q
"""

import os

os.environ["TAREFAS_AUTOMATICAS"] = "false"   # nos testes, as tarefas rodam só quando chamadas

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registra todas as tabelas
from app.database import Base, get_db
from app.main import app
from app.models.assinatura import Assinatura, Periodicidade, StatusAssinatura
from app.models.horario import HorarioFuncionamento
from app.models.plano import Plano
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.usuario import RoleUsuario, Usuario
from app.security import hash_senha

ORIGEM = {"Origin": "http://localhost"}   # (mantido por compatibilidade)
SENHA = "senha12345"


def enviar(cliente, url, data=None, files=None, **kwargs):
    """POST como um navegador de verdade: inclui o código CSRF do cookie."""
    if not cliente.cookies.get("csrf_token"):
        cliente.get("/health")
    dados = dict(data or {})
    dados["csrf_token"] = cliente.cookies.get("csrf_token")
    kwargs.setdefault("follow_redirects", False)
    kwargs.pop("headers", None)
    return cliente.post(url, data=dados, files=files, **kwargs)


def _semear(db):
    basico = Plano(nome="Básico", preco_mensal=Decimal("49.90"), preco_anual=Decimal("479"),
                   max_usuarios=2, max_servicos=10, max_emails=2, historico_meses=2, max_fotos=0)
    pro = Plano(nome="Pro", preco_mensal=Decimal("89.90"), preco_anual=Decimal("863"),
                max_usuarios=4, max_servicos=30, max_emails=3, historico_meses=6, max_fotos=5,
                relatorios_avancados=True, personalizacao_avancada=True, lembretes=True,
                permite_gerente=True, sincronizacao_agenda=True)
    db.add_all([basico, pro])
    db.flush()

    admin = Usuario(nome="Admin SaaS", email="admin@teste.com", senha_hash=hash_senha(SENHA), role=RoleUsuario.ADMIN, email_verificado=True)
    db.add(admin)

    saloes = {}
    for slug, email in [("salao-a", "dono.a@teste.com"), ("salao-b", "dono.b@teste.com")]:
        s = Salao(nome=slug.replace("-", " ").title(), slug=slug, email_principal=email, ativo=True,
                  telefone="(11) 98888-7777", cidade="São Paulo", estado="SP")
        db.add(s)
        db.flush()
        db.add(Usuario(nome=f"Dono {slug}", email=email, senha_hash=hash_senha(SENHA), role=RoleUsuario.DONO, salao_id=s.id,
                        email_verificado=True, atende_clientes=True, especialidade="Cabeleireiro", comissao_percentual=Decimal("40")))
        db.add(Assinatura(salao_id=s.id, plano_id=pro.id, periodicidade=Periodicidade.MENSAL,
                          status=StatusAssinatura.ATIVO, valor_cobrado=pro.preco_mensal,
                          data_pagamento=datetime.now(timezone.utc), data_inicio=date.today(),
                          data_fim=date.today() + timedelta(days=30)))
        db.add(Servico(salao_id=s.id, nome=f"Corte {slug}", preco=Decimal("100"), custo=Decimal("30"), duracao_minutos=60))
        for dia in range(7):
            db.add(HorarioFuncionamento(salao_id=s.id, dia_semana=dia, ativo=True,
                                        hora_abertura=time(9), hora_fechamento=time(18), intervalo_minutos=30))
        saloes[slug] = s
    db.commit()


@pytest.fixture(autouse=True)
def _zerar_limites():
    from app.services import limite_taxa
    from app.services.email_service import caixa_saida_dev
    limite_taxa.resetar()
    caixa_saida_dev.clear()
    yield


@pytest.fixture()
def db_sessao(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'teste.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Sessao()
    _semear(db)

    def _get_db():
        sessao = Sessao()
        try:
            yield sessao
        finally:
            sessao.close()

    app.dependency_overrides[get_db] = _get_db
    yield db
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


@pytest.fixture()
def cliente(db_sessao):
    """Navegador anônimo."""
    return TestClient(app, base_url="http://localhost")


@pytest.fixture()
def logar(db_sessao):
    """logar('dono.a@teste.com') -> TestClient já autenticado."""
    def _logar(email, senha=SENHA):
        c = TestClient(app, base_url="http://localhost")
        r = enviar(c, "/minhaagenda/login", {"email": email, "senha": senha})
        assert r.status_code == 303 and "erro" not in r.headers["location"], r.headers.get("location")
        return c
    return _logar
