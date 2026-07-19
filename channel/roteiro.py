"""Montagem do roteiro.json (a receita de edição) e escolha das expressões.

Aqui vive o "o quê" da edição: quais expressões entram, música por clima, cortes,
legenda e overlays — tudo virando o roteiro.json que o motor (editor) executa.
"""

import glob
import json
import os
import random

from config import settings
from channel.common import _abs, ffprobe_dur, log, BIBLIOTECA

# Padrão do último vídeo aprovado
STD_SUBTITLES = {
    "enabled": True, "mode": "karaoke", "source": "script",
    "text_path": "assets/narration.txt", "align": True,
    "karaoke": {"font_name": "Anton", "font_size": 92, "margin_v": 540, "words_per_block": 3},
    "path": "output/subtitles.srt",
}
STD_ANIMATION = {"slide_seconds": 0.28, "easing": "ease_out"}
STD_WIDTH_FRAC = 0.46
POSITION_CYCLE = ["left", "right", "left", "right", "center", "right"]

# Expressões padrão (na Biblioteca) — ponto de partida de um vídeo novo
DEFAULT_EXPRESSIONS = [
    ("confuso.png", "left"), ("anotando animado.png", "right"),
    ("muito impressionado.png", "left"), ("sorriso engraçado.png", "right"),
    ("boquiaberto.png", "center"), ("dando joinha.png", "right"),
]


# ---------------------------------------------------------------------------
# Expressões do personagem — seleção VARIADA (não repete ordem entre vídeos)
# ---------------------------------------------------------------------------
def _personagem_imgs():
    d = os.path.join(BIBLIOTECA, "Personagem")
    imgs = [p for p in sorted(glob.glob(os.path.join(d, "*.png")))
            if not os.path.basename(p).startswith("_")]
    return imgs


def _posicoes_variadas(n, rng):
    """n posições com viés 40% esquerda / 40% direita / 20% centro, sem repetir seguido."""
    pesos = {"left": 0.4, "right": 0.4, "center": 0.2}
    out, prev = [], None
    for _ in range(n):
        opts = [p for p in pesos if p != prev] or list(pesos)
        w = [pesos[p] for p in opts]
        pick = rng.choices(opts, weights=w, k=1)[0]
        out.append(pick)
        prev = pick
    return out


def _expr_count(dur, avail):
    n = round(dur / 4.0)                 # ~ uma expressão a cada 4 segundos
    return min(max(5, n), avail, 12)     # nunca mais que o disponível na biblioteca


def escolher_expressoes(dur, rng=None):
    """Fallback: sorteia expressões ÚNICAS da biblioteca quando o roteiro não
    trouxe uma lista escolhida pelo Claude (ex.: fluxo manual)."""
    rng = rng or random.Random()
    imgs = _personagem_imgs()
    if not imgs:                          # sem biblioteca: cai no padrão fixo
        return [{"image": os.path.join(BIBLIOTECA, "Personagem", img), "position": pos}
                for img, pos in DEFAULT_EXPRESSIONS]
    n = _expr_count(dur, len(imgs))
    escolhidas = rng.sample(imgs, n)
    rng.shuffle(escolhidas)
    posicoes = _posicoes_variadas(n, rng)
    return [{"image": img, "position": pos} for img, pos in zip(escolhidas, posicoes)]


def _resolve_expr_path(name):
    """Acha o PNG da expressão pelo nome (o nome descreve a emoção)."""
    if not name:
        return None
    base = os.path.splitext(str(name))[0].strip().lower()
    for p in _personagem_imgs():
        if os.path.splitext(os.path.basename(p))[0].strip().lower() == base:
            return p
    return None


def _normalizar_expressoes(lista):
    """Converte a lista de expressões do roteiro (nomes escolhidos pelo Claude)
    em [{image, position?}], descartando nomes que não existem na biblioteca."""
    norm = []
    for e in lista:
        if isinstance(e, str):
            name, pos, img = e, None, None
        else:
            name = e.get("name") or e.get("id")
            pos = e.get("position")
            img = e.get("image") if e.get("image") and os.path.exists(e["image"]) else None
        img = img or _resolve_expr_path(name)
        if img:
            norm.append({"image": img, "position": pos})
    return norm


# ---------------------------------------------------------------------------
# música por clima + montagem do roteiro.json
# ---------------------------------------------------------------------------
def resolve_music(project_dir, plano):
    m = plano.get("music")
    if m:
        return _abs(project_dir, m)
    mood = plano.get("music_mood", "adventure")
    lib = plano.get("music_library") or os.path.join(BIBLIOTECA, "Musicas")
    folder = os.path.join(_abs(project_dir, lib), mood)
    tracks = sorted(glob.glob(os.path.join(folder, "*.mp3")))
    if not tracks:
        raise RuntimeError(f"Sem música para o clima '{mood}' em {folder}. Baixe uma faixa (Pixabay).")
    return tracks[0]


def build_roteiro(project_dir, plano, video_path=None, output_name=None):
    narr_abs = _abs(project_dir, plano.get("narration", "assets/narration.wav"))
    dur = ffprobe_dur(narr_abs) if os.path.exists(narr_abs) else None
    if not dur:
        raise RuntimeError("Não foi possível medir a narração. Rode `narrate` antes de `plan`.")

    # expressões: preferimos a lista que o Claude escolheu junto do roteiro
    # (casa com o texto). Só sorteia se o roteiro não trouxe nada aproveitável.
    exprs = _normalizar_expressoes(plano.get("expressions") or [])
    if not exprs:
        exprs = escolher_expressoes(dur)
    n = len(exprs)
    start = 0.3
    seg = (dur - start) / n
    posic = _posicoes_variadas(n, random.Random())    # 40/40/20, sem repetir seguido
    overlays = []
    for i, e in enumerate(exprs):
        pos = e.get("position") or posic[i]
        overlays.append({
            "id": e.get("id", os.path.splitext(os.path.basename(e["image"]))[0]).replace(" ", "_"),
            "path": e["image"], "start": round(start + i * seg, 2),
            "end": round(start + (i + 1) * seg, 2), "width_frac": e.get("width_frac", STD_WIDTH_FRAC),
            "position": pos, "slide_in": True,
        })

    whooshes = plano.get("whooshes")
    if not whooshes and plano.get("whooshes_dir"):
        wd = _abs(project_dir, plano["whooshes_dir"])
        whooshes = sorted(glob.glob(os.path.join(wd, "*.mp3")))

    roteiro = {
        "project": plano.get("project", os.path.basename(project_dir)),
        "output_name": output_name or plano.get("output_name", "final.mp4"),
        "resolution": {"width": 1080, "height": 1920}, "fps": 30, "layout": "cover",
        "video": {"path": video_path or plano["video"], "start": plano.get("video_start", 0.0)},
        "narration": plano.get("narration", "assets/narration.wav"),
        "music": {"path": resolve_music(project_dir, plano), "volume": plano.get("music_volume", 0.12)},
        "duration": None, "subtitles": STD_SUBTITLES, "animation": STD_ANIMATION,
        "cuts": {"seconds": plano.get("cut_seconds", 2.5)},
        "overlay_sfx": whooshes or [], "overlays": overlays,
    }
    out = os.path.join(project_dir, "roteiro.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(roteiro, f, ensure_ascii=False, indent=2)
    log(f"roteiro.json gerado ({n} expressões, {dur:.1f}s, clima={plano.get('music_mood','?')}): {out}")
    return out
