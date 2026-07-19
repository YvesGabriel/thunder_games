"""Utilitários compartilhados da camada de canal (log, caminhos, ffprobe)."""

import json
import os
import subprocess

from config import settings

BIBLIOTECA = settings.BIBLIOTECA


def log(msg):
    print(f"[pipeline] {msg}")


def _abs(base, rel):
    if not rel:
        return rel
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(base, rel))


def load_plano(project_dir):
    path = os.path.join(project_dir, "plano.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"plano.json não encontrado em {project_dir}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ffprobe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return None
