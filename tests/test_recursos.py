"""
Testes dos recursos novos: equipe e permissões, CSRF, limites por IP, cobrança,
pedido de senha, lista de espera, pacotes, avaliação do atendimento, calendário e LGPD.
"""

import io
import json
import re
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.assinatura import StatusAssinatura
from app.models.avaliacao_atendimento import AvaliacaoAtendimento
from app.models.cliente import Cliente
from app.models.convite_equipe import ConviteEquipe
from app.models.lista_espera import ListaEspera
from app.models.pacote import Pacote, PacoteCliente
from app.models.salao import Salao
from app.models.servico import Servico
from app.models.solicitacao_senha import SolicitacaoSenha
from app.models.usuario import RoleUsuario, Usuario
from app.security import hash_senha
from tests.conftest import SENHA, enviar


def _salao(db, slug="salao-a"):
    return db.query(Salao).filter_by(slug=slug).one()


def _link_email(trecho):
    from app.services.email_service import caixa_saida_dev
    for email in reversed(caixa_saida_dev):
        achado = re.search(r'href="https?://[^/"]+(' + re.escape(trecho) + r'[^"]*)"', email["corpo"])
        if achado:
            return achado.group(1).replace("&amp;", "&")
    raise AssertionError(f"Nenhum e-mail com {trecho}")


def _funcionario(db, salao, email="func@teste.com", papel=RoleUsuario.FUNCIONARIO):
    u = Usuario(nome="Fulana Func", email=email, senha_hash=hash_senha(SENHA), role=papel, salao_id=salao.id,
                email_verificado=True, atende_clientes=True, comissao_percentual=Decimal("50"))
    db.add(u)
    db.commit()
    return u


def _agendamento(db, salao, profissional_id=None, dias=1, status=StatusAgendamento.CONFIRMADO, email=None):
    servico = db.query(Servico).filter_by(salao_id=salao.id).first()
    cli = Cliente(salao_id=salao.id, nome="Ana Cliente", telefone=f"(11) 9{dias:04d}-{len(email or 'x'):04d}", email=email)
    db.add(cli)
    db.flush()
    ag = Agendamento(salao_id=salao.id, cliente_id=cli.id, servico_id=servico.id, profissional_id=profissional_id,
                     data=date.today() + timedelta(days=dias), hora_inicio=time(10), hora_fim=time(11),
                     valor=servico.preco, custo=servico.custo, status=status)
    db.add(ag)
    db.commit()
    return ag


# ---------------------------------------------------------------- segurança básica
def test_post_sem_csrf_e_recusado(cliente):
    cliente.get("/health")
    r = cliente.post("/minhaagenda/login", data={"email": "x@x.com", "senha": "y"}, follow_redirects=False)
    assert r.status_code == 403


def test_limite_de_tentativas_de_login_por_ip(cliente):
    codigos = [enviar(cliente, "/minhaagenda/login", {"email": "naoexiste@teste.com", "senha": "errada123"}).status_code
               for _ in range(12)]
    assert 429 in codigos


def test_mfa_continua_desligado(logar):
    from app.config import settings
    assert settings.MFA_ENABLED is False and settings.MFA_ADMIN_OBRIGATORIO is False
    c = logar("admin@teste.com")
    assert c.get("/admin", follow_redirects=False).status_code == 200


# ---------------------------------------------------------------- equipe e permissões
def test_convite_de_equipe_e_link_de_uso_unico(logar, db_sessao):
    dono = logar("dono.a@teste.com")
    r = enviar(dono, "/minhaagenda/equipe/convidar", {"email": "nova@teste.com", "papel": "FUNCIONARIO"})
    assert r.status_code == 303
    link = _link_email("/convite/")
    anon = TestClient(app, base_url="http://localhost")
    assert anon.get(link).status_code == 200
    r = enviar(anon, link, {"nome": "Nova Pessoa", "senha": "senha12345", "confirmar_senha": "senha12345",
                            "especialidade": "Manicure", "aceite_termos": "on"})
    assert r.status_code == 303
    nova = db_sessao.query(Usuario).filter_by(email="nova@teste.com").one()
    assert nova.role == RoleUsuario.FUNCIONARIO and nova.salao_id == _salao(db_sessao).id
    # Segunda vez: o link não vale mais
    outro = TestClient(app, base_url="http://localhost")
    r = enviar(outro, link, {"nome": "Intrusa Silva", "senha": "senha12345", "confirmar_senha": "senha12345", "aceite_termos": "on"})
    assert db_sessao.query(Usuario).filter_by(nome="Intrusa Silva").count() == 0


def test_funcionario_ve_so_a_propria_agenda_e_nao_ve_lucro(logar, db_sessao):
    salao = _salao(db_sessao)
    func = _funcionario(db_sessao, salao)
    dono = db_sessao.query(Usuario).filter_by(email="dono.a@teste.com").one()
    meu = _agendamento(db_sessao, salao, func.id, dias=1)
    do_dono = _agendamento(db_sessao, salao, dono.id, dias=2)

    c = logar("func@teste.com")
    for url in ["/minhaagenda/servicos", "/minhaagenda/relatorios", "/minhaagenda/clientes", "/minhaagenda/equipe",
                "/minhaagenda/configuracoes", "/minhaagenda/assinatura", "/minhaagenda/comissoes"]:
        assert c.get(url, follow_redirects=False).status_code == 403, url
    assert c.get(f"/minhaagenda/agenda/{meu.id}").status_code == 200
    assert c.get(f"/minhaagenda/agenda/{do_dono.id}", follow_redirects=False).status_code == 404
    assert c.get("/minhaagenda/meus-ganhos").status_code == 200


def test_gerente_nao_existe_no_plano_basico(logar, db_sessao):
    from app.models.plano import Plano
    salao = _salao(db_sessao)
    salao.assinatura.plano_id = db_sessao.query(Plano).filter_by(nome="Básico").one().id
    db_sessao.commit()
    dono = logar("dono.a@teste.com")
    enviar(dono, "/minhaagenda/equipe/convidar", {"email": "ger@teste.com", "papel": "GERENTE"})
    assert db_sessao.query(ConviteEquipe).filter_by(email="ger@teste.com").count() == 0


# ---------------------------------------------------------------- senha esquecida → admin
def test_pedido_de_senha_vira_alerta_para_o_admin(cliente, logar, db_sessao):
    enviar(cliente, "/minhaagenda/recuperar-senha", {"email": "dono.a@teste.com"})
    pedido = db_sessao.query(SolicitacaoSenha).one()
    assert pedido.status == "PENDENTE"
    admin = logar("admin@teste.com")
    assert "dono.a" in admin.get("/admin/senhas").text
    enviar(admin, f"/admin/senhas/{pedido.id}/enviar")
    db_sessao.expire_all()
    assert pedido.status == "ENVIADO"
    link = _link_email("/minhaagenda/nova-senha")
    anon = TestClient(app, base_url="http://localhost")
    token = link.split("token=")[1]
    r = enviar(anon, "/minhaagenda/nova-senha", {"token": token, "nova_senha": "outra12345", "confirmar_senha": "outra12345"})
    assert r.status_code == 303
    # Link de uso único: a senha mudou, então o mesmo link não serve de novo
    r = enviar(anon, "/minhaagenda/nova-senha", {"token": token, "nova_senha": "mais12345", "confirmar_senha": "mais12345"})
    assert "erro" in r.headers.get("location", "") or r.status_code == 400


# ---------------------------------------------------------------- cobrança
def test_regua_de_cobranca_aviso_atraso_e_suspensao(db_sessao):
    from app.services import cobranca
    from app.services.email_service import caixa_saida_dev
    salao = _salao(db_sessao)
    a = salao.assinatura
    a.data_fim = date.today() + timedelta(days=3)
    db_sessao.commit()
    cobranca.tarefa_cobranca(db_sessao)
    assert any("vence em 3 dias" in e["assunto"] for e in caixa_saida_dev)
    cobranca.tarefa_cobranca(db_sessao)   # no mesmo dia, não repete
    assert sum("vence em 3 dias" in e["assunto"] for e in caixa_saida_dev) == 1

    a.data_fim = date.today() - timedelta(days=2)
    db_sessao.commit()
    cobranca.tarefa_cobranca(db_sessao)
    assert a.status == StatusAssinatura.EM_ATRASO and salao.ativo

    a.data_fim = date.today() - timedelta(days=30)
    db_sessao.commit()
    cobranca.tarefa_cobranca(db_sessao)
    db_sessao.refresh(salao)
    assert a.status == StatusAssinatura.SUSPENSO and salao.ativo is False


def test_salao_suspenso_ve_pagina_de_conta_bloqueada(logar, db_sessao):
    salao = _salao(db_sessao)
    salao.ativo = False
    salao.assinatura.status = StatusAssinatura.SUSPENSO
    db_sessao.commit()
    c = logar("dono.a@teste.com")
    r = c.get("/minhaagenda/agenda", follow_redirects=False)
    assert r.headers["location"] == "/minhaagenda/conta-bloqueada"
    assert "suspensa" in c.get("/minhaagenda/conta-bloqueada").text
    assert c.get("/minhaagenda/assinatura").status_code == 200


# ---------------------------------------------------------------- lista de espera, pacotes, avaliação
def test_lista_de_espera_avisa_o_primeiro_quando_cancelam(cliente, logar, db_sessao):
    salao = _salao(db_sessao)
    ag = _agendamento(db_sessao, salao, dias=3)
    servico_id = ag.servico_id
    for nome, tel in [("Primeira Pessoa", "(11) 91111-1111"), ("Segunda Pessoa", "(11) 92222-2222")]:
        r = enviar(cliente, "/salao-a/lista-espera", {"servico_id": servico_id, "data": ag.data.isoformat(),
                                                    "nome": nome, "telefone": tel, "email": "fila@gmail.com"})
        assert "mensagem" in r.headers["location"]
    dono = logar("dono.a@teste.com")
    enviar(dono, f"/minhaagenda/agenda/{ag.id}/cancelar", {"motivo_cancelamento": "Cliente desmarcou"})
    db_sessao.expire_all()
    status = {i.nome: i.status for i in db_sessao.query(ListaEspera)}
    assert status == {"Primeira Pessoa": "AVISADO", "Segunda Pessoa": "AGUARDANDO"}
    assert "Primeira Pessoa" in dono.get("/minhaagenda/lista-espera").text


def test_pacote_vendido_paga_o_atendimento(logar, db_sessao):
    salao = _salao(db_sessao)
    ag = _agendamento(db_sessao, salao, dias=0)
    dono = logar("dono.a@teste.com")
    enviar(dono, "/minhaagenda/pacotes", {"nome": "4 cortes", "tipo": "PACOTE", "quantidade_sessoes": "4",
                                          "preco": "320,00", "validade_dias": "90", "publico": "on"})
    pacote = db_sessao.query(Pacote).one()
    enviar(dono, "/minhaagenda/pacotes/vender", {"pacote_id": pacote.id, "cliente_id": ag.cliente_id, "forma_pagamento": "PIX"})
    pc = db_sessao.query(PacoteCliente).one()
    assert pc.valor_pago == Decimal("320.00")
    enviar(dono, f"/minhaagenda/agenda/{ag.id}/status", {"novo_status": "CONCLUIDO", "usar_pacote": pc.id})
    db_sessao.expire_all()
    assert pc.sessoes_restantes == 3 and ag.pacote_cliente_id == pc.id


def test_avaliacao_do_atendimento_com_convite_do_google(logar, db_sessao):
    salao = _salao(db_sessao)
    salao.pedir_avaliacao = True
    salao.link_avaliacao_google = "https://g.page/r/teste/review"
    db_sessao.commit()
    ag = _agendamento(db_sessao, salao, dias=0, email="ana@gmail.com")
    dono = logar("dono.a@teste.com")
    enviar(dono, f"/minhaagenda/agenda/{ag.id}/status", {"novo_status": "CONCLUIDO"})
    link = _link_email("/avaliar/")
    anon = TestClient(app, base_url="http://localhost")
    assert "Como foi" in anon.get(link).text
    enviar(anon, link, {"nota": "5", "comentario": "Adorei"})
    pagina = anon.get(link).text
    assert "Avaliar no Google" in pagina
    av = db_sessao.query(AvaliacaoAtendimento).one()
    db_sessao.refresh(av)
    assert av.nota == 5
    assert "Adorei" in dono.get("/minhaagenda/avaliacoes").text


# ---------------------------------------------------------------- calendário
def test_calendario_ics_do_profissional(logar, db_sessao):
    salao = _salao(db_sessao)
    func = _funcionario(db_sessao, salao)
    _agendamento(db_sessao, salao, func.id, dias=1)
    _agendamento(db_sessao, salao, None, dias=2)
    c = logar("func@teste.com")
    enviar(c, "/minhaagenda/perfil/calendario", {})
    db_sessao.refresh(func)
    r = TestClient(app).get(f"/calendario/{func.calendario_token}.ics")
    assert r.status_code == 200 and r.text.startswith("BEGIN:VCALENDAR")
    assert r.text.count("BEGIN:VEVENT") == 1   # só os dele
    assert TestClient(app).get("/calendario/token-falso-qualquer-123456.ics").status_code == 404


# ---------------------------------------------------------------- LGPD
def test_baixar_meus_dados_e_encerrar_conta(logar, db_sessao):
    from app.services import lgpd
    salao = _salao(db_sessao)
    _agendamento(db_sessao, salao, dias=1, email="ana@gmail.com")
    dono = logar("dono.a@teste.com")
    r = dono.get("/minhaagenda/assinatura/meus-dados.zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    dados = json.loads(z.read("dados.json"))
    assert dados["clientes"][0]["nome"] == "Ana Cliente" and "clientes.csv" in z.namelist()

    r = enviar(dono, "/minhaagenda/assinatura/encerrar", {"senha": SENHA, "confirmacao": "encerrar"})
    assert r.headers["location"] == "/minhaagenda/conta-bloqueada"
    db_sessao.expire_all()
    assert salao.encerrado_em and salao.assinatura.status == StatusAssinatura.CANCELADO
    assert TestClient(app).get("/salao-a").status_code == 404

    # Passado o prazo, a retenção anonimiza tudo
    salao.exclusao_prevista_em = datetime.now(timezone.utc) - timedelta(days=1)
    db_sessao.commit()
    lgpd.tarefa_retencao(db_sessao)
    db_sessao.expire_all()
    assert salao.anonimizado_em is not None and salao.documento is None
    assert db_sessao.query(Cliente).filter_by(nome="Ana Cliente").count() == 0
    assert db_sessao.query(Usuario).filter_by(email="dono.a@teste.com").count() == 0


# ---------------------------------------------------------------- admin
def test_paginas_do_admin_abrem(logar, db_sessao):
    admin = logar("admin@teste.com")
    salao = _salao(db_sessao)
    for url in ["/admin", "/admin/financeiro", "/admin/auditoria", "/admin/auditoria?so_admin=1", "/admin/senhas",
                "/admin/assinaturas", "/admin/assinaturas?status_filtro=TESTE", "/admin/saloes?status_filtro=teste",
                f"/admin/saloes/{salao.id}", "/admin/planos"]:
        assert admin.get(url).status_code == 200, url


def test_admin_encerra_e_estende_teste_e_salao_ve_acesso_do_suporte(logar, db_sessao):
    from app.models.log_seguranca import EventoSeguranca, LogSeguranca
    salao = _salao(db_sessao)
    a = salao.assinatura
    a.status, a.data_fim = StatusAssinatura.TESTE, date.today() + timedelta(days=5)
    db_sessao.commit()
    admin = logar("admin@teste.com")
    assert "linha-teste" in admin.get("/admin/assinaturas").text

    enviar(admin, f"/admin/assinaturas/{a.id}/renovar-teste", {"dias": "10"})
    db_sessao.expire_all()
    assert a.status == StatusAssinatura.TESTE and a.data_fim == date.today() + timedelta(days=15)

    enviar(admin, f"/admin/assinaturas/{a.id}/encerrar-teste", {})
    db_sessao.expire_all()
    assert a.status == StatusAssinatura.AGUARDANDO_PAGAMENTO and salao.ativo is False

    enviar(admin, f"/admin/assinaturas/{a.id}/confirmar-pagamento", {"forma": "PIX"})
    db_sessao.expire_all()
    assert a.status == StatusAssinatura.ATIVO and salao.ativo is True
    assert db_sessao.query(LogSeguranca).filter_by(evento=EventoSeguranca.PAGAMENTO_CONFIRMADO).count() == 1

    admin.get(f"/admin/saloes/{salao.id}")
    dono = logar("dono.a@teste.com")
    assert "Suporte consultou" in dono.get("/minhaagenda/assinatura").text


def test_admin_convida_pessoa_para_o_salao(logar, db_sessao):
    salao = _salao(db_sessao)
    admin = logar("admin@teste.com")
    enviar(admin, f"/admin/saloes/{salao.id}/convidar", {"email": "via.admin@teste.com", "papel": "GERENTE"})
    assert db_sessao.query(ConviteEquipe).filter_by(email="via.admin@teste.com", papel="GERENTE").count() == 1
    assert _link_email("/convite/")


# ---------------------------------------------------------------- regra de comissão por profissional
def _concluir(db, salao, prof_id, dias):
    ag = _agendamento(db, salao, prof_id, dias=-dias, status=StatusAgendamento.CONCLUIDO)  # valor 100, custo 30
    return ag


def test_regras_de_comissao_por_profissional(logar, db_sessao):
    from app.services.comissoes import relatorio_comissoes
    salao = _salao(db_sessao)
    dono = db_sessao.query(Usuario).filter_by(email="dono.a@teste.com").one()
    func = _funcionario(db_sessao, salao)                 # 50%
    ger = _funcionario(db_sessao, salao, "ger@teste.com", RoleUsuario.GERENTE)
    ger.nome = "Gerson Gerente"
    db_sessao.commit()
    hoje = date.today()
    for d in (1, 2):
        _concluir(db_sessao, salao, func.id, d)          # 2 atendimentos da funcionária
    _concluir(db_sessao, salao, dono.id, 3)              # 1 do dono (40%)

    c = logar("dono.a@teste.com")
    # Funcionária: 50% sobre o LUCRO do que atendeu  → 2 × (100 − 30) × 50% = 70
    enviar(c, f"/minhaagenda/equipe/{func.id}/profissional",
           {"comissao": "50", "comissao_base": "LUCRO", "comissao_escopo": "PROPRIOS", "voltar": "/minhaagenda/comissoes"})
    # Gerente: 10% sobre o VALOR de todos os atendimentos do salão → 3 × 100 × 10% = 30
    enviar(c, f"/minhaagenda/equipe/{ger.id}/profissional",
           {"comissao": "10", "comissao_base": "VALOR", "comissao_escopo": "SALAO", "voltar": "/minhaagenda/comissoes"})
    db_sessao.expire_all()

    inicio = hoje - timedelta(days=10)
    rel = relatorio_comissoes(db_sessao, salao.id, inicio, hoje)
    por_nome = {l["nome"]: l["comissao"] for l in rel["linhas"]}
    assert por_nome["Fulana Func"] == 70.0
    assert por_nome[ger.nome] == 30.0
    assert por_nome[dono.nome] == 40.0               # dono: 40% sobre o valor (padrão)
    assert rel["totais"]["comissao"] == 140.0
    assert rel["totais"]["lucro_salao"] == 300 - 90 - 140

    # A funcionária vê o próprio ganho, sem o total do salão
    tela = logar("func@teste.com").get("/minhaagenda/meus-ganhos?mes=" + hoje.strftime("%Y-%m")).text
    assert "sobre o lucro do serviço" in tela


def test_gerente_ajusta_percentual_mas_nao_o_tipo_da_comissao(logar, db_sessao):
    salao = _salao(db_sessao)
    func = _funcionario(db_sessao, salao)
    _funcionario(db_sessao, salao, "ger@teste.com", RoleUsuario.GERENTE)
    g = logar("ger@teste.com")
    enviar(g, f"/minhaagenda/equipe/{func.id}/profissional",
           {"comissao": "35", "comissao_base": "LUCRO", "comissao_escopo": "SALAO", "voltar": "/minhaagenda/comissoes"})
    db_sessao.refresh(func)
    assert func.comissao_percentual == Decimal("35") and func.comissao_base == "VALOR" and func.comissao_escopo == "PROPRIOS"


def test_trocar_quem_atendeu_na_ficha(logar, db_sessao):
    salao = _salao(db_sessao)
    func = _funcionario(db_sessao, salao)
    ag = _agendamento(db_sessao, salao, None, dias=1)
    c = logar("dono.a@teste.com")
    assert "Sem profissional definido" in c.get(f"/minhaagenda/agenda/{ag.id}").text
    enviar(c, f"/minhaagenda/agenda/{ag.id}/profissional", {"profissional_id": func.id})
    db_sessao.refresh(ag)
    assert ag.profissional_id == func.id and ag.comissao_percentual == Decimal("50")
    enviar(c, f"/minhaagenda/agenda/{ag.id}/profissional", {"profissional_id": ""})
    db_sessao.refresh(ag)
    assert ag.profissional_id is None
    # Funcionário não troca o profissional
    f = logar("func@teste.com")
    ag.profissional_id = func.id
    db_sessao.commit()
    assert enviar(f, f"/minhaagenda/agenda/{ag.id}/profissional", {"profissional_id": ""}).status_code == 403


def test_pagina_de_agendar_oferece_sem_preferencia_e_especialidade(cliente):
    texto = cliente.get("/salao-a/agendar/1").text
    assert "Sem preferência de profissional" in texto and "Dono salao-a — Cabeleireiro" in texto
