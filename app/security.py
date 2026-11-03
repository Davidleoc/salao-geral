"""
Segurança — Módulo central de autenticação e criptografia.

Responsabilidades:
  - Hash de senha com Argon2id
  - Tokens de sessão (JWT em cookie httpOnly), que deixam de valer quando a senha muda
  - MFA (TOTP) com o segredo CRIPTOGRAFADO no banco
  - Links assinados: recuperação de senha (uso único) e confirmação de e-mail
  - Tokens aleatórios para links de convite e avaliação (no banco fica só o hash)

Nunca retornar senhas, segredos ou tokens em texto puro em logs ou telas.
"""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from jose import JWTError, jwt

from app.config import settings

# ---------------------------------------------------------------------------
# Argon2id — hash de senha
# ---------------------------------------------------------------------------
_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


def hash_senha(senha: str) -> str:
    """Gera um hash Argon2id da senha. Nunca guardar a senha original."""
    return _ph.hash(senha)


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica se a senha corresponde ao hash. Retorna False em qualquer erro."""
    try:
        return _ph.verify(hash_armazenado, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def senha_precisa_rehash(hash_armazenado: str) -> bool:
    return _ph.check_needs_rehash(hash_armazenado)


def versao_senha(hash_armazenado: str) -> str:
    """Impressão digital curta do hash: muda sempre que a senha muda (invalida sessões e links)."""
    return hashlib.sha256((hash_armazenado or "").encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Criptografia de dados sensíveis guardados no banco (ex: segredo do MFA)
# Chave: CHAVE_CRIPTOGRAFIA no .env; se vazia, derivada do SECRET_KEY.
# ---------------------------------------------------------------------------
_PREFIXO_CIFRADO = "enc:"


def _fernet() -> Fernet:
    base = settings.CHAVE_CRIPTOGRAFIA or settings.SECRET_KEY
    chave = base64.urlsafe_b64encode(hashlib.sha256(("cripto:" + base).encode()).digest())
    return Fernet(chave)


def cifrar(texto: Optional[str]) -> Optional[str]:
    if not texto:
        return texto
    if texto.startswith(_PREFIXO_CIFRADO):
        return texto
    return _PREFIXO_CIFRADO + _fernet().encrypt(texto.encode()).decode()


def decifrar(valor: Optional[str]) -> Optional[str]:
    """Aceita valor cifrado ("enc:...") ou antigo em texto puro (migração gradual)."""
    if not valor or not valor.startswith(_PREFIXO_CIFRADO):
        return valor
    try:
        return _fernet().decrypt(valor[len(_PREFIXO_CIFRADO):].encode()).decode()
    except InvalidToken:
        return None


# ---------------------------------------------------------------------------
# JWT — tokens de sessão (cookie httpOnly)
# ---------------------------------------------------------------------------
ALGORITHM = "HS256"


def criar_token_acesso(usuario_id: int, salao_id: Optional[int], role: str, senha_hash: str = "") -> str:
    """
    sub: usuário · salao_id · role · pv: versão da senha (a sessão cai se a senha mudar) · exp
    """
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario_id),
        "salao_id": salao_id,
        "role": role,
        "pv": versao_senha(senha_hash),
        "exp": expira,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verificar_token(token: str) -> Optional[dict]:
    """Decodifica e valida um JWT. Retorna o payload ou None se inválido/expirado."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# MFA — TOTP (Google Authenticator, Authy etc.)
# ---------------------------------------------------------------------------
def gerar_mfa_secret() -> str:
    """Gera um segredo TOTP (base32). Guarde no banco com cifrar()."""
    return pyotp.random_base32()


def gerar_mfa_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.APP_NAME)


def verificar_codigo_mfa(secret_armazenado: str, codigo: str) -> bool:
    """Recebe o valor do banco (cifrado ou não). valid_window=1 tolera 30s de diferença."""
    secret = decifrar(secret_armazenado)
    if not secret:
        return False
    return pyotp.TOTP(secret).verify((codigo or "").strip(), valid_window=1)


# ---------------------------------------------------------------------------
# Links assinados (itsdangerous)
# ---------------------------------------------------------------------------
_serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
_SALT_RECUPERACAO = "recuperacao-senha-v2"
_SALT_VERIFICACAO = "verificacao-email"


def gerar_token_recuperacao(usuario) -> str:
    """Link de redefinição: deixa de valer assim que a senha é trocada (uso único)."""
    return _serializer.dumps({"u": usuario.id, "pv": versao_senha(usuario.senha_hash)}, salt=_SALT_RECUPERACAO)


def ler_token_recuperacao(token: str, max_age_segundos: int = 24 * 3600) -> Optional[dict]:
    """Retorna {"u": id, "pv": versão} ou None. Quem chama confere se a versão ainda é a atual."""
    try:
        dados = _serializer.loads(token, salt=_SALT_RECUPERACAO, max_age=max_age_segundos)
        return dados if isinstance(dados, dict) and "u" in dados else None
    except (BadSignature, SignatureExpired):
        return None


def gerar_token_verificacao(usuario) -> str:
    return _serializer.dumps({"u": usuario.id, "e": usuario.email}, salt=_SALT_VERIFICACAO)


def ler_token_verificacao(token: str, max_age_segundos: int = 72 * 3600) -> Optional[dict]:
    try:
        dados = _serializer.loads(token, salt=_SALT_VERIFICACAO, max_age=max_age_segundos)
        return dados if isinstance(dados, dict) and "u" in dados else None
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Tokens aleatórios (convites, avaliações, calendário) — no banco só o hash
# ---------------------------------------------------------------------------
def gerar_token_url() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()
