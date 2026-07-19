"""Validação do projeto antes de renderizar.

Produz um relatório claro no terminal:
- lista dos arquivos encontrados / faltando;
- problemas de tempos de overlays;
- checagem do FFmpeg;
- criação das pastas de output.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from . import ffmpeg_utils
from .logging_utils import title, line
from .models import Project


@dataclass
class ValidationReport:
    checks: List[tuple] = field(default_factory=list)   # (rótulo, ok: bool, detalhe)
    problems: List[str] = field(default_factory=list)

    def add(self, label: str, ok: bool, detail: str = "") -> None:
        self.checks.append((label, ok, detail))
        if not ok:
            self.problems.append(f"{label}: {detail}" if detail else label)

    @property
    def ok(self) -> bool:
        return len(self.problems) == 0


def _check_file(report: ValidationReport, label: str, path: Optional[str]) -> None:
    if not path:
        report.add(label, False, "caminho não informado")
    elif os.path.exists(path):
        report.add(label, True, path)
    else:
        report.add(label, False, f"não encontrado ({path})")


def validate_project(project: Project, create_dirs: bool = True) -> ValidationReport:
    """Valida o projeto e devolve um ValidationReport."""
    r = ValidationReport()

    # 1) FFmpeg / FFprobe instalados
    r.add("FFmpeg instalado", ffmpeg_utils.ffmpeg_available(),
          "" if ffmpeg_utils.ffmpeg_available() else "instale o FFmpeg (ver README)")
    r.add("FFprobe instalado", ffmpeg_utils.ffprobe_available(),
          "" if ffmpeg_utils.ffprobe_available() else "instale o FFmpeg (inclui ffprobe)")

    # 2) Arquivos principais
    _check_file(r, "vídeo principal", project.video_path)
    _check_file(r, "narração", project.narration_path)
    if project.music_path:
        _check_file(r, "música", project.music_path)
    else:
        r.add("música", True, "(sem música — opcional)")

    # 3) Imagens dos overlays
    for ov in project.overlays:
        _check_file(r, f"imagem {ov.id}", ov.path)

    # 4) Duração final de referência (narração ou 'duration' do JSON)
    final_duration = project.duration or ffmpeg_utils.get_duration(project.narration_path)
    if not final_duration or final_duration <= 0:
        r.add("duração final", False, "não foi possível determinar a duração (narração?)")
        final_duration = None
    else:
        r.add("duração final", True, f"{final_duration:.2f}s")

    # 5) Tempos dos overlays
    for ov in project.overlays:
        if ov.end <= ov.start:
            r.add(f"tempos {ov.id}", False,
                  f"fim ({ov.end}) deve ser maior que início ({ov.start})")
        elif ov.start < 0:
            r.add(f"tempos {ov.id}", False, f"início negativo ({ov.start})")
        elif final_duration and ov.end > final_duration + 0.05:
            r.add(f"tempos {ov.id}", False,
                  f"fim ({ov.end}s) ultrapassa a duração final ({final_duration:.2f}s)")
        else:
            r.add(f"tempos {ov.id}", True, f"{ov.start:.2f}s → {ov.end:.2f}s")

    # 6) Layout válido
    r.add("layout", project.layout in ("cover", "blurred"),
          "" if project.layout in ("cover", "blurred") else f"'{project.layout}' inválido (use cover|blurred)")

    # 7) Pastas de output
    if create_dirs:
        try:
            os.makedirs(project.output_dir, exist_ok=True)
            os.makedirs(project.review_frames_dir, exist_ok=True)
            r.add("pasta de output", True, project.output_dir)
        except OSError as e:
            r.add("pasta de output", False, str(e))
    else:
        r.add("pasta de output", os.path.isdir(project.output_dir), project.output_dir)

    return r


def print_report(project: Project, r: ValidationReport) -> None:
    """Imprime o relatório de validação no formato pedido."""
    title(f"Projeto: {project.name}")
    line("Arquivos encontrados:")
    for label, ok, detail in r.checks:
        mark = "OK" if ok else "FALHOU"
        extra = f" — {detail}" if detail else ""
        line(f"  * {label}: {mark}{extra}")
    line("")
    line("Problemas:")
    if r.problems:
        for p in r.problems:
            line(f"  * {p}")
    else:
        line("  * Nenhum problema encontrado.")
    line("")
