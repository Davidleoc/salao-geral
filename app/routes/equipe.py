"""
Rotas: equipe do salão, perfil, comissões e ganhos.

Painel (logado):
  GET  /minhaagenda/equipe                              → equipe, convites e vagas do plano  [equipe.ver]
  POST /minhaagenda/equipe/convidar                     → convida por e-mail (link único)     [equipe.convidar]
  POST /minhaagenda/equipe/convites/{id}/reenviar|cancelar                                     [equipe.convidar]
  POST /minhaagenda/equipe/{id}/papel                   → muda Gerente/Funcionário            [equipe.papeis]
  POST /minhaagenda/equipe/{id}/remover                 → tira da equipe                       [equipe.papeis]
  POST /minhaagenda/equipe/{id}/enviar-senha            → manda link de nova senha             [equipe.papeis]
  POST /minhaagenda/equipe/{id}/profissional            → especialidade, % comissão, atende    [comissoes.gerenciar]
  GET  /minhaagenda/comissoes                           → relatório de comissões               [comissoes.gerenciar]
  GET  /minhaagenda/meus-ganhos                         → atendimentos e comissões da pessoa   [ganhos.proprios]
  GET/POST /minhaagenda/perfil, /perfil/foto, /perfil/senha → dados, foto e senha da pessoa logada

Público:
  GET/POST /convite/{token}                             → aceitar convite e criar o acesso
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import obter_usuario_atual
from app.models.convite_equipe import ConviteEquipe
from app.models.log_seguranca import EventoSeguranca
from app.models.usuario import RoleUsuario, Usuario
from app.permissoes import ROTULOS
from app.security import criar_token_acesso, gerar_token_url, hash_senha, verificar_senha
from app.services import equipe as svc
from app.services import uploads
from app.services.auditoria import registrar_evento
from app.services.comissoes import BASES, ESCOPOS, descrever_regra, ganhos_profissional, relatorio_comissoes
from app.services.contas import enviar_link_redefinicao
from app.services.limite_taxa import verificar_limite
from app.services.notificacoes import notificar_salao
from app.templates_compat import templates
from app.tenant import obter_tenant
from app.validacao import nome_pessoa_valido, normalizar_telefone, senha_forte

router = APIRouter()

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _ir(url: str, mensagem: str = "", erro: str = "") -> RedirectResponse:
    if mensagem:
        url += ("&" if "?" in url else "?") + "mensagem=" + quote(mensagem)
    if erro:
        url += ("&" if "?" in url else "?") + "erro=" + quote(erro)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _periodo(mes: str) -> tuple[date, date, str]:
    """'2026-10' → (1º dia, último dia, '2026-10'). Vazio = mês atual."""
    hoje = date.today()
    try:
        ano, m = (int(x) for x in mes.split("-"))
        inicio = date(ano, m, 1)
    except (ValueError, AttributeError):
        inicio = hoje.replace(day=1)
    fim = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return inicio, fim, f"{inicio:%Y-%m}"


def _meses_recentes(qtd: int = 12):
    hoje = date.today().replace(day=1)
    lista = []
    for _ in range(qtd):
        lista.append((f"{hoje:%Y-%m}", f"{MESES[hoje.month - 1].capitalize()} de {hoje.year}"))
        hoje = (hoje - timedelta(days=1)).replace(day=1)
    return lista


# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/equipe", response_class=HTMLResponse)
def pagina_equipe(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.ver")
    from app.permissoes import PODE_CONVIDAR
    return templates.TemplateResponse(request, "painel/equipe.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "equipe",
        "membros": svc.membros(db, tenant.salao_id), "convites": svc.convites_pendentes(db, tenant.salao_id),
        "vagas": svc.vagas(db, tenant.salao_id), "pode_convidar_papeis": PODE_CONVIDAR.get(tenant.papel, []),
        "rotulos": ROTULOS, "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/equipe/convidar")
def convidar(request: Request, email: str = Form(...), papel: str = Form("FUNCIONARIO"),
             db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.convidar")
    try:
        convite = svc.convidar(db, tenant.salao, email, papel, usuario, request)
    except svc.ErroConvite as e:
        return _ir("/minhaagenda/equipe", erro=str(e))
    return _ir("/minhaagenda/equipe", mensagem=f"Convite enviado para {convite.email}.")


@router.post("/minhaagenda/equipe/convites/{convite_id}/reenviar")
def reenviar_convite(convite_id: int, request: Request, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.convidar")
    convite = tenant.get_or_404(ConviteEquipe, convite_id)
    try:
        svc.reenviar(db, convite, usuario, request)
    except svc.ErroConvite as e:
        return _ir("/minhaagenda/equipe", erro=str(e))
    return _ir("/minhaagenda/equipe", mensagem="Convite reenviado com um link novo.")


@router.post("/minhaagenda/equipe/convites/{convite_id}/cancelar")
def cancelar_convite(convite_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.convidar")
    convite = tenant.get_or_404(ConviteEquipe, convite_id)
    convite.cancelado_em = datetime.now(timezone.utc)
    db.commit()
    return _ir("/minhaagenda/equipe", mensagem="Convite cancelado. O link deixou de funcionar.")


def _membro(tenant, usuario_id: int) -> Usuario:
    return tenant.get_or_404(Usuario, usuario_id)


@router.post("/minhaagenda/equipe/{usuario_id}/papel")
def mudar_papel(usuario_id: int, request: Request, papel: str = Form(...), db: Session = Depends(get_db),
                usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.papeis")
    membro = _membro(tenant, usuario_id)
    if membro.id == usuario.id or membro.role == RoleUsuario.DONO:
        return _ir("/minhaagenda/equipe", erro="A função do dono não pode ser alterada por aqui.")
    if papel not in ("GERENTE", "FUNCIONARIO"):
        return _ir("/minhaagenda/equipe", erro="Função inválida.")
    if papel == "GERENTE" and not tenant.pode_usar("permite_gerente"):
        return _ir("/minhaagenda/equipe", erro="A função Gerente não está disponível no plano atual.")
    antes = ROTULOS.get(membro.role.value)
    membro.role = RoleUsuario(papel)
    db.commit()
    registrar_evento(db, EventoSeguranca.PAPEL_ALTERADO, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"{membro.nome}: {antes} → {ROTULOS.get(papel)}")
    notificar_salao(db, tenant.salao_id, "equipe", "Sua função mudou", f"Agora você é {ROTULOS.get(papel)}.",
                    usuario_id=membro.id, autor_id=usuario.id)
    return _ir("/minhaagenda/equipe", mensagem=f"{membro.nome} agora é {ROTULOS.get(papel)}.")


@router.post("/minhaagenda/equipe/{usuario_id}/remover")
def remover_membro(usuario_id: int, request: Request, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.papeis")
    membro = _membro(tenant, usuario_id)
    if membro.id == usuario.id or membro.role == RoleUsuario.DONO:
        return _ir("/minhaagenda/equipe", erro="O dono não pode ser removido.")
    membro.ativo = False
    membro.atende_clientes = False
    db.commit()
    registrar_evento(db, EventoSeguranca.USUARIO_REMOVIDO, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"{membro.nome} removido da equipe")
    return _ir("/minhaagenda/equipe", mensagem=f"{membro.nome} foi removido da equipe e não consegue mais entrar.")


@router.post("/minhaagenda/equipe/{usuario_id}/enviar-senha")
def enviar_senha_membro(usuario_id: int, request: Request, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("equipe.papeis")
    membro = _membro(tenant, usuario_id)
    enviar_link_redefinicao(membro, f"{usuario.nome} pediu um link para você criar uma nova senha no {tenant.salao.nome}.")
    registrar_evento(db, EventoSeguranca.SENHA_RESET_ENVIADO, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"Link de nova senha enviado para {membro.nome}")
    return _ir("/minhaagenda/equipe", mensagem=f"Link para criar nova senha enviado ao e-mail de {membro.nome}.")


@router.post("/minhaagenda/equipe/{usuario_id}/profissional")
def salvar_profissional(usuario_id: int, request: Request, especialidade: str = Form(""), comissao: str = Form(""),
                        comissao_base: str = Form(""), comissao_escopo: str = Form(""),
                        atende_clientes: str = Form(""), voltar: str = Form("/minhaagenda/equipe"),
                        db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("comissoes.gerenciar")
    destino = voltar if voltar in ("/minhaagenda/equipe", "/minhaagenda/comissoes") else "/minhaagenda/equipe"
    membro = _membro(tenant, usuario_id)
    if membro.role == RoleUsuario.DONO and tenant.papel != "DONO":
        return _ir(destino, erro="Só o dono altera os próprios dados.")
    try:
        pct = Decimal(comissao.replace(",", ".")) if comissao.strip() else None
    except InvalidOperation:
        return _ir(destino, erro="Comissão inválida.")
    if pct is not None and not (0 <= pct <= 100):
        return _ir(destino, erro="A comissão deve ficar entre 0% e 100%.")
    membro.especialidade = especialidade.strip()[:100] or None
    membro.comissao_percentual = pct
    # O tipo da comissão (base e escopo) quem define é o dono; o gerente ajusta só o %.
    # Campos vazios (ex: formulário da tela Equipe, que só tem o %) mantêm a regra atual.
    if tenant.papel == "DONO":
        if comissao_base in BASES:
            membro.comissao_base = comissao_base
        if comissao_escopo in ESCOPOS:
            membro.comissao_escopo = comissao_escopo
    membro.atende_clientes = atende_clientes == "on"
    db.commit()
    registrar_evento(db, EventoSeguranca.CONFIGURACAO_ALTERADA, request, usuario_id=usuario.id, salao_id=tenant.salao_id,
                     descricao=f"Comissão de {membro.nome}: {descrever_regra(membro)}")
    return _ir(destino, mensagem=f"Dados de {membro.nome} salvos.")


# ---------------------------------------------------------------------------
# Comissões e ganhos
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/comissoes", response_class=HTMLResponse)
def pagina_comissoes(request: Request, mes: str = "", db: Session = Depends(get_db),
                     usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("comissoes.gerenciar")
    inicio, fim, mes = _periodo(mes)
    relatorio = relatorio_comissoes(db, tenant.salao_id, inicio, fim)
    return templates.TemplateResponse(request, "painel/comissoes.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "comissoes",
        "linhas": relatorio["linhas"], "totais": relatorio["totais"], "bases": BASES, "escopos": ESCOPOS,
        "descrever_regra": descrever_regra,
        "membros": [m for m in svc.membros(db, tenant.salao_id)], "mes": mes, "meses": _meses_recentes(),
        "inicio": inicio, "fim": fim, "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""),
    })


@router.get("/minhaagenda/meus-ganhos", response_class=HTMLResponse)
def pagina_meus_ganhos(request: Request, mes: str = "", db: Session = Depends(get_db),
                       usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    tenant.exigir("ganhos.proprios")
    inicio, fim, mes = _periodo(mes)
    ganhos = ganhos_profissional(db, tenant.salao_id, usuario.id, inicio, fim)
    from app.services.comissoes import comissao_de
    return templates.TemplateResponse(request, "painel/meus_ganhos.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "meus_ganhos", "ganhos": ganhos,
        "comissao_de": comissao_de, "mes": mes, "meses": _meses_recentes(), "inicio": inicio, "fim": fim,
    })


# ---------------------------------------------------------------------------
# Meu perfil
# ---------------------------------------------------------------------------
@router.get("/minhaagenda/perfil", response_class=HTMLResponse)
def pagina_perfil(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    return templates.TemplateResponse(request, "painel/perfil.html", {
        "usuario": usuario, "salao": tenant.salao, "active_page": "perfil",
        "pode_sincronizar": tenant.pode_usar("sincronizacao_agenda"), "url_base": settings.URL_BASE.rstrip("/"),
        "mfa_habilitado": settings.MFA_ENABLED,
        "mensagem": request.query_params.get("mensagem", ""), "erro": request.query_params.get("erro", ""),
    })


@router.post("/minhaagenda/perfil")
def salvar_perfil(nome: str = Form(...), especialidade: str = Form(""), telefone: str = Form(""),
                  db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    obter_tenant(db, usuario)
    nome = " ".join(nome.split())
    if not nome_pessoa_valido(nome):
        return _ir("/minhaagenda/perfil", erro="Informe seu nome usando apenas letras.")
    tel = None
    if telefone.strip():
        tel = normalizar_telefone(telefone)
        if not tel:
            return _ir("/minhaagenda/perfil", erro="Telefone inválido.")
    usuario.nome = nome
    usuario.especialidade = especialidade.strip()[:100] or None
    usuario.telefone = tel
    db.commit()
    return _ir("/minhaagenda/perfil", mensagem="Perfil atualizado.")


@router.post("/minhaagenda/perfil/foto")
async def salvar_foto(foto: Optional[UploadFile] = File(None), remover: str = Form(""),
                      db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    if remover:
        uploads.apagar(usuario.foto)
        usuario.foto = None
        db.commit()
        return _ir("/minhaagenda/perfil", mensagem="Foto removida.")
    if not foto or not foto.filename:
        return _ir("/minhaagenda/perfil", erro="Escolha uma imagem.")
    try:
        conteudo, ext = await uploads.ler_imagem(foto)
    except uploads.ImagemInvalida as e:
        return _ir("/minhaagenda/perfil", erro=str(e))
    uploads.apagar(usuario.foto)
    usuario.foto = uploads.salvar(conteudo, ext, "saloes", str(tenant.salao_id), "equipe")
    db.commit()
    return _ir("/minhaagenda/perfil", mensagem="Foto atualizada. Ela aparece para os clientes na hora de agendar.")


@router.post("/minhaagenda/perfil/senha")
def trocar_senha(request: Request, senha_atual: str = Form(...), nova_senha: str = Form(...), confirmar_senha: str = Form(...),
                 db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    if not verificar_senha(senha_atual, usuario.senha_hash):
        return _ir("/minhaagenda/perfil", erro="Senha atual incorreta.")
    if nova_senha != confirmar_senha:
        return _ir("/minhaagenda/perfil", erro="As senhas novas não coincidem.")
    if not senha_forte(nova_senha):
        return _ir("/minhaagenda/perfil", erro="A nova senha precisa de 8 caracteres, com letras e números.")
    usuario.senha_hash = hash_senha(nova_senha)
    db.commit()
    registrar_evento(db, EventoSeguranca.SENHA_ALTERADA, request, usuario_id=usuario.id, salao_id=usuario.salao_id,
                     descricao="Senha alterada pelo próprio usuário")
    # A troca derruba as outras sessões; esta continua com um token novo
    resp = _ir("/minhaagenda/perfil", mensagem="Senha alterada. Outros aparelhos conectados precisarão entrar de novo.")
    resp.set_cookie("access_token", criar_token_acesso(usuario.id, usuario.salao_id, usuario.role.value, usuario.senha_hash),
                    httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=settings.SESSION_EXPIRE_MINUTES * 60)
    return resp


@router.post("/minhaagenda/perfil/calendario")
def gerar_link_calendario(revogar: str = Form(""), db: Session = Depends(get_db), usuario: Usuario = Depends(obter_usuario_atual)):
    tenant = obter_tenant(db, usuario)
    if not tenant.pode_usar("sincronizacao_agenda"):
        return _ir("/minhaagenda/perfil", erro="A sincronização com o Google Agenda está disponível a partir do plano Pro.")
    usuario.calendario_token = None if revogar else gerar_token_url()
    db.commit()
    return _ir("/minhaagenda/perfil", mensagem="Link desativado." if revogar else "Novo link de calendário gerado.")


# ---------------------------------------------------------------------------
# Aceite do convite (público)
# ---------------------------------------------------------------------------
@router.get("/convite/{token}", response_class=HTMLResponse)
def pagina_convite(token: str, request: Request, erro: str = "", db: Session = Depends(get_db)):
    convite = svc.convite_pelo_token(db, token)
    return templates.TemplateResponse(request, "auth/convite.html", {
        "convite": convite, "token": token, "erro": erro, "rotulos": ROTULOS,
    }, status_code=200 if convite else 404)


@router.post("/convite/{token}")
def aceitar_convite(token: str, request: Request, nome: str = Form(...), especialidade: str = Form(""),
                    senha: str = Form(...), confirmar_senha: str = Form(...), aceite_termos: str = Form(""),
                    db: Session = Depends(get_db)):
    verificar_limite(request, "convite")
    convite = svc.convite_pelo_token(db, token)
    if not convite:
        return _ir(f"/convite/{quote(token)}")

    def erro(msg):
        return _ir(f"/convite/{quote(token)}", erro=msg)

    nome = " ".join(nome.split())
    if not nome_pessoa_valido(nome) or len(nome.split()) < 2:
        return erro("Informe nome e sobrenome, apenas letras.")
    if not senha_forte(senha):
        return erro("A senha precisa de 8 caracteres, com letras e números.")
    if senha != confirmar_senha:
        return erro("As senhas não coincidem.")
    if aceite_termos != "on":
        return erro("Para continuar, aceite os Termos de Uso e a Política de Privacidade.")
    if db.query(Usuario).filter(Usuario.email == convite.email).first():
        return erro("Este e-mail já tem uma conta. Use 'Esqueci a senha' no login.")

    agora = datetime.now(timezone.utc)
    novo = Usuario(
        salao_id=convite.salao_id, nome=nome, email=convite.email, senha_hash=hash_senha(senha),
        role=RoleUsuario(convite.papel), ativo=True, email_verificado=True, termos_aceitos_em=agora,
        especialidade=especialidade.strip()[:100] or None, atende_clientes=True,
    )
    db.add(novo)
    db.flush()
    convite.usado_em = agora            # uso único
    convite.usuario_criado_id = novo.id
    db.commit()
    registrar_evento(db, EventoSeguranca.USUARIO_CRIADO, request, usuario_id=novo.id, salao_id=convite.salao_id,
                     descricao=f"Entrou na equipe como {ROTULOS.get(convite.papel)} pelo convite")
    notificar_salao(db, convite.salao_id, "equipe", "Nova pessoa na equipe",
                    f"{nome} aceitou o convite ({ROTULOS.get(convite.papel)}).", link="/minhaagenda/equipe",
                    papeis=["DONO", "GERENTE"])
    return _ir("/minhaagenda/login", mensagem="Acesso criado! Entre com seu e-mail e a senha que você escolheu.")
