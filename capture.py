#!/usr/bin/env python3
"""Captação do vídeo bruto — orquestra busca (services.youtube) + download (services.download).

    # baixa os melhores trailers do jogo do plano.json:
    python capture.py --project projects/core_keeper

    # tipo específico / consulta manual / link direto:
    python capture.py --project projects/core_keeper --type gameplay
    python capture.py --project projects/core_keeper --query "Core Keeper launch trailer"
    python capture.py --project projects/core_keeper --url https://youtu.be/xxxx --append

ATENÇÃO (direitos): prefira o trailer OFICIAL (as publishers costumam liberar a
divulgação). Gameplay/cortes de terceiros exigem edição transformadora e cuidado
com copyright.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys

from services import download, youtube

for _s in (sys.stdout, sys.stderr):        # utf-8: console cp1252 do Windows quebra com → / emojis
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

QUERIES = {
    "trailer": "{game} game official trailer",
    "gameplay": "{game} game gameplay 4k no commentary",
    "funny": "{game} game funny moments",
}


def load_plano(project_dir):
    with open(os.path.join(project_dir, "plano.json"), encoding="utf-8") as f:
        return json.load(f)


def _next_index(base_dir):
    idx = 0
    for f in glob.glob(os.path.join(base_dir, "*.mp4")):
        m = re.match(r"(\d+)\.mp4$", os.path.basename(f))
        if m:
            idx = max(idx, int(m.group(1)))
    return idx + 1


def _merge_sources(base_dir, novos):
    """Guarda em base/sources.json as URLs baixadas (pra o bot mostrar os links)."""
    path = os.path.join(base_dir, "sources.json")
    atuais = []
    if os.path.exists(path):
        try:
            atuais = json.load(open(path, encoding="utf-8"))
        except Exception:
            atuais = []
    urls = {s.get("url") for s in atuais}
    for s in novos:
        if s.get("url") not in urls:
            atuais.append(s)
    json.dump(atuais, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Baixa o vídeo bruto do jogo (trailer/gameplay).")
    ap.add_argument("--project", required=True)
    ap.add_argument("--type", default="trailer", choices=list(QUERIES))
    ap.add_argument("--query", default=None, help="consulta manual (sobrepõe o tipo)")
    ap.add_argument("--url", default=None, help="baixar direto de uma URL do YouTube")
    ap.add_argument("--append", action="store_true",
                    help="com --url: baixa como vídeo ADICIONAL (não sobrescreve os de base)")
    ap.add_argument("--game", default=None, help="nome do jogo (senão, pega do plano.json)")
    ap.add_argument("--n", type=int, default=4, help="quantos vídeos baixar (padrão 4)")
    args = ap.parse_args()

    project_dir = os.path.abspath(args.project)
    plano = load_plano(project_dir)
    game = args.game or plano.get("game") or plano.get("project", "")

    base_dir = os.path.join(project_dir, "base")
    os.makedirs(base_dir, exist_ok=True)

    url = args.url or plano.get("capture_url")
    query = args.query or plano.get("capture_query") or QUERIES[args.type].format(game=game)

    sources = []
    if url:
        idx = _next_index(base_dir) if args.append else 1   # append = próximo índice livre
        if download.baixar(url, os.path.join(base_dir, f"{idx}.mp4")) == 0:
            sources.append({"index": idx, "url": url, "title": "(link manual)"})
    else:
        vids = youtube.melhores_videos(query, n=args.n)   # os N melhores pela API
        if vids:
            for i, (vid, title, ch, dur) in enumerate(vids, 1):
                u = f"https://www.youtube.com/watch?v={vid}"
                print(f"[{i}] {title}  (canal: {ch}, {dur}s)")
                if download.baixar(u, os.path.join(base_dir, f"{i}.mp4")) == 0:
                    sources.append({"index": i, "url": u, "title": title})
        else:                                 # fallback: 1º resultado do yt-dlp
            if download.baixar(f"ytsearch1:{query}", os.path.join(base_dir, "1.mp4")) == 0:
                sources.append({"index": 1, "url": f"ytsearch:{query}", "title": query})

    _merge_sources(base_dir, sources)

    # o primeiro trailer disponível também vira assets/video.mp4 (fluxo de 1 vídeo)
    disponiveis = sorted(glob.glob(os.path.join(base_dir, "*.mp4")))
    if disponiveis:
        assets = os.path.join(project_dir, "assets")
        os.makedirs(assets, exist_ok=True)
        shutil.copyfile(disponiveis[0], os.path.join(assets, "video.mp4"))
        print(f"{len(disponiveis)} trailer(s) em base/.")
    else:
        print("Nenhum trailer baixado.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
