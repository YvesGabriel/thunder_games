"""Leitura central do secrets/credentials.json — um único ponto de acesso.

Antes, cada módulo (notify, capture, brain, publish) abria o credentials.json
por conta própria. Agora todos passam por aqui. Se um dia trocar o formato ou o
cofre de segredos, muda-se só este arquivo.
"""

import json

from .settings import SECRETS_FILE

_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(SECRETS_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def get(section, default=None):
    return _load().get(section, {} if default is None else default)


def telegram():
    """(bot_token, chat_id) do Telegram."""
    t = _load()["telegram"]
    return t["bot_token"], str(t["chat_id"])


def youtube():
    return get("youtube")


def pixabay_key():
    return get("pixabay").get("api_key")


def tiktok():
    return get("tiktok")


def claude_cli():
    """(command, model) do Claude Code local."""
    c = get("claude_cli") or {}
    return c.get("command", "claude"), (c.get("model") or "")
