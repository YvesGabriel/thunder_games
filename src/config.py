"""Carregamento e parsing do roteiro.json -> Project.

Regras:
- Caminhos de assets no JSON são relativos à PASTA do roteiro.json.
- Aqui só fazemos parsing + defaults. A checagem de existência/validade
  fica no módulo de validação (validation.py), para gerar um relatório.
"""

import json
import os
from typing import Any, Dict

from .models import Overlay, Project

# Campos obrigatórios no JSON (estrutura mínima)
REQUIRED_FIELDS = ["video", "narration"]

# Presets de legenda (estilo tipo CapCut). Valores em PIXELS do vídeo final
# (a .srt vira .ass com PlayRes = resolução do vídeo). Cores em ASS: &HAABBGGRR
# (AA = transparência; 00 = opaco). Escolha com "subtitles": { "preset": "..." }
# e ajuste pontual com "subtitles": { "style": { ... } }.
SUBTITLE_PRESETS = {
    # branco com contorno preto (limpo, padrão)
    "classic": {
        "font_name": "Arial", "font_size": 60, "bold": True,
        "primary_colour": "&H00FFFFFF", "outline_colour": "&H00000000",
        "border_style": 1, "outline": 3, "shadow": 0,
        "back_colour": "&H00000000", "alignment": 2, "margin_v": 430,
    },
    # amarelo em negrito com contorno grosso (bem "viral")
    "bold_yellow": {
        "font_name": "Arial", "font_size": 66, "bold": True,
        "primary_colour": "&H0000FFFF", "outline_colour": "&H00000000",
        "border_style": 1, "outline": 5, "shadow": 0,
        "back_colour": "&H00000000", "alignment": 2, "margin_v": 430,
    },
    # texto branco dentro de uma caixa preta semitransparente
    "boxed": {
        "font_name": "Arial", "font_size": 58, "bold": True,
        "primary_colour": "&H00FFFFFF", "outline_colour": "&H00000000",
        "border_style": 3, "outline": 6, "shadow": 0,
        "back_colour": "&H99000000", "alignment": 2, "margin_v": 440,
    },
    # branco com contorno bem grosso (estilo "pop")
    "outline_heavy": {
        "font_name": "Arial", "font_size": 64, "bold": True,
        "primary_colour": "&H00FFFFFF", "outline_colour": "&H00000000",
        "border_style": 1, "outline": 7, "shadow": 0,
        "back_colour": "&H00000000", "alignment": 2, "margin_v": 430,
    },
    # branco com sombra marcada (sem contorno)
    "shadow_pop": {
        "font_name": "Arial", "font_size": 62, "bold": True,
        "primary_colour": "&H00FFFFFF", "outline_colour": "&H00000000",
        "border_style": 1, "outline": 1, "shadow": 4,
        "back_colour": "&H00000000", "alignment": 2, "margin_v": 430,
    },
}
DEFAULT_PRESET = "classic"

# Estilo das legendas KARAOKÊ (palavra a palavra, estilo CapCut/Shorts).
# A palavra falada fica destacada em `highlight_colour` e cresce `word_scale`%.
KARAOKE_DEFAULTS = {
    "font_name": "Anton",              # fonte pesada; caia para Poppins/Impact se faltar
    "font_size": 92,
    "bold": True,
    "primary_colour": "&H00FFFFFF",    # branco
    "outline_colour": "&H00000000",    # contorno preto
    "back_colour": "&HA0000000",       # sombra semitransparente
    "border_style": 1,
    "outline": 8,                       # contorno grosso
    "shadow": 3,
    "alignment": 2,
    "margin_v": 540,
    "highlight_colour": "&H0000D4FF",  # amarelo #FFD400 (ASS = &HAABBGGRR)
    "words_per_block": 3,               # 2 a 5 palavras por bloco
    "word_scale": 114,                  # escala da palavra destacada (%)
    "pop": True,                        # efeito "pop" ao surgir o bloco
}


class ConfigError(ValueError):
    """roteiro.json inválido ou ilegível."""


def _abs(root: str, rel: str) -> str:
    """Resolve um caminho relativo à pasta do projeto para absoluto."""
    if not rel:
        return rel
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(root, rel))


def load_project(json_path: str) -> Project:
    """Lê o roteiro.json e devolve um Project com caminhos absolutos."""
    json_path = os.path.abspath(json_path)
    if not os.path.exists(json_path):
        raise ConfigError(f"roteiro.json não encontrado: {json_path}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"roteiro.json com JSON inválido: {e}")

    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        raise ConfigError(
            "Campos obrigatórios ausentes no roteiro.json: " + ", ".join(missing)
        )

    root = os.path.dirname(json_path)
    name = data.get("project") or os.path.basename(root) or "projeto"

    # --- vídeo principal ---
    video = data["video"]
    if isinstance(video, str):
        video = {"path": video}
    video_path = _abs(root, video.get("path", ""))
    video_start = float(video.get("start", 0.0))

    # --- narração ---
    narration = data["narration"]
    narration_path = _abs(root, narration if isinstance(narration, str) else narration.get("path", ""))

    # --- música (opcional) ---
    music = data.get("music")
    music_path = None
    music_volume = 0.12
    if music:
        if isinstance(music, str):
            music_path = _abs(root, music)
        else:
            music_path = _abs(root, music.get("path", ""))
            music_volume = float(music.get("volume", music_volume))

    narration_volume = float(data.get("narration_volume", 1.0))

    # --- resolução / fps / layout ---
    res = data.get("resolution", {})
    width = int(res.get("width", 1080))
    height = int(res.get("height", 1920))
    fps = int(data.get("fps", 30))
    layout = str(data.get("layout", "cover")).lower()
    duration = data.get("duration")
    duration = float(duration) if duration is not None else None

    # --- legendas ---
    subs = data.get("subtitles", {})
    if isinstance(subs, bool):
        subs = {"enabled": subs}
    subtitles_enabled = bool(subs.get("enabled", True))
    subtitles_mode = str(subs.get("mode", "static")).lower()
    if subtitles_mode == "karaoke":
        style = dict(KARAOKE_DEFAULTS)
        style.update(subs.get("karaoke", {}))
        style.update(subs.get("style", {}))
    else:
        preset_name = str(subs.get("preset", DEFAULT_PRESET)).lower()
        style = dict(SUBTITLE_PRESETS.get(preset_name, SUBTITLE_PRESETS[DEFAULT_PRESET]))
        style.update(subs.get("style", {}))   # ajustes pontuais por cima do preset

    output_dir = _abs(root, data.get("output_dir", "output"))
    subtitles_rel = subs.get("path", os.path.join("output", "subtitles.srt"))
    subtitles_path = _abs(root, subtitles_rel)

    # Fonte do texto da legenda: o texto do roteiro (inline ou .txt) é preferível
    # a transcrever o áudio (evita erros de reconhecimento).
    subtitles_text = subs.get("text")
    text_path = subs.get("text_path")
    if not subtitles_text and text_path:
        tp = _abs(root, text_path)
        if os.path.exists(tp):
            with open(tp, "r", encoding="utf-8") as f:
                subtitles_text = f.read().strip()
    default_source = "script" if subtitles_text else "transcribe"
    subtitles_source = str(subs.get("source", default_source)).lower()
    subtitles_align = bool(subs.get("align", True))

    # --- animação dos overlays ---
    anim = data.get("animation", {})
    slide_seconds = float(anim.get("slide_seconds", 0.25))
    easing = str(anim.get("easing", "ease_out")).lower()

    # cortes dinâmicos (montagem): corta a cada N segundos (0 = vídeo contínuo)
    cuts = data.get("cuts", {})
    cut_seconds = float(cuts.get("seconds", 0.0))

    # sons de entrada (whoosh) ciclados pelas aparições
    overlay_sfx = [_abs(root, s) for s in data.get("overlay_sfx", [])]

    # --- overlays (imagens) ---
    overlays = []
    for i, ov in enumerate(data.get("overlays", [])):
        overlays.append(Overlay(
            id=str(ov.get("id", f"img{i+1}")),
            path=_abs(root, ov.get("path", "")),
            start=float(ov.get("start", 0.0)),
            end=float(ov.get("end", 0.0)),
            width_frac=float(ov.get("width_frac", 0.30)),
            slide_in=bool(ov.get("slide_in", True)),
            exit=str(ov.get("exit", "none")).lower(),
            position=str(ov.get("position", "right")).lower(),
            enter=str(ov.get("enter", "")).lower(),
            sfx=_abs(root, ov["sfx"]) if ov.get("sfx") else None,
        ))

    return Project(
        name=name, root=root,
        video_path=video_path, video_start=video_start,
        narration_path=narration_path,
        music_path=music_path,
        narration_volume=narration_volume, music_volume=music_volume,
        width=width, height=height, fps=fps, layout=layout, duration=duration,
        subtitles_enabled=subtitles_enabled, subtitle_style=style,
        subtitles_path=subtitles_path,
        subtitles_source=subtitles_source, subtitles_text=subtitles_text,
        subtitles_align=subtitles_align,
        slide_seconds=slide_seconds, subtitles_mode=subtitles_mode,
        easing=easing, overlay_sfx=overlay_sfx, cut_seconds=cut_seconds,
        overlays=overlays,
        output_dir=output_dir,
        output_name=data.get("output_name", "final.mp4"),
    )
