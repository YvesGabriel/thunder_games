"""Kit de publicação — gera título/descrição/tags/comentário pras 3 plataformas.

Usa o Claude local (services.claude) a partir do jogo + roteiro do vídeo, e
formata pra enviar no Telegram (uma mensagem por plataforma, fácil de copiar).
"""

import json
import re

from config import prompts
from services import claude

# As regras da publicação vivem em prompts/publicacao.md (editável sem tocar no código).

_SCHEMA = ('{"youtube":{"title":"... #Shorts","description":"...","tags":["..."],"comment":"..."},'
           '"tiktok":{"caption":"..."},"instagram":{"caption":"..."}}')


def _json_do_texto(txt):
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        return json.loads(txt[a:b + 1])
    raise RuntimeError("A resposta do Claude não continha JSON. Início:\n" + (txt or "")[:400])


def gerar_kit(game, roteiro=""):
    """Gera o kit de publicação (dict) pras 3 plataformas."""
    prompt = (f"Jogo: {game}\n\nRoteiro do vídeo (pra você entender o conteúdo):\n{roteiro}\n\n"
              "Gere o kit de publicação. Responda SOMENTE com JSON válido no formato:\n" + _SCHEMA)
    return _json_do_texto(claude.call(prompt, system=prompts.load("publicacao")))


def formatar_telegram(kit, game):
    """Formata o kit em mensagens (uma por plataforma) fáceis de copiar."""
    yt = kit.get("youtube", {})
    tt = kit.get("tiktok", {})
    ig = kit.get("instagram", {})
    tags = ", ".join(yt.get("tags", [])) if isinstance(yt.get("tags"), list) else yt.get("tags", "")
    msgs = []
    msgs.append(
        f"▶️ YOUTUBE — {game}\n\n"
        f"Título:\n{yt.get('title', '')}\n\n"
        f"Descrição:\n{yt.get('description', '')}\n\n"
        f"Tags: {tags}\n\n"
        f"💬 Comentário pra fixar:\n{yt.get('comment', '')}")
    msgs.append(f"🎵 TIKTOK — {game}\n\n{tt.get('caption', '')}")
    msgs.append(f"📸 INSTAGRAM — {game}\n\n{ig.get('caption', '')}")
    return msgs
