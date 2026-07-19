"""Kit de publicação — gera título/descrição/tags/comentário pras 3 plataformas.

Usa o Claude local (services.claude) a partir do jogo + roteiro do vídeo, e
formata pra enviar no Telegram (uma mensagem por plataforma, fácil de copiar).
"""

import json
import re

from services import claude

REGRAS_PUB = """Você escreve o KIT DE PUBLICAÇÃO de um vídeo curto (Short/Reels/TikTok)
do canal "Thunder Games" (@thunder_games_8), que apresenta jogos. Público brasileiro.
Tom chamativo, em português-BR, com emojis com moderação.

Gere para TRÊS plataformas:

YOUTUBE:
- title: chamativo, termina com " #Shorts".
- description: 2–3 linhas sobre o jogo + "🎮 <nome do jogo>" + este bloco fixo:
  "\\n\\n👉 Segue o Thunder Games pra mais achados de games!\\n📸 Instagram: @thunder_games_8\\n🎵 TikTok: @thunder_games_8\\n\\n#Shorts " + 3 a 5 hashtags pt-BR relevantes.
- tags: lista de 5–6 tags pt-BR.
- comment: comentário pra FIXAR, com uma pergunta que engaje.

TIKTOK:
- caption: curta e com pegada de trend + "🎮 <jogo>" + hashtags (inclua #fyp #foryou e 2–3 pt-BR).

INSTAGRAM:
- caption: 2 linhas + "🎮 <jogo>" + "Segue o @thunder_games_8" + hashtags (#reels e 3–4 pt-BR)."""

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
    return _json_do_texto(claude.call(prompt, system=REGRAS_PUB))


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
