"""
Validação e normalização de dados digitados pelo usuário.

Usado na contratação, no agendamento público e nos cadastros do painel,
para que o banco nunca receba telefone com letras, e-mail malformado etc.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

# E-mail: parte local + domínio com pelo menos um ponto e TLD de 2+ letras
_RE_EMAIL = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,}$"
)

# Nome de pessoa: letras (com acentos), espaços, apóstrofo, hífen e ponto
_RE_NOME_PESSOA = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]*$")

# Caminhos que já são rotas do sistema e não podem virar slug de salão
SLUGS_RESERVADOS = {
    "admin", "api", "contratar", "minhaagenda", "static", "health", "docs",
    "redoc", "openapi", "termos", "favicon", "login", "logout", "sucesso", "dev",
    "avaliar", "calendario", "convite", "verificar-email", "reenviar-verificacao", "robots.txt",
}


def normalizar_email(email: str) -> Optional[str]:
    """Retorna o e-mail em minúsculas se for válido, senão None."""
    email = (email or "").strip().lower()
    if len(email) > 255 or not _RE_EMAIL.match(email):
        return None
    if ".." in email.split("@")[0]:
        return None
    return email


def normalizar_telefone(telefone: str) -> Optional[str]:
    """
    Aceita telefone brasileiro com ou sem máscara.
    Exige DDD válido + 8 dígitos (fixo) ou 9 dígitos começando com 9 (celular).
    Retorna no formato (11) 98888-7777 ou None se inválido.
    Qualquer letra no campo invalida o telefone.
    """
    telefone = (telefone or "").strip()
    if not telefone or re.search(r"[^0-9()\-+ ]", telefone):
        return None
    digitos = re.sub(r"\D", "", telefone)
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) not in (10, 11):
        return None
    ddd, numero = digitos[:2], digitos[2:]
    if ddd[0] == "0" or ddd[1] == "0":
        return None
    if len(numero) == 9 and numero[0] != "9":
        return None
    if len(numero) == 8 and numero[0] in "01":
        return None
    return f"({ddd}) {numero[:-4]}-{numero[-4:]}"


def nome_pessoa_valido(nome: str) -> bool:
    nome = (nome or "").strip()
    return 2 <= len(nome) <= 200 and bool(_RE_NOME_PESSOA.match(nome))


def senha_forte(senha: str) -> bool:
    """Mínimo 8 caracteres, com pelo menos uma letra e um número."""
    return (
        len(senha or "") >= 8
        and re.search(r"[A-Za-z]", senha) is not None
        and re.search(r"\d", senha) is not None
    )


def converter_dinheiro(valor: str, obrigatorio: bool = True) -> Optional[Decimal]:
    """
    Converte '1.234,56', '1234,56' ou '1234.56' em Decimal.
    Retorna None se vazio (quando opcional). Lança ValueError se inválido ou negativo.
    """
    valor = (valor or "").strip().replace("R$", "").replace(" ", "")
    if not valor:
        if obrigatorio:
            raise ValueError("Valor obrigatório.")
        return None
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        raise ValueError("Valor inválido.")
    if numero < 0 or numero > Decimal("99999999.99"):
        raise ValueError("Valor fora do intervalo permitido.")
    return numero.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# CPF / CNPJ (com dígitos verificadores)
# ---------------------------------------------------------------------------
def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(d[j]) * (i + 1 - j) for j in range(i))
        if int(d[i]) != (soma * 10 % 11) % 10:
            return False
    return True


def _cnpj_valido(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n in (12, 13):
        soma = sum(int(d[i]) * pesos[i + (13 - n)] for i in range(n))
        dv = 0 if soma % 11 < 2 else 11 - soma % 11
        if int(d[n]) != dv:
            return False
    return True


def normalizar_documento(valor: str) -> Optional[tuple]:
    """Aceita CPF ou CNPJ com ou sem pontuação. Retorna ("CPF"|"CNPJ", só números) ou None."""
    digitos = re.sub(r"\D", "", valor or "")
    if re.search(r"[A-Za-z]", valor or ""):
        return None
    if len(digitos) == 11 and _cpf_valido(digitos):
        return ("CPF", digitos)
    if len(digitos) == 14 and _cnpj_valido(digitos):
        return ("CNPJ", digitos)
    return None


def mascarar_documento(tipo: Optional[str], digitos: Optional[str]) -> str:
    """Para mostrar sem expor o número todo: ***.456.789-** / **.345.678/0001-**"""
    if not digitos:
        return ""
    if tipo == "CPF" and len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    if tipo == "CNPJ" and len(digitos) == 14:
        return f"**.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-**"
    return "***"


def formatar_documento(tipo: Optional[str], digitos: Optional[str]) -> str:
    if tipo == "CPF" and digitos and len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if tipo == "CNPJ" and digitos and len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return digitos or ""
