#!/usr/bin/env python3
"""Orquestrador do canal — junta as peças num fluxo contínuo.

Comandos:
  new      cria a pasta de um vídeo novo (esqueleto + plano.json)
  narrate  gera a narração no VoiceBox a partir do texto do roteiro
  plan     gera o roteiro.json no padrão aprovado (karaokê + apresentador + whoosh)
  auto     quando os pré-requisitos existem, dispara a edição sozinho (--watch espera)
  publish  sobe o vídeo final no YouTube (título + descrição + #Shorts) e mostra o comentário

Fluxo típico de um vídeo:
  python pipeline.py new     --name core_keeper --game "Core Keeper"
  # (capta o trailer -> assets/video.mp4 ; escreve o roteiro -> assets/narration.txt)
  python pipeline.py narrate --project projects/core_keeper
  python pipeline.py auto    --project projects/core_keeper
  python pipeline.py publish --project projects/core_keeper --privacy public
"""

import argparse
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# stdout/stderr em utf-8 (senão o console cp1252 do Windows quebra ao imprimir → ou emojis)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BIBLIOTECA = os.path.join(os.path.dirname(HERE), "Biblioteca")
VOICEBOX_URL = "http://127.0.0.1:17493"

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


def log(msg):
    print(f"[pipeline] {msg}")


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
        "voicebox": {"profile": "Yves", "profile_id": "01d97944-3ffc-48ff-9a3a-704b2ccf434b", "language": "pt"},
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
# narrate — VoiceBox
# ---------------------------------------------------------------------------
def _vb_profiles():
    """Lista os perfis de voz do VoiceBox (GET /profiles)."""
    with urllib.request.urlopen(f"{VOICEBOX_URL}/profiles", timeout=30) as r:
        data = json.loads(r.read())
    if isinstance(data, list):
        return data
    for k in ("profiles", "data", "items"):
        if isinstance(data.get(k), list):
            return data[k]
    return []


def _resolve_profile_id(vb):
    """Descobre o profile_id: usa o informado, ou acha pelo nome em /profiles."""
    if vb.get("profile_id"):
        return vb["profile_id"]
    name = vb.get("profile", "")
    try:
        profs = _vb_profiles()
    except Exception as e:
        raise RuntimeError(f"Não consegui listar os perfis do VoiceBox: {e}")
    for p in profs:
        if str(p.get("name", "")).strip().lower() == name.strip().lower():
            return p.get("id") or p.get("profile_id")
    nomes = [p.get("name") for p in profs]
    raise RuntimeError(
        f"Perfil '{name}' não encontrado no VoiceBox. Disponíveis: {nomes}\n"
        "Ajuste 'voicebox.profile' (nome exato) ou 'voicebox.profile_id' no plano.json.")


def _vb_history(req_timeout=15):
    with urllib.request.urlopen(f"{VOICEBOX_URL}/history", timeout=req_timeout) as r:
        d = json.loads(r.read())
    return d.get("items", []) if isinstance(d, dict) else d


_DONE = {"completed", "done", "success", "finished"}


def _wait_generation(gen_id, timeout=420, interval=3):
    """Espera a geração terminar e retorna o caminho do áudio (audio_path).

    Enquanto o VoiceBox carrega o modelo/gera, o servidor fica ocupado e o
    /history pode dar timeout — nesses casos a gente ignora e tenta de novo.
    """
    t0 = time.time()
    last_log = 0
    while time.time() - t0 < timeout:
        try:
            for it in _vb_history():
                if it.get("id") == gen_id:
                    if it.get("error"):
                        raise RuntimeError(f"VoiceBox falhou: {it['error']}")
                    if str(it.get("status", "")).lower() in _DONE:
                        return True
                    break
        except RuntimeError:
            raise
        except Exception:
            pass  # servidor ocupado gerando; segue tentando
        if time.time() - last_log > 15:
            log(f"  ...ainda gerando ({int(time.time()-t0)}s)")
            last_log = time.time()
        time.sleep(interval)
    raise RuntimeError(
        "Tempo esgotado esperando o VoiceBox. A fila pode ter travado — "
        "FECHE e reabra o app VoiceBox e rode o `narrate` UMA vez só.")


def cmd_narrate(project_dir, plano):
    text_path = _abs(project_dir, plano.get("narration_text", "assets/narration.txt"))
    out_wav = _abs(project_dir, plano.get("narration", "assets/narration.wav"))
    if not os.path.exists(text_path):
        raise FileNotFoundError(f"Texto da narração não encontrado: {text_path}")
    text = open(text_path, encoding="utf-8").read().strip()
    vb = plano.get("voicebox", {})
    profile_id = _resolve_profile_id(vb)
    payload = {"text": text, "language": vb.get("language", "pt"), "profile_id": profile_id}
    if vb.get("engine"):
        payload["engine"] = vb["engine"]
    if vb.get("instruct"):
        payload["instruct"] = vb["instruct"]

    log(f"Gerando narração no VoiceBox (perfil {profile_id})...")
    req = urllib.request.Request(f"{VOICEBOX_URL}/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"VoiceBox recusou (HTTP {e.code}): {body[:600]}")
    except Exception as e:
        raise RuntimeError(f"Falha ao falar com o VoiceBox: {e}\n"
                           "Confirme que o app VoiceBox está aberto (API 127.0.0.1:17493).")
    if data[:4] == b"RIFF":            # (algumas versões devolvem o áudio direto)
        os.makedirs(os.path.dirname(out_wav), exist_ok=True)
        open(out_wav, "wb").write(data)
        log(f"Narração salva: {out_wav}")
        return 0
    # API assíncrona: retorna JSON com o id da geração -> espera e copia o áudio
    try:
        gen_id = json.loads(data).get("id")
    except Exception:
        gen_id = None
    if not gen_id:
        raise RuntimeError("Resposta inesperada do VoiceBox:\n" + data.decode("utf-8", "ignore")[:300])
    log(f"Geração enfileirada ({gen_id}). Aguardando o VoiceBox terminar...")
    _wait_generation(gen_id)
    with urllib.request.urlopen(f"{VOICEBOX_URL}/audio/{gen_id}", timeout=180) as r:
        audio = r.read()
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)
    open(out_wav, "wb").write(audio)
    log(f"Narração salva: {out_wav}")
    return 0


# ---------------------------------------------------------------------------
# plan — gera roteiro.json
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


# ---------------------------------------------------------------------------
# auto — dispara a edição quando tudo está pronto
# ---------------------------------------------------------------------------
def missing_prerequisites(project_dir, plano):
    faltando = []
    for nome, rel in (("vídeo", plano.get("video")), ("narração", plano.get("narration"))):
        if not rel or not os.path.exists(_abs(project_dir, rel)):
            faltando.append(nome)
    try:
        if not os.path.exists(resolve_music(project_dir, plano)):
            faltando.append("música")
    except Exception:
        faltando.append("música")
    # expressões: não bloqueiam a edição. O build_roteiro resolve os nomes
    # escolhidos pelo Claude e, se nada bater, sorteia da biblioteca. Só avisamos
    # se a pasta de personagens estiver completamente vazia.
    if not _personagem_imgs():
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
            build_roteiro(project_dir, plano)   # sempre regenera (casa com a narração atual)
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
    import glob
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
        build_roteiro(project_dir, plano, video_path=rel, output_name=f"candidato{i}.mp4")
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
# publish — sobe no YouTube
# ---------------------------------------------------------------------------
def cmd_publish(project_dir, plano, privacy="private"):
    pub = plano.get("publish", {})
    game = plano.get("game", plano.get("project", ""))
    video = _abs(project_dir, os.path.join("output", plano.get("output_name", "final.mp4")))
    if not os.path.exists(video):
        raise FileNotFoundError(f"Vídeo final não encontrado: {video}. Rode `auto` antes.")

    desc = pub.get("description", "").format(game=game, instagram=pub.get("instagram", ""),
                                             tiktok=pub.get("tiktok", ""))
    desc_path = os.path.join(project_dir, "output", "descricao.txt")
    open(desc_path, "w", encoding="utf-8").write(desc)
    comment = pub.get("comment", "").format(game=game)
    open(os.path.join(project_dir, "output", "comentario.txt"), "w", encoding="utf-8").write(comment)

    tags = ",".join(pub.get("tags", []))
    up = os.path.join(HERE, "publish", "youtube_upload.py")
    cmd = [sys.executable, up, "upload", "--video", video, "--title", pub.get("title", game),
           "--description-file", desc_path, "--tags", tags, "--privacy", privacy]
    log(f"Publicando no YouTube (privacidade: {privacy})...")
    code = subprocess.run(cmd, cwd=HERE).returncode
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
        build_roteiro(project_dir, plano); return 0
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
