#!/usr/bin/env python3
"""video_auto_editor — CLI.

Comandos:
  validate    valida os arquivos e o roteiro.json (relatório no terminal)
  transcribe  gera a legenda .srt a partir da narração (Whisper)
  render      renderiza o vídeo final em MP4
  inspect     inspeciona o vídeo final e extrai frames de revisão
  all         validate -> transcribe -> render -> inspect

Uso:
  python main.py <comando> --project projects/video_001
  (ou aponte direto para o JSON: --roteiro projects/video_001/roteiro.json)

Exemplos:
  python main.py validate  --project projects/video_001
  python main.py transcribe --project projects/video_001 --model base
  python main.py render    --project projects/video_001
  python main.py inspect   --project projects/video_001
  python main.py all       --project projects/video_001
"""

import argparse
import os
import sys

# stdout/stderr em utf-8 (console cp1252 do Windows quebra ao imprimir → ou emojis)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src import config, render as render_mod, transcription, validation
from src.inspect_output import inspect_output
from src.logging_utils import get_logger

log = get_logger()


def _resolve_roteiro(args) -> str:
    """Descobre o caminho do roteiro.json a partir de --project ou --roteiro."""
    if args.roteiro:
        return args.roteiro
    if args.project:
        return os.path.join(args.project, "roteiro.json")
    log.error("Informe --project <pasta> ou --roteiro <arquivo.json>.")
    sys.exit(2)


def _load(args):
    path = _resolve_roteiro(args)
    try:
        return config.load_project(path)
    except config.ConfigError as e:
        log.error("Erro no roteiro.json: %s", e)
        sys.exit(2)


def cmd_validate(args) -> int:
    project = _load(args)
    report = validation.validate_project(project, create_dirs=True)
    validation.print_report(project, report)
    return 0 if report.ok else 1


def cmd_transcribe(args) -> int:
    project = _load(args)
    try:
        if project.subtitles_mode == "karaoke":
            # Legenda karaokê: gera a .ass palavra a palavra a partir do texto do roteiro.
            if not project.subtitles_text:
                log.error("O modo karaokê exige o texto do roteiro (subtitles.text ou text_path).")
                return 1
            ass_path = os.path.splitext(project.subtitles_path)[0] + ".ass"
            transcription.karaoke_ass_from_script(
                project.subtitles_text, project.narration_path, ass_path,
                project.subtitle_style, project.width, project.height,
                align=project.subtitles_align, model_size=args.model, language=args.language,
            )
        elif project.subtitles_source == "script" and project.subtitles_text:
            # Fonte recomendada: texto do roteiro (correto) + tempo do áudio.
            transcription.subtitles_from_script(
                project.subtitles_text, project.narration_path, project.subtitles_path,
                align=project.subtitles_align, model_size=args.model, language=args.language,
            )
        else:
            if project.subtitles_source == "script":
                log.warning("source='script' mas sem texto ('text'/'text_path'); "
                            "transcrevendo o áudio como alternativa.")
            transcription.generate_subtitles(
                project.narration_path, project.subtitles_path,
                model_size=args.model, language=args.language,
            )
    except Exception as e:
        log.error("%s", e)
        return 1
    return 0


def cmd_render(args) -> int:
    project = _load(args)
    # valida antes para não renderizar com problemas
    report = validation.validate_project(project, create_dirs=True)
    if not report.ok:
        validation.print_report(project, report)
        log.error("Corrija os problemas acima antes de renderizar.")
        return 1
    try:
        render_mod.render(project)
    except Exception as e:
        log.error("Falha na renderização: %s", e)
        return 1
    return 0


def cmd_inspect(args) -> int:
    project = _load(args)
    try:
        inspect_output(project, extract_frames=not args.no_frames)
    except Exception as e:
        log.error("%s", e)
        return 1
    return 0


def cmd_all(args) -> int:
    for step in (cmd_validate, cmd_transcribe, cmd_render, cmd_inspect):
        code = step(args)
        if code != 0:
            log.error("Etapa '%s' falhou (código %d). Interrompendo.", step.__name__, code)
            return code
    log.info("Pipeline completo com sucesso.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pipeline programático de edição de vídeos verticais.")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--project", help="pasta do projeto (contém roteiro.json)")
        sp.add_argument("--roteiro", help="caminho direto para o roteiro.json")

    sp = sub.add_parser("validate", help="valida arquivos e roteiro")
    add_common(sp); sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("transcribe", help="gera legenda .srt da narração")
    add_common(sp)
    sp.add_argument("--model", default="base", help="tamanho do modelo Whisper (tiny/base/small/medium)")
    sp.add_argument("--language", default="pt", help="idioma da narração")
    sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("render", help="renderiza o vídeo final")
    add_common(sp); sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("inspect", help="inspeciona o vídeo e extrai frames de revisão")
    add_common(sp)
    sp.add_argument("--no-frames", action="store_true", help="não extrair frames de revisão")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("all", help="validate + transcribe + render + inspect")
    add_common(sp)
    sp.add_argument("--model", default="base", help="modelo Whisper para o transcribe")
    sp.add_argument("--language", default="pt", help="idioma da narração")
    sp.add_argument("--no-frames", action="store_true", help="não extrair frames de revisão")
    sp.set_defaults(func=cmd_all)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
