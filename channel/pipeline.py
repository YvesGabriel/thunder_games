#!/usr/bin/env python3
"""Orquestrador do canal — junta as peças num fluxo contínuo.

Comandos: new, narrate, plan, auto, publish, candidatos, pick.
A montagem do roteiro fica em channel/roteiro.py; os utilitários em channel/common.py.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

# stdout/stderr em utf-8 (senão o console cp1252 do Windows quebra ao imprimir → ou emojis)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import settings
from services import voicebox
from channel import roteiro
from channel.common import _abs, load_plano, log, BIBLIOTECA

HERE = settings.ROOT


# ---------------------------------------------------------------------------
# new — esqueleto de um vídeo novo
# ---------------------------------------------------------------------------
def cmd_new(args):
    slug = args.name
    project_dir = os.path.join(HERE, "projects", slug)
    os.makedirs(os.path.join(project_dir, "assets"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "output"), exist_ok=True)

    plano = {
        "project": slug,
        "output_name": "final.mp4",
        "game": args.game or slug,
        "video": "assets/video.mp4",
        "video_start": 10.0,
        "narration": "assets/narration.wav",
        "narration_text": "assets/narration.txt",
        "music_mood": args.mood,
        "music_library": os.path.join(BIBLIOTECA, "Musicas"),
        "whooshes_dir": os.path.join(BIBLIOTECA, "Efeitos"),
        "voicebox": {"profile": settings.VOICE_PROFILE_NAME, "profile_id": settings.VOICE_PROFILE_ID, "language": "pt"},
        # o Claude escolhe as expressões junto do roteiro (nomes da Biblioteca/Personagem);
        # se ficar vazio, o sistema sorteia da biblioteca automaticamente.
        "expressions": [],
        "publish": {
            "title": f"{args.game or slug} #Shorts",
            "description": ("[gancho]\n\n[o que é o jogo e por que vale]\n\n"
                            "🎮 {game}\n\n👉 Segue o Thunder Games pra mais achados de games!\n"
                            "📸 Instagram: {instagram}\n🎵 TikTok: {tiktok}\n\n"
                            "#Shorts #games #jogosindie"),
            "tags": [args.game or slug, "games", "jogos", "shorts"],
            "comment": "[comentário pessoal + pergunta pra engajar]",
            "instagram": "@thunder_games_8",
            "tiktok": "@thunder_games_8",
        },
    }
    with open(os.path.join(project_dir, "plano.json"), "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    log(f"Projeto criado: projects/{slug}")
    log("Agora: 1) coloque o vídeo em assets/video.mp4 (ou rode capture.py);")
    log("       2) escreva o roteiro em assets/narration.txt;")
    log("       3) ajuste o plano.json (clima da música, expressões, publish);")
    log("       4) rode: narrate -> auto -> publish.")
    return 0


# ---------------------------------------------------------------------------
# narrate — VoiceBox (via services.voicebox)
# ---------------------------------------------------------------------------
def cmd_narrate(project_dir, plano):
    text_path = _abs(project_dir, plano.get("narration_text", "assets/narration.txt"))
    out_wav = _abs(project_dir, plano.get("narration", "assets/narration.wav"))
    if not os.path.exists(text_path):
        raise FileNotFoundError(f"Texto da narração não encontrado: {text_path}")
    text = open(text_path, encoding="utf-8").read().strip()
    vb = plano.get("voicebox", {})
    profile_id = voicebox.resolve_profile_id(vb)
    audio = voicebox.gerar(text, profile_id, language=vb.get("language", "pt"),
                           engine=vb.get("engine"), instruct=vb.get("instruct"), on_log=log)
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)
    open(out_wav, "wb").write(audio)
    log(f"Narração salva: {out_wav}")
    return 0


# ---------------------------------------------------------------------------
# auto — dispara a edição quando tudo está pronto
# ---------------------------------------------------------------------------
def missing_prerequisites(project_dir, plano):
    faltando = []
    for nome, rel in (("vídeo", plano.get("video")), ("narração", plano.get("narration"))):
        if not rel or not os.path.exists(_abs(project_dir, rel)):
            faltando.append(nome)
    try:
        if not os.path.exists(roteiro.resolve_music(project_dir, plano)):
            faltando.append("música")
    except Exception:
        faltando.append("música")
    # expressões não bloqueiam a edição (o build_roteiro resolve/sorteia).
    # Só avisamos se a pasta de personagens estiver completamente vazia.
    if not roteiro._personagem_imgs():
        faltando.append("personagens (Biblioteca/Personagem vazia)")
    return faltando


def run_editor(project_dir):
    log("Pré-requisitos OK → iniciando edição...")
    return subprocess.run([sys.executable, os.path.join(HERE, "main.py"), "all",
                           "--project", project_dir], cwd=HERE).returncode


def _copy_final(project_dir, plano):
    """Copia o vídeo final pra uma pasta fácil (Canal de Games/Videos prontos)."""
    src = os.path.join(project_dir, "output", plano.get("output_name", "final.mp4"))
    if not os.path.exists(src):
        return
    dest_dir = os.path.join(os.path.dirname(HERE), "Videos prontos")
    os.makedirs(dest_dir, exist_ok=True)
    name = (plano.get("game") or plano.get("project") or "video")
    name = "".join(c if c not in ':/\\?*"<>|' else "-" for c in name)
    dest = os.path.join(dest_dir, f"{name}.mp4")
    shutil.copyfile(src, dest)
    log(f"Vídeo final em: {dest}")


def cmd_auto(project_dir, plano, watch=False, interval=10):
    while True:
        faltando = missing_prerequisites(project_dir, plano)
        if not faltando:
            roteiro.build_roteiro(project_dir, plano)   # sempre regenera (casa com a narração atual)
            code = run_editor(project_dir)
            if code == 0:
                _copy_final(project_dir, plano)
            return code
        log("Aguardando: " + ", ".join(faltando))
        if not watch:
            log("Use --watch para esperar os arquivos aparecerem.")
            return 1
        time.sleep(interval)


def cmd_candidatos(project_dir, plano):
    """Edita UMA versão por trailer em base/ -> candidatos/candidatoN.mp4."""
    bases = sorted(glob.glob(os.path.join(project_dir, "base", "*.mp4")))
    if not bases:
        raise FileNotFoundError("Nenhum trailer em base/. Rode o capture.py antes.")
    falt = [x for x in missing_prerequisites(project_dir, plano) if x != "vídeo"]
    if falt:
        raise RuntimeError("Faltando (voz/música/imagens): " + ", ".join(falt))
    cand_dir = os.path.join(project_dir, "candidatos")
    os.makedirs(cand_dir, exist_ok=True)
    ok = 0
    for i, bv in enumerate(bases, 1):
        rel = os.path.relpath(bv, project_dir).replace("\\", "/")
        log(f"Editando candidato {i}/{len(bases)} (base: {os.path.basename(bv)})...")
        roteiro.build_roteiro(project_dir, plano, video_path=rel, output_name=f"candidato{i}.mp4")
        if run_editor(project_dir) == 0:
            src = os.path.join(project_dir, "output", f"candidato{i}.mp4")
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(cand_dir, f"candidato{i}.mp4"))
                ok += 1
    log(f"{ok} candidato(s) gerado(s) em: {cand_dir}")
    return 0 if ok else 1


def cmd_pick(project_dir, plano, num):
    """Marca o candidato escolhido como o vídeo PRONTO (na pasta do jogo)."""
    src = os.path.join(project_dir, "candidatos", f"candidato{num}.mp4")
    if not os.path.exists(src):
        raise FileNotFoundError(f"Candidato {num} não encontrado: {src}")
    game = plano.get("game") or plano.get("project", "video")
    safe = "".join(c if c not in ':/\\?*"<>|' else "-" for c in game)
    dest = os.path.join(project_dir, f"PRONTO - {safe}.mp4")
    shutil.copyfile(src, dest)
    vp = os.path.join(os.path.dirname(HERE), "Videos prontos")
    os.makedirs(vp, exist_ok=True)
    shutil.copyfile(src, os.path.join(vp, f"PRONTO - {safe}.mp4"))
    log(f"Vídeo pronto: {dest}")
    return 0


# ---------------------------------------------------------------------------
# publish — sobe no YouTube (via services.youtube_upload)
# ---------------------------------------------------------------------------
def cmd_publish(project_dir, plano, privacy="private"):
    pub = plano.get("publish", {})
    game = plano.get("game", plano.get("project", ""))
    video = _abs(project_dir, os.path.join("output", plano.get("output_name", "final.mp4")))
    if not os.path.exists(video):
        raise FileNotFoundError(f"Vídeo final não encontrado: {video}. Rode `auto` antes.")

    desc = pub.get("description", "").format(game=game, instagram=pub.get("instagram", ""),
                                             tiktok=pub.get("tiktok", ""))
    open(os.path.join(project_dir, "output", "descricao.txt"), "w", encoding="utf-8").write(desc)
    comment = pub.get("comment", "").format(game=game)
    open(os.path.join(project_dir, "output", "comentario.txt"), "w", encoding="utf-8").write(comment)

    from services import youtube_upload
    log(f"Publicando no YouTube (privacidade: {privacy})...")
    code = youtube_upload.upload(video, pub.get("title", game), description=desc,
                                 tags=pub.get("tags", []), privacy=privacy, on_log=log)
    if code == 0:
        log("Publicado. Comentário pra FIXAR manualmente no vídeo:")
        print("\n  " + comment + "\n")
    return code


# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Orquestrador do canal Thunder Games.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new"); sp.add_argument("--name", required=True)
    sp.add_argument("--game", default=""); sp.add_argument("--mood", default="adventure")

    for name in ("narrate", "plan", "auto", "publish", "candidatos", "pick"):
        sp = sub.add_parser(name); sp.add_argument("--project", required=True)
        if name == "auto":
            sp.add_argument("--watch", action="store_true")
        if name == "publish":
            sp.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
        if name == "pick":
            sp.add_argument("--num", type=int, required=True, help="número do candidato escolhido")

    args = p.parse_args()
    if args.cmd == "new":
        return cmd_new(args)

    project_dir = os.path.abspath(args.project)
    plano = load_plano(project_dir)
    if args.cmd == "narrate":
        return cmd_narrate(project_dir, plano)
    if args.cmd == "plan":
        roteiro.build_roteiro(project_dir, plano); return 0
    if args.cmd == "auto":
        return cmd_auto(project_dir, plano, watch=args.watch)
    if args.cmd == "candidatos":
        return cmd_candidatos(project_dir, plano)
    if args.cmd == "pick":
        return cmd_pick(project_dir, plano, args.num)
    if args.cmd == "publish":
        return cmd_publish(project_dir, plano, privacy=args.privacy)


if __name__ == "__main__":
    sys.exit(main())
