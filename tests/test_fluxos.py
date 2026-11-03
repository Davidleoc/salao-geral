"""
Testes de ponta a ponta dos fluxos principais (banco temporário — ver conftest.py).
Se algum quebrar depois de uma alteração, o nome do teste diz o que parou de funcionar.
"""

import re
from datetime import date, timedelta

from jose import jwt

from app.config import settings
from app.models.agendamento import Agendamento
from app.models.avaliacao import Avaliacao
from app.models.cliente import Cliente
from app.models.salao import Salao
from app.models.servico import Servico
from app.textos import textos
from tests.conftest import SENHA, enviar

FORM_CONTRATACAO = {
    "nome_salao": "Barbearia Nova", "slug": "barbearia-nova", "nome_responsavel": "João Silva",
    "email": "Joao@Gmail.com", "confirmar_email": "joao@gmail.com", "telefone": "(11) 97777-6666",
    "senha": "senha1234", "confirmar_senha": "senha1234", "periodicidade": "MENSAL", "aceite_termos": "on",
    "documento": "529.982.247-25",
}


def _contratar(cliente, **mudancas):
    dados = {**FORM_CONTRATACAO, **mudancas}
    dados = {k: v for k, v in dados.items() if v is not None}
    return enviar(cliente, "/contratar/1", data=dados, follow_redirects=False)


# ---------------------------------------------------------------- páginas públicas
def test_paginas_publicas_e_arquivos_estaticos(cliente):
    for url in ["/contratar", "/contratar/1", "/termos", "/salao-a", "/salao-a/agendar/1", "/minhaagenda/login"]:
        r = cliente.get(url)
        assert r.status_code == 200, url
        for asset in re.findall(r'(?:href|src)="(/static/[^"]+)"', r.text):
            assert cliente.get(asset).status_code == 200, f"{url}: {asset}"


def test_textos_vem_dos_arquivos_de_texto(cliente):
    assert textos.landing.HERO["etiqueta"] in cliente.get("/contratar").text
    assert textos.login.TITULO in cliente.get("/minhaagenda/login").text
    assert textos.salao_publico.ABA_SOBRE in cliente.get("/salao-a").text


def test_sem_none_na_pagina_publica(cliente):
    assert ">None<" not in cliente.get("/salao-a").text


# ---------------------------------------------------------------- contratação
def test_contratacao_rejeita_dados_invalidos(cliente):
    casos = {
        "telefone com letras": {"telefone": "11abc977776666"},
        "e-mail sem domínio": {"email": "joao@gmail", "confirmar_email": "joao@gmail"},
        "e-mails diferentes": {"confirmar_email": "outro@gmail.com"},
        "senha sem número": {"senha": "abcdefgh", "confirmar_senha": "abcdefgh"},
        "senhas diferentes": {"confirmar_senha": "outra1234"},
        "sem aceite dos termos": {"aceite_termos": None},
        "endereço reservado": {"slug": "admin"},
        "nome com número": {"nome_responsavel": "J0ão"},
        "CPF inválido": {"documento": "123.456.789-00"},
        "sem documento": {"documento": ""},
    }
    for nome, mudanca in casos.items():
        assert _contratar(cliente, **mudanca).status_code == 400, nome


def _link_do_email(trecho_url):
    from app.services.email_service import caixa_saida_dev
    for email in reversed(caixa_saida_dev):
        achado = re.search(r'href="https?://[^/"]+(' + re.escape(trecho_url) + r'[^"]*)"', email["corpo"])
        if achado:
            return achado.group(1).replace("&amp;", "&")
    raise AssertionError(f"Nenhum e-mail com link {trecho_url}")


def test_contratacao_valida_cria_salao_inativo_e_teste_comeca_ao_confirmar_email(cliente, db_sessao):
    from app.models.assinatura import StatusAssinatura
    r = _contratar(cliente)
    assert r.status_code == 303 and "/contratar/sucesso?c=" in r.headers["location"]
    salao = db_sessao.query(Salao).filter_by(slug="barbearia-nova").one()
    assert salao.ativo is False and salao.email_principal == "joao@gmail.com"
    assert salao.tipo_documento == "CPF" and salao.documento == "52998224725"
    assert salao.assinatura.status == StatusAssinatura.TESTE and salao.assinatura.data_fim is None
    assert "confirmar seu e-mail" in cliente.get(r.headers["location"]).text
    # A página de sucesso não abre só com o slug (não expõe dados de outro cadastro)
    assert cliente.get("/contratar/sucesso?salao=barbearia-nova", follow_redirects=False).status_code == 303

    # Antes de confirmar o e-mail, o login é recusado
    r = enviar(cliente, "/minhaagenda/login", {"email": "joao@gmail.com", "senha": "senha1234"})
    assert "nao_verificado" in r.headers["location"] or "erro" in r.headers["location"]

    cliente.get(_link_do_email("/verificar-email"))
    db_sessao.expire_all()
    assert salao.ativo is True
    assert salao.assinatura.data_fim == date.today() + timedelta(days=settings.DIAS_TESTE)


def test_contratacao_com_documento_repetido_nao_ganha_teste(cliente, db_sessao):
    from app.models.assinatura import StatusAssinatura
    _contratar(cliente)
    r = _contratar(cliente, slug="outra-loja", nome_salao="Outra Loja", email="maria@gmail.com", confirmar_email="maria@gmail.com")
    assert r.status_code == 303
    outra = db_sessao.query(Salao).filter_by(slug="outra-loja").one()
    assert outra.assinatura.status == StatusAssinatura.AGUARDANDO_PAGAMENTO


# ---------------------------------------------------------------- avaliações
def test_avaliacao_exige_contratante_logado(cliente, logar, db_sessao):
    r = enviar(cliente, "/contratar/avaliar", data={"nota": "5", "comentario": "Tentativa anônima"}, follow_redirects=False)
    assert "aval_erro" in r.headers["location"]

    dono = logar("dono.a@teste.com")
    r = enviar(dono, "/contratar/avaliar", data={"nota": "4.3", "comentario": "Nota fora do passo"}, follow_redirects=False)
    assert "aval_erro" in r.headers["location"]
    r = enviar(dono, "/contratar/avaliar", data={"nota": "4.5", "comentario": "Organizou toda a agenda!"}, follow_redirects=False)
    assert "aval_msg" in r.headers["location"]
    assert db_sessao.query(Avaliacao).count() == 1


# ---------------------------------------------------------------- segurança
def test_isolamento_entre_saloes(logar, db_sessao):
    cli_b = Cliente(salao_id=2, nome="Cliente Secreto", telefone="(11) 90000-0001")
    db_sessao.add(cli_b)
    db_sessao.commit()
    dono_a = logar("dono.a@teste.com")
    assert dono_a.get(f"/minhaagenda/clientes/{cli_b.id}").status_code == 404
    assert dono_a.get("/minhaagenda/servicos/2").status_code == 404


def test_dono_nao_acessa_admin(logar):
    dono = logar("dono.a@teste.com")
    assert dono.get("/admin", follow_redirects=False).status_code == 403


def test_token_forjado_e_mfa_pendente_nao_entram(cliente):
    forjado = jwt.encode({"sub": "1", "role": "ADMIN", "exp": 9999999999}, "chave-errada", algorithm="HS256")
    cliente.cookies.set("access_token", forjado)
    assert cliente.get("/admin", follow_redirects=False).status_code != 200

    pendente = jwt.encode({"sub": "2", "role": "MFA_PENDENTE", "exp": 9999999999}, settings.SECRET_KEY, algorithm="HS256")
    cliente.cookies.set("access_token", pendente)
    assert cliente.get("/minhaagenda/dashboard", follow_redirects=False).status_code in (302, 303)


def test_horarios_com_entrada_invalida_nao_quebra(logar):
    dono = logar("dono.a@teste.com")
    r = enviar(dono, "/minhaagenda/configuracoes/horarios",
                  data={"intervalo_minutos": "abc", "dia_0_ativo": "1", "dia_0_abertura": "9h", "dia_0_fechamento": "25:99"},
                  follow_redirects=False)
    assert r.status_code == 303


def test_cor_invalida_nao_e_gravada(logar, db_sessao):
    dono = logar("dono.a@teste.com")
    enviar(dono, "/minhaagenda/configuracoes", data={"nome": "Salao A", "cor_principal": "red;}</style>", "cor_secundaria": "#0f766e"},
              follow_redirects=False)
    db_sessao.expire_all()
    salao = db_sessao.get(Salao, 1)
    assert salao.cor_principal == "#6366f1" and salao.cor_secundaria == "#0f766e"


# ---------------------------------------------------------------- painel do salão
def test_paginas_do_painel(logar):
    dono = logar("dono.a@teste.com")
    for url in ["/minhaagenda/dashboard", "/minhaagenda/agenda", "/minhaagenda/clientes", "/minhaagenda/servicos",
                "/minhaagenda/servicos/1", "/minhaagenda/relatorios", "/minhaagenda/configuracoes",
                "/minhaagenda/configuracoes/horarios", "/minhaagenda/assinatura"]:
        assert dono.get(url).status_code == 200, url


def test_custo_opcional_e_lucro(logar, db_sessao):
    dono = logar("dono.a@teste.com")
    r = enviar(dono, "/minhaagenda/servicos/novo", data={"nome": "Escova", "descricao": "", "preco": "1.200,00", "custo": "", "duracao_minutos": "60"},
                  follow_redirects=False)
    assert "erro" not in r.headers["location"]
    novo = db_sessao.query(Servico).filter_by(nome="Escova").one()
    assert novo.custo is None and str(novo.preco) == "1200.00" and novo.descricao is None
    assert "Lucro por Serviço" in dono.get("/minhaagenda/relatorios").text


# ---------------------------------------------------------------- agendamento pelo cliente
def test_agendamento_publico(cliente, db_sessao):
    dia = (date.today() + timedelta(days=7)).isoformat()
    horas = cliente.get(f"/api/public/salao-a/disponibilidade?servico_id=1&data={dia}").json()["horarios"]
    assert horas
    base = {"data": dia, "hora": horas[0], "nome": "Ana Paula", "telefone": "(21) 99999-1111", "email": "ana@exemplo.com", "forma_pagamento": "PIX"}

    r = enviar(cliente, "/salao-a/agendar/1", data={**base, "telefone": "21abc"}, follow_redirects=False)
    assert "erro" in r.headers["location"]
    r = enviar(cliente, "/salao-a/agendar/1", data={**base, "email": "ana@"}, follow_redirects=False)
    assert "erro" in r.headers["location"]

    r = enviar(cliente, "/salao-a/agendar/1", data=base, follow_redirects=False)
    assert "/sucesso" in r.headers["location"]
    ag = db_sessao.query(Agendamento).one()
    assert ag.custo is not None  # custo do serviço fica gravado no agendamento

    # o mesmo horário não pode ser agendado de novo
    r = enviar(cliente, "/salao-a/agendar/1", data={**base, "nome": "Outra Pessoa", "telefone": "(21) 98888-2222"}, follow_redirects=False)
    assert "erro" in r.headers["location"]
