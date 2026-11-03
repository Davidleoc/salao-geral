"""
Limite de tentativas por IP (proteção contra robôs).

    verificar_limite(request, "login", maximo=10, janela_segundos=300)

Se o IP passar do limite na janela de tempo, lança LimiteExcedido — o main.py
transforma isso numa página amigável (ou JSON, para chamadas de API) com status 429.

Os contadores ficam na memória do servidor (somem ao reiniciar). Para vários
servidores ao mesmo tempo, troque por Redis mantendo a mesma função.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import settings

# Limites usados no sistema: (máximo de tentativas, janela em segundos)
LIMITES = {
    "login": (10, 300),
    "contratar": (5, 3600),
    "agendar": (10, 3600),
    "recuperar_senha": (5, 3600),
    "avaliar": (10, 3600),
    "lista_espera": (8, 3600),
    "convite": (10, 3600),
    "verificacao_email": (5, 3600),
    "avaliar_atendimento": (10, 3600),
    "disponibilidade": (120, 60),
    "exportar_dados": (5, 3600),
}

_tentativas: dict = defaultdict(deque)
_trava = threading.Lock()


class LimiteExcedido(Exception):
    def __init__(self, acao: str, segundos: int):
        self.acao = acao
        self.segundos = segundos
        minutos = max(1, round(segundos / 60))
        self.mensagem = f"Muitas tentativas seguidas. Aguarde cerca de {minutos} minuto(s) e tente de novo."
        super().__init__(self.mensagem)


def ip_do_cliente(request: Request) -> str:
    if settings.CONFIAR_PROXY:
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def verificar_limite(request: Request, acao: str, maximo: int = None, janela_segundos: int = None) -> None:
    padrao_max, padrao_janela = LIMITES.get(acao, (20, 3600))
    maximo = maximo or padrao_max
    janela = janela_segundos or padrao_janela
    chave = (acao, ip_do_cliente(request))
    agora = time.monotonic()
    with _trava:
        fila = _tentativas[chave]
        while fila and agora - fila[0] > janela:
            fila.popleft()
        if len(fila) >= maximo:
            raise LimiteExcedido(acao, int(janela - (agora - fila[0])) + 1)
        fila.append(agora)


def resetar() -> None:
    """Zera todos os contadores (usado nos testes)."""
    with _trava:
        _tentativas.clear()
