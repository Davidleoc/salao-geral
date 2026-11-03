"""
Configuração dos templates (Jinja2) usada por todas as rotas: `from app.templates_compat import templates`.

Além do objeto `templates`, aqui ficam:
  Filtros   {{ valor|brl }}  {{ status|status_label }}  {{ texto|com_numero(n) }}  {{ telefone|link_whatsapp }}
  Globais   {{ icon('calendar', 20) }}  {{ textos.landing... }}  {{ asset('css/landing.css') }}
"""

from fastapi.templating import Jinja2Templates as _StarletteJinja2Templates
from fastapi import Request

class Jinja2TemplatesCompat(_StarletteJinja2Templates):
    def TemplateResponse(self, *args, **kwargs):
        # Suporta tanto TemplateResponse('nome.html', {'request': req, ...})
        # quanto TemplateResponse(request, 'nome.html', {...})
        # quanto TemplateResponse(name='nome.html', context={...})
        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
            name = args[0]
            context = args[1]
            req = context.get('request')
            status_code = kwargs.get('status_code', 200)
            headers = kwargs.get('headers')
            return super().TemplateResponse(
                request=req,
                name=name,
                context=context,
                status_code=status_code,
                headers=headers
            )
        elif len(args) >= 2 and isinstance(args[0], Request):
            req = args[0]
            name = args[1]
            context = args[2] if len(args) > 2 else kwargs.get('context', {})
            return super().TemplateResponse(
                request=req,
                name=name,
                context=context,
                status_code=kwargs.get('status_code', 200),
                headers=kwargs.get('headers')
            )
        elif 'name' in kwargs and 'context' in kwargs and 'request' not in kwargs:
            context = kwargs['context']
            req = context.get('request')
            kwargs['request'] = req
            return super().TemplateResponse(**kwargs)
        return super().TemplateResponse(*args, **kwargs)

templates = Jinja2TemplatesCompat(directory='app/templates')

def _formatar_brl(valor) -> str:
    """1234.5 → '1.234,50' (sem o prefixo R$)."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


templates.env.filters["brl"] = _formatar_brl


_ROTULOS_STATUS = {
    "AGENDADO": "Agendado",
    "CONFIRMADO": "Confirmado",
    "CONCLUIDO": "Concluído",
    "CANCELADO_PELO_CLIENTE": "Cancelado pelo cliente",
    "CANCELADO_PELO_SALAO": "Cancelado pelo salão",
    "NAO_COMPARECEU": "Não compareceu",
}


def _rotulo_status(status) -> str:
    """StatusAgendamento → texto amigável (evita exibir 'StatusAgendamento.X')."""
    valor = getattr(status, "value", status)
    return _ROTULOS_STATUS.get(valor, str(valor))


templates.env.filters["status_label"] = _rotulo_status


# Ícones SVG disponíveis em todos os templates: {{ icon('calendar', 20) }}
from app.icons import icon as _icon
templates.env.globals["icon"] = _icon


# Arquivos estáticos com versão: {{ asset('css/landing.css') }} -> /static/css/landing.css?v=<data da última edição>
# Assim o navegador nunca usa um CSS/JS antigo depois que o arquivo é alterado.
import os as _os

_PASTA_STATIC = _os.path.join(_os.path.dirname(__file__), "static")


def _asset(caminho: str) -> str:
    try:
        versao = int(_os.path.getmtime(_os.path.join(_PASTA_STATIC, caminho)))
    except OSError:
        versao = 0
    return f"/static/{caminho}?v={versao}"


templates.env.globals["asset"] = _asset


# Textos das telas (app/textos/): {{ textos.landing.HERO.etiqueta }}
from app.textos import textos as _textos
templates.env.globals["textos"] = _textos


# "Até {n} profissionais" -> "Até <strong>4</strong> profissionais" (texto escapado, só o número em negrito)
from markupsafe import Markup as _Markup, escape as _escape


def _com_numero(texto, n) -> _Markup:
    return _Markup(str(_escape(texto)).replace("{n}", f"<strong>{_escape(n)}</strong>"))


templates.env.filters["com_numero"] = _com_numero


# Telefone brasileiro -> link do WhatsApp: {{ salao.whatsapp|link_whatsapp }} -> https://wa.me/5511988887777
import re as _re


def _link_whatsapp(numero) -> str:
    digitos = _re.sub(r"\D", "", str(numero or ""))
    if not digitos:
        return ""
    if not (digitos.startswith("55") and len(digitos) > 11):
        digitos = "55" + digitos
    return f"https://wa.me/{digitos}"


templates.env.filters["link_whatsapp"] = _link_whatsapp


# Campo escondido de proteção CSRF: coloque {{ csrf_input() }} dentro de todo <form method="post">
from jinja2 import pass_context as _pass_context
from app.csrf import csrf_input_html as _csrf_input_html


@_pass_context
def _csrf_input(ctx):
    return _csrf_input_html(ctx["request"])


templates.env.globals["csrf_input"] = _csrf_input


# Permissões da equipe nos templates: {% if pode('relatorios.ver') %} (usa a variável "usuario" da tela)
from app.permissoes import pode as _pode, ROTULOS as _ROTULOS


@_pass_context
def _pode_template(ctx, permissao: str) -> bool:
    usuario = ctx.get("usuario")
    return bool(usuario) and _pode(usuario, permissao)


templates.env.globals["pode"] = _pode_template
templates.env.globals["rotulo_papel"] = lambda papel: _ROTULOS.get(getattr(papel, "value", papel), papel)


# Faixa de aviso da assinatura no painel (teste grátis, vencimento, atraso)
def _aviso_assinatura(salao):
    from datetime import date
    from app.models.assinatura import StatusAssinatura
    a = getattr(salao, "assinatura", None) if salao else None
    if not a or not a.data_fim:
        return None
    dias = (a.data_fim - date.today()).days
    if a.status == StatusAssinatura.TESTE:
        return {"tipo": "info", "texto": f"Teste grátis: {'termina hoje' if dias <= 0 else f'faltam {dias} dia(s)'} (até {a.data_fim:%d/%m/%Y})."}
    if a.status == StatusAssinatura.EM_ATRASO:
        return {"tipo": "perigo", "texto": f"Assinatura em atraso desde {a.data_fim:%d/%m/%Y}. Regularize para evitar a suspensão."}
    if a.status == StatusAssinatura.ATIVO and dias <= 5:
        return {"tipo": "alerta", "texto": f"Sua assinatura {'vence hoje' if dias <= 0 else f'vence em {dias} dia(s)'} ({a.data_fim:%d/%m/%Y})."}
    return None


templates.env.globals["aviso_assinatura"] = _aviso_assinatura


# Situação da assinatura: {{ a.status|status_assinatura }} -> ("Teste grátis", "badge-teste")
_STATUS_ASSINATURA = {
    "TESTE": ("Teste grátis", "badge-teste"),
    "AGUARDANDO_PAGAMENTO": ("Aguardando pagamento", "badge-warning"),
    "ATIVO": ("Ativa", "badge-success"),
    "PAGO": ("Ativa", "badge-success"),
    "EM_ATRASO": ("Em atraso", "badge-danger"),
    "SUSPENSO": ("Suspensa", "badge-danger"),
    "CANCELADO": ("Cancelada", "badge-neutral"),
}


def _status_assinatura(status):
    valor = getattr(status, "value", status) or ""
    return _STATUS_ASSINATURA.get(valor, (valor, "badge-neutral"))


templates.env.filters["status_assinatura"] = _status_assinatura


# Regra de comissão em texto: {{ regra_comissao(pessoa) }} -> "40% sobre o valor do serviço · só o que atendeu"
from app.services.comissoes import descrever_regra as _descrever_regra
templates.env.globals["regra_comissao"] = _descrever_regra
