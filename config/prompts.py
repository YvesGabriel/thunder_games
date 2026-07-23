"""Carregador de prompts externos — os "moldes" que comandam o Claude.

Cada prompt vive em prompts/<nome>.md (texto puro, editável sem tocar em código).
Lê a cada chamada, então editar o .md tem efeito no próximo uso, sem reiniciar nada.

    from config import prompts
    system = prompts.load("roteiro")
"""

import os

from .settings import PROMPTS_DIR


def load(name):
    """Retorna o texto de prompts/<name>.md."""
    path = os.path.join(PROMPTS_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
