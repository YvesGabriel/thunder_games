"""Inspeção do vídeo final + extração de frames de revisão.

Gera um relatório (resolução, duração, fps, tamanho, áudio, se bate com a
narração, lista de overlays) e extrai frames nos momentos em que cada imagem
deveria aparecer — pensado para futura revisão visual por uma IA (via MCP).
"""

import os
from typing import Optional

from . import ffmpeg_utils
from .logging_utils import get_logger, title, line
from .models import Project

log = get_logger()


def _fmt_size(num_bytes: Optional[int]) -> str:
    if not num_bytes:
        return "?"
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.2f} MB"


def extract_review_frames(project: Project) -> list:
    """Extrai frames no início/meio/fim de cada overlay a partir do vídeo final.

    Salva em output/review_frames/<id>_<pos>.png e retorna a lista de caminhos.
    """
    out_video = project.output_path
    if not os.path.exists(out_video):
        raise FileNotFoundError(f"Vídeo final não encontrado: {out_video}")

    os.makedirs(project.review_frames_dir, exist_ok=True)
    saved = []
    for ov in project.overlays:
        mid = (ov.start + ov.end) / 2.0
        near_end = max(ov.start, ov.end - 0.15)
        moments = {"inicio": ov.start + 0.05, "meio": mid, "fim": near_end}
        for pos, t in moments.items():
            out_path = os.path.join(project.review_frames_dir, f"{ov.id}_{pos}.png")
            try:
                ffmpeg_utils.extract_frame(out_video, t, out_path)
                saved.append(out_path)
            except Exception as e:
                log.warning("Falha ao extrair frame %s de %s: %s", pos, ov.id, e)
    return saved


def inspect_output(project: Project, extract_frames: bool = True) -> dict:
    """Inspeciona o vídeo final e imprime o relatório. Retorna um dict com os dados."""
    out_video = project.output_path
    if not os.path.exists(out_video):
        raise FileNotFoundError(
            f"Vídeo final não encontrado: {out_video}. Rode 'render' antes."
        )

    info = ffmpeg_utils.get_video_info(out_video)
    narration_dur = ffmpeg_utils.get_duration(project.narration_path)
    dur = info.get("duration")
    matches = (
        narration_dur is not None and dur is not None
        and abs(dur - narration_dur) <= 1.0
    )

    frames = extract_review_frames(project) if extract_frames else []

    # --- relatório ---
    title(f"Inspeção: {project.name}")
    line(f"  * arquivo: {out_video}")
    line(f"  * resolução: {info.get('width')}x{info.get('height')}")
    line(f"  * duração: {dur:.2f}s" if dur else "  * duração: ?")
    line(f"  * fps: {info.get('fps')}")
    line(f"  * tamanho: {_fmt_size(info.get('size_bytes'))}")
    line(f"  * tem áudio: {'sim' if info.get('has_audio') else 'NÃO'}")
    if narration_dur:
        line(f"  * duração da narração: {narration_dur:.2f}s "
             f"({'bate' if matches else 'NÃO bate'} com o vídeo)")
    line("")
    line("Overlays esperados:")
    if project.overlays:
        for ov in project.overlays:
            pos = {"left": "esquerda", "right": "direita", "center": "centro"}.get(ov.position, ov.position)
            line(f"  * {ov.id}: {ov.start:.2f}s → {ov.end:.2f}s "
                 f"({pos}, largura {int(ov.width_frac*100)}%)")
    else:
        line("  * (nenhum)")
    line("")
    line(f"Frames de revisão extraídos: {len(frames)}")
    if frames:
        line(f"  em: {project.review_frames_dir}")
    line("")

    return {
        "resolution": (info.get("width"), info.get("height")),
        "duration": dur,
        "fps": info.get("fps"),
        "size_bytes": info.get("size_bytes"),
        "has_audio": info.get("has_audio"),
        "duration_matches_narration": matches,
        "overlays": [(ov.id, ov.start, ov.end) for ov in project.overlays],
        "review_frames": frames,
    }
