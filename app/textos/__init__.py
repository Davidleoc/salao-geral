"""
TEXTOS DAS TELAS — um arquivo por tela, só com textos (sem HTML).

    landing.py         → página de vendas /contratar
    login.py           → tela de login
    salao_publico.py   → página pública de cada salão /{slug}

Nos templates eles ficam disponíveis como `textos`, por exemplo:
    {{ textos.landing.HERO.titulo_antes }}
    {{ textos.login.TITULO }}

Para criar textos de outra tela: crie um arquivo aqui (ex: agenda.py),
importe-o abaixo e acrescente-o em `textos`.
"""

from types import SimpleNamespace

from app.textos import landing, login, salao_publico

textos = SimpleNamespace(
    landing=landing,
    login=login,
    salao_publico=salao_publico,
)
