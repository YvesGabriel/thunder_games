"""Renderização determinística do vídeo final com FFmpeg.

Monta UM único filter_complex e chama o FFmpeg uma vez. Etapas:
  1. adapta o vídeo horizontal para vertical (cover ou blurred);
  2. queima as legendas (estáticas via preset OU karaokê palavra a palavra);
  3. sobrepõe as imagens (posição esquerda/direita/centro, entrada ease-out);
  4. mixa narração + música + sons de entrada (whoosh) por aparição;
  5. exporta MP4 (H.264 + AAC).
"""

import math
import os
from typing import List, Optional, Tuple

from . import ffmpeg_utils
from .logging_utils import get_logger
from .models import Overlay, Project

log = get_logger()

MARGIN_X = 40     # margem lateral da imagem (px)
MARGIN_Y = 40     # margem inferior da imagem (px)
SFX_VOLUME = 0.7  # volume dos sons de entrada


# ----------------------------------------------------------------------------
# Legenda estática (.srt -> .ass) — usada quando mode != "karaoke"
# ----------------------------------------------------------------------------
def _srt_time_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _seconds_to_ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round((t - int(t)) * 100))
    s = int(t) % 60
    m = (int(t) // 60) % 60
    h = int(t) // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _parse_srt(path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    blocks = [b for b in raw.replace("\r\n", "\n").split("\n\n") if b.strip()]
    cues = []
    for block in blocks:
        lines = block.strip().split("\n")
        ti = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ti is None:
            continue
        a, b = [p.strip() for p in lines[ti].split("-->")]
        text = "\\N".join(lines[ti + 1:]).strip()
        cues.append((_srt_time_to_seconds(a), _srt_time_to_seconds(b), text))
    return cues


def srt_to_ass(srt_path: str, ass_path: str, style: dict, width: int, height: int) -> str:
    """Converte uma .srt em .ass com PlayRes = resolução do vídeo (determinístico)."""
    bold = -1 if style.get("bold", True) else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.get('font_name','Arial')},{style.get('font_size',60)},{style.get('primary_colour','&H00FFFFFF')},&H000000FF,{style.get('outline_colour','&H00000000')},{style.get('back_colour','&H00000000')},{bold},0,0,0,100,100,0,0,{style.get('border_style',1)},{style.get('outline',3)},{style.get('shadow',0)},{style.get('alignment',2)},60,60,{style.get('margin_v',430)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, text in _parse_srt(srt_path):
        lines.append(f"Dialogue: 0,{_seconds_to_ass_time(start)},{_seconds_to_ass_time(end)},"
                     f"Default,,0,0,0,,{text}\n")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    return ass_path


# ----------------------------------------------------------------------------
# Posição e animação da imagem (personagem "apresentador")
# ----------------------------------------------------------------------------
def _overlay_xy(ov: Overlay, slide: float, easing: str) -> Tuple[str, str]:
    """Expressões (x, y) do overlay: posição L/R/C + entrada de fora da tela
    com ease-out, sincronizada ao tempo. Variáveis do FFmpeg: W, H, w, h, t."""
    si, ei = ov.start, ov.end
    slide = max(0.05, slide)
    p = f"min(max((t-{si})/{slide}\\,0)\\,1)"
    prog = f"(1-(1-{p})*(1-{p}))" if easing == "ease_out" else p

    if ov.position == "left":
        restx = f"{MARGIN_X}"
    elif ov.position == "center":
        restx = "((W-w)/2)"
    else:
        restx = f"(W-w-{MARGIN_X})"
    yb = f"(H-h-{MARGIN_Y})"

    if not ov.slide_in:
        return (restx, yb)

    enter = ov.enter_from
    if enter == "left":
        x, y = f"(-w+(({restx})+w)*{prog})", yb
    elif enter == "right":
        x, y = f"(W-(W-({restx}))*{prog})", yb
    elif enter == "top":
        x, y = restx, f"(-h+(({yb})+h)*{prog})"
    else:  # bottom
        x, y = restx, f"(H-(H-({yb}))*{prog})"

    # saída deslizando (apenas entradas horizontais)
    if ov.exit == "slide" and enter in ("left", "right"):
        po = f"min(max((t-({ei}-{slide}))/{slide}\\,0)\\,1)"
        if enter == "right":
            xo = f"(({restx})+(W-({restx}))*{po})"
        else:
            xo = f"(({restx})-(({restx})+w)*{po})"
        x = f"if(gt(t\\,{ei}-{slide})\\,{xo}\\,{x})"
    return (x, y)


# ----------------------------------------------------------------------------
# Filtergraph
# ----------------------------------------------------------------------------
def _montage_base(project: Project, duration: float, trailer_dur: Optional[float]) -> str:
    """Base 'cover' em MONTAGEM: costura vários trechos do vídeo (corte a cada
    `cut_seconds`) espalhados pelo trailer, pulando o começo (video_start)."""
    W, H, fps = project.width, project.height, project.fps
    L = max(1.0, project.cut_seconds)
    avail = (trailer_dur - project.video_start) if trailer_dur else duration
    n = max(1, math.ceil(duration / L))
    win_end = max(L, avail - L)
    starts = [0.0] if n == 1 else [i * win_end / (n - 1) for i in range(n)]
    p = ["[0:v]split=%d%s" % (n, "".join(f"[c{i}]" for i in range(n)))]
    for i, si in enumerate(starts):
        p.append(f"[c{i}]trim=start={si:.2f}:duration={L},setpts=PTS-STARTPTS,fps={fps},"
                 f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[seg{i}]")
    p.append("".join(f"[seg{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[base]")
    return ";".join(p)


def _build_filter_complex(project: Project, duration: float, subs_name: Optional[str],
                          img_base: int, sfx_list: List[Tuple[int, int]],
                          trailer_dur: Optional[float] = None) -> str:
    W, H, fps = project.width, project.height, project.fps
    parts: List[str] = []

    # 1) base vertical
    if project.layout == "cover" and project.cut_seconds and project.cut_seconds > 0:
        parts.append(_montage_base(project, duration, trailer_dur))   # cortes dinâmicos
    elif project.layout == "blurred":
        parts.append(
            f"[0:v]fps={fps},split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bgb];"
            f"[fg]scale={W}:-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[base]"
        )
    else:
        parts.append(
            f"[0:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1[base]"
        )
    cur = "base"

    # 2) legendas (arquivo .ass já pronto: estático convertido ou karaokê)
    if subs_name:
        parts.append(f"[{cur}]ass={subs_name}[subd]")
        cur = "subd"

    # 3) imagens (personagem), cada uma numa camada
    for i, ov in enumerate(project.overlays):
        idx = img_base + i
        ow = max(2, int(ov.width_frac * W))
        parts.append(f"[{idx}:v]scale={ow}:-2[img{i}]")
        x, y = _overlay_xy(ov, project.slide_seconds, project.easing)
        enable = f"between(t\\,{ov.start}\\,{ov.end})"
        parts.append(f"[{cur}][img{i}]overlay=x='{x}':y='{y}':enable='{enable}'[v{i}]")
        cur = f"v{i}"
    parts.append(f"[{cur}]null[vout]")

    # 4) áudio: narração + música + whooshes
    parts.append(f"[1:a]aresample=48000,volume={project.narration_volume}[na]")
    amix = ["[na]"]
    if project.music_path:
        parts.append(f"[2:a]aresample=48000,atrim=0:{duration:.3f},"
                     f"asetpts=N/SR/TB,volume={project.music_volume}[ma]")
        amix.append("[ma]")
    for k, (idx, ms) in enumerate(sfx_list):
        parts.append(f"[{idx}:a]aresample=48000,volume={SFX_VOLUME},adelay={ms}|{ms}[sfx{k}]")
        amix.append(f"[sfx{k}]")
    if len(amix) == 1:
        parts.append("[na]anull[aout]")
    else:
        parts.append("".join(amix) +
                     f"amix=inputs={len(amix)}:duration=first:normalize=0,alimiter=limit=0.95[aout]")

    return ";".join(parts)


# ----------------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------------
def _resolve_sfx(project: Project) -> List[Tuple[int, Optional[str]]]:
    """Para cada overlay, decide o som de entrada: overlay.sfx ou overlay_sfx ciclado."""
    out = []
    for i, ov in enumerate(project.overlays):
        sfx = ov.sfx
        if not sfx and project.overlay_sfx:
            sfx = project.overlay_sfx[i % len(project.overlay_sfx)]
        out.append((i, sfx))
    return out


def render(project: Project) -> str:
    """Renderiza o vídeo final. Retorna o caminho do MP4 gerado."""
    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("FFmpeg não encontrado no PATH. Veja o README.")
    os.makedirs(project.output_dir, exist_ok=True)

    duration = project.duration or ffmpeg_utils.get_duration(project.narration_path)
    if not duration or duration <= 0:
        raise RuntimeError("Não foi possível determinar a duração final (narração?).")

    # --- legendas: descobrir/gerar a .ass a ser queimada ---
    ass_path = os.path.splitext(project.subtitles_path)[0] + ".ass"
    subs_name = subs_cwd = None
    if project.subtitles_enabled:
        if project.subtitles_mode == "karaoke":
            if os.path.exists(ass_path):
                subs_name, subs_cwd = os.path.basename(ass_path), os.path.dirname(ass_path)
            else:
                log.warning("modo karaokê, mas .ass não encontrada (%s). Rode 'transcribe' "
                            "antes. Seguindo SEM legenda.", ass_path)
        else:
            if os.path.exists(project.subtitles_path):
                srt_to_ass(project.subtitles_path, ass_path, project.subtitle_style,
                           project.width, project.height)
                subs_name, subs_cwd = os.path.basename(ass_path), os.path.dirname(ass_path)
            else:
                log.warning("Legendas ligadas, mas .srt não encontrada (%s). Rode 'transcribe' "
                            "antes. Seguindo SEM legenda.", project.subtitles_path)

    # --- inputs: vídeo, narração, [música], imagens, [whooshes] ---
    inputs: List[str] = ["-ss", f"{project.video_start:.3f}", "-i", project.video_path]  # 0
    inputs += ["-i", project.narration_path]                                              # 1
    if project.music_path:
        inputs += ["-i", project.music_path]                                              # 2
    img_base = 2 + (1 if project.music_path else 0)
    for ov in project.overlays:
        inputs += ["-loop", "1", "-framerate", str(project.fps),
                   "-t", f"{duration:.3f}", "-i", ov.path]

    sfx_resolved = _resolve_sfx(project)
    sfx_list: List[Tuple[int, int]] = []
    sfx_idx = img_base + len(project.overlays)
    for i, sfx in sfx_resolved:
        if sfx and os.path.exists(sfx):
            inputs += ["-i", sfx]
            sfx_list.append((sfx_idx, int(project.overlays[i].start * 1000)))
            sfx_idx += 1
        elif sfx:
            log.warning("SFX não encontrado (ignorado): %s", sfx)

    trailer_dur = ffmpeg_utils.get_duration(project.video_path)
    filter_complex = _build_filter_complex(project, duration, subs_name, img_base, sfx_list,
                                           trailer_dur=trailer_dur)

    args = [
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{duration:.3f}",
        "-r", str(project.fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        project.output_path,
    ]

    log.info("Renderizando '%s' (%s, %dx%d, %.2fs, %d imagens, %d whooshes, legenda=%s)...",
             project.output_name, project.layout, project.width, project.height, duration,
             len(project.overlays), len(sfx_list),
             project.subtitles_mode if subs_name else "off")
    ffmpeg_utils.run_ffmpeg(args, cwd=subs_cwd)
    log.info("Vídeo final gerado: %s", project.output_path)
    return project.output_path
