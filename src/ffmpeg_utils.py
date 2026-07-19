"""Wrappers finos em volta do FFmpeg / FFprobe.

Mantém todo o contato com o FFmpeg num só lugar, para o resto do código
não precisar montar subprocessos na mão.
"""

import json
import os
import shutil
import subprocess
from typing import List, Optional

from .logging_utils import get_logger

log = get_logger()


class FFmpegError(RuntimeError):
    """Erro ao executar FFmpeg/FFprobe."""


def ffmpeg_available() -> bool:
    """True se o binário `ffmpeg` está no PATH."""
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def run_ffmpeg(args: List[str], cwd: Optional[str] = None) -> None:
    """Executa `ffmpeg` com os argumentos dados. Levanta FFmpegError em falha."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    log.info("Executando FFmpeg (%d args)...", len(args))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")   # ffmpeg não emite utf-8 puro no Windows
    if proc.returncode != 0:
        raise FFmpegError(
            "FFmpeg falhou (código %d).\nComando: %s\n\nSaída de erro:\n%s"
            % (proc.returncode, " ".join(cmd), (proc.stderr or "").strip())
        )


def ffprobe_json(path: str) -> dict:
    """Retorna metadados do arquivo via ffprobe (streams + format) como dict."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration,size",
        "-of", "json", path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError("ffprobe falhou para %s:\n%s" % (path, (proc.stderr or "").strip()))
    return json.loads(proc.stdout or "{}")


def get_duration(path: str) -> Optional[float]:
    """Duração do arquivo (segundos) ou None se indisponível."""
    try:
        data = ffprobe_json(path)
        dur = data.get("format", {}).get("duration")
        return float(dur) if dur is not None else None
    except Exception:
        return None


def has_audio(path: str) -> bool:
    """True se o arquivo tem pelo menos uma stream de áudio."""
    try:
        data = ffprobe_json(path)
        return any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    except Exception:
        return False


def get_video_info(path: str) -> dict:
    """Retorna {width, height, fps, duration, has_audio, size_bytes} do vídeo."""
    data = ffprobe_json(path)
    info = {"width": None, "height": None, "fps": None,
            "duration": None, "has_audio": False, "size_bytes": None}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and info["width"] is None:
            info["width"] = s.get("width")
            info["height"] = s.get("height")
            rate = s.get("r_frame_rate", "0/1")
            try:
                num, den = rate.split("/")
                info["fps"] = round(float(num) / float(den), 2) if float(den) else None
            except Exception:
                info["fps"] = None
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    fmt = data.get("format", {})
    if fmt.get("duration") is not None:
        info["duration"] = float(fmt["duration"])
    if fmt.get("size") is not None:
        info["size_bytes"] = int(fmt["size"])
    elif os.path.exists(path):
        info["size_bytes"] = os.path.getsize(path)
    return info


def extract_frame(video_path: str, time_s: float, out_path: str) -> None:
    """Extrai 1 frame do vídeo no instante `time_s` para `out_path` (PNG)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    run_ffmpeg(["-ss", f"{max(0.0, time_s):.3f}", "-i", video_path,
                "-frames:v", "1", out_path])
