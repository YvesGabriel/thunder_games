"""Configuração central de logging — logs claros e consistentes em todo o programa."""

import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "video_auto_editor") -> logging.Logger:
    """Retorna um logger já configurado (formato simples e legível no terminal)."""
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _CONFIGURED = True
    return logger


# Pequenos helpers de impressão de "relatório" (separados do logging técnico)
def title(text: str) -> None:
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def line(text: str = "") -> None:
    print(text)
