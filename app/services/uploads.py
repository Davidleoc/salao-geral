"""
Envio de imagens (fotos do salão e foto do profissional).

Segurança: confere o conteúdo real do arquivo (JPG, PNG ou WEBP), não o nome nem o tipo
informado pelo navegador; limita o tamanho (MAX_UPLOAD_MB); gera um nome aleatório.
Os arquivos ficam em app/static/uploads/ (fora do git).
"""

import os
import uuid
from typing import Optional

from app.config import settings

PASTA_UPLOADS = os.path.join("app", "static", "uploads")

_ASSINATURAS = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png"}


def extensao_imagem(conteudo: bytes) -> Optional[str]:
    for assinatura, ext in _ASSINATURAS.items():
        if conteudo.startswith(assinatura):
            return ext
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return ".webp"
    return None


class ImagemInvalida(Exception):
    pass


async def ler_imagem(arquivo) -> tuple[bytes, str]:
    """Lê o UploadFile, valida tamanho e formato. Lança ImagemInvalida com mensagem para o usuário."""
    maximo = settings.MAX_UPLOAD_MB * 1024 * 1024
    conteudo = await arquivo.read(maximo + 1)
    if len(conteudo) > maximo:
        raise ImagemInvalida(f"A imagem {arquivo.filename} passa de {settings.MAX_UPLOAD_MB} MB.")
    ext = extensao_imagem(conteudo)
    if not ext:
        raise ImagemInvalida(f"O arquivo {arquivo.filename} não é uma imagem JPG, PNG ou WEBP.")
    return conteudo, ext


def salvar(conteudo: bytes, ext: str, *subpastas: str) -> str:
    """Grava e devolve a URL pública (/static/uploads/...)."""
    pasta = os.path.join(PASTA_UPLOADS, *subpastas)
    os.makedirs(pasta, exist_ok=True)
    nome = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(pasta, nome), "wb") as fp:
        fp.write(conteudo)
    return "/static/uploads/" + "/".join(subpastas + (nome,))


def apagar(url: Optional[str]) -> None:
    """Apaga um arquivo enviado (só dentro de /static/uploads/)."""
    if not url or not url.startswith("/static/uploads/") or ".." in url:
        return
    caminho = os.path.join("app", *url.lstrip("/").split("/"))
    try:
        os.remove(caminho)
    except FileNotFoundError:
        pass
