"""
Proteção CSRF (envio de formulário forjado por outro site).

Como funciona ("double submit"):
  1. CSRFMiddleware dá a cada navegador um código aleatório no cookie `csrf_token`.
  2. Todo <form method="post"> inclui {{ csrf_input() }} → campo escondido com o mesmo código.
     Chamadas fetch/AJAX mandam o código no cabeçalho X-CSRF-Token (ver static/js/notificacoes.js).
  3. verificar_csrf (dependência global no main.py) recusa POST/PUT/PATCH/DELETE sem o código certo.
Outro site não consegue ler o cookie, então não consegue montar um envio válido.

Formulário novo? Coloque {{ csrf_input() }} logo depois da tag <form method="post">.
"""

import hmac
import secrets

from fastapi import Request
from markupsafe import Markup

from app.config import settings

COOKIE = "csrf_token"
CAMPO = "csrf_token"
CABECALHO = "x-csrf-token"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class CSRFInvalido(Exception):
    pass


def _cookie_da_requisicao(scope) -> str:
    for nome, valor in scope.get("headers", []):
        if nome == b"cookie":
            for parte in valor.decode("latin-1").split(";"):
                k, _, v = parte.strip().partition("=")
                if k == COOKIE and v:
                    return v
    return ""


class CSRFMiddleware:
    """Garante que todo navegador tenha o cookie csrf_token (cria na primeira visita)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        token = _cookie_da_requisicao(scope)
        novo = not token
        if novo:
            token = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csrf_token"] = token

        async def enviar(mensagem):
            if novo and mensagem["type"] == "http.response.start":
                atributos = f"{COOKIE}={token}; Path=/; SameSite=Lax"
                if settings.cookie_secure:
                    atributos += "; Secure"
                mensagem.setdefault("headers", []).append((b"set-cookie", atributos.encode()))
            await send(mensagem)

        await self.app(scope, receive, enviar)


async def verificar_csrf(request: Request) -> None:
    """Dependência global: valida o código em toda requisição que altera dados."""
    if request.method in METODOS_SEGUROS:
        return
    cookie = request.cookies.get(COOKIE, "")
    enviado = request.headers.get(CABECALHO, "")
    if not enviado:
        tipo = request.headers.get("content-type", "")
        if "form" in tipo:
            formulario = await request.form()
            enviado = str(formulario.get(CAMPO, ""))
    if not cookie or not enviado or not hmac.compare_digest(cookie, enviado):
        raise CSRFInvalido()


def token_da_requisicao(request: Request) -> str:
    estado = request.scope.get("state", {})
    return estado.get("csrf_token") or request.cookies.get(COOKIE, "")


def csrf_input_html(request: Request) -> Markup:
    return Markup(f'<input type="hidden" name="{CAMPO}" value="{token_da_requisicao(request)}">')
