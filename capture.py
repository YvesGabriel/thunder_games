#!/usr/bin/env python3
"""Captação do vídeo bruto — busca no YouTube e baixa para assets/video.mp4.

Estratégia: procura o TRAILER OFICIAL; se você preferir, baixa GAMEPLAY ou
FUNNY MOMENTS. Roda na SUA máquina (precisa do yt-dlp + FFmpeg).

    pip install yt-dlp

    # baixa o trailer do jogo do plano.json:
    python capture.py --project projects/core_keeper

    # tipo específico / consulta manual:
    python capture.py --project projects/core_keeper --type gameplay
    python capture.py --project projects/core_keeper --query "Core Keeper launch trailer"

ATENÇÃO (direitos): prefira o trailer OFICIAL (as publishers costumam liberar a
divulgação). Gameplay/cortes de terceiros exigem edição transformadora e cuidado
com copyright — como já conversamos.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys
import tempfile

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

# palavras que indicam vídeo que NÃO queremos (evita reação, gameplay longo, live)
_BAD = ["react", "reaç", "gameplay", "walkthrough", "playthrough", "longplay",
        "full game", "speedrun", "live", "ao vivo", "análise", "analise", "review"]

# indícios de que é FILME/série, não jogo (a busca às vezes traz trailer de cinema)
_MOVIE = ["prime video", "netflix", "in theaters", "only in theaters", "movie",
          "the movie", "hbo", "max original", "disney", "episode", "season",
          "film", "cinema", "box office", "streaming now"]


def _api_key():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets", "credentials.json")
    try:
        return json.load(open(p, encoding="utf-8"))["youtube"]["api_key"]
    except Exception:
        return None


_ISO = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _dur_seconds(iso):
    m = _ISO.match(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _score(title, channel, dur, views):
    t, c, s = title.lower(), channel.lower(), 0.0
    if "official" in t or "oficial" in t:
        s += 3
    if "trailer" in t:
        s += 2
    if "demo" in t:
        s += 1
    if "official" in c or "oficial" in c:
        s += 2
    for b in _BAD:
        if b in t:
            s -= 4
    for mv in _MOVIE:
        if mv in t or mv in c:       # filme/série no título ou no canal
            s -= 8
    if "game" in t or "gameplay" in c or "games" in c:
        s += 1.5
    if 15 <= dur <= 240:       # duração típica de trailer
        s += 2
    elif dur > 600:
        s -= 3
    s += min(views / 1_000_000, 3)   # leve peso de popularidade
    return s


def pick_best_videos(query, n=4, max_results=15):
    """Usa a API do YouTube e retorna os N melhores como [(videoId, título, canal, dur), ...]."""
    key = _api_key()
    if not key:
        return []
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=key)
        sr = yt.search().list(q=query, part="snippet", type="video",
                              maxResults=max_results).execute()
        ids = [it["id"]["videoId"] for it in sr.get("items", [])]
        if not ids:
            return []
        dv = yt.videos().list(id=",".join(ids),
                              part="contentDetails,statistics,snippet").execute()
        scored = []
        for it in dv.get("items", []):
            title = it["snippet"]["title"]
            ch = it["snippet"]["channelTitle"]
            dur = _dur_seconds(it.get("contentDetails", {}).get("duration"))
            views = int(it.get("statistics", {}).get("viewCount", 0))
            scored.append((_score(title, ch, dur, views), it["id"], title, ch, dur))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(v, t, c, d) for (_s, v, t, c, d) in scored[:n]]
    except Exception as e:
        print(f"(busca inteligente indisponível: {e})")
        return []


def load_plano(project_dir):
    with open(os.path.join(project_dir, "plano.json"), encoding="utf-8") as f:
        return json.load(f)


def download(target, out_path):
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("Instale o yt-dlp:  pip install yt-dlp")
        return 1
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Baixa numa pasta TEMPORÁRIA sem acentos e só depois move pro destino.
    # Motivo: o yt-dlp chama o ffmpeg pra juntar vídeo+áudio e lê a saída dele;
    # se o caminho tiver acento ("Área", "ç", "õ"), a leitura quebra no Windows
    # (console em cp/UTF-8) e derruba a thread interna do yt-dlp.
    tmp = tempfile.mkdtemp(prefix="tgvid_")
    opts = {
        "outtmpl": os.path.join(tmp, "dl.%(ext)s"),
        # pega até 1080p: vídeo + áudio separados e junta (precisa do FFmpeg + Deno)
        "format": ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                   "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "overwrites": True,
        "quiet": False,
        "noprogress": False,
        # retentativas contra 403/throttling do YouTube no meio do download
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "http_chunk_size": 10485760,
    }
    print(f"Baixando: {target}")
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([target])
        baixados = sorted(glob.glob(os.path.join(tmp, "dl.*")))
        arq = next((c for c in baixados if c.lower().endswith(".mp4")), baixados[0] if baixados else None)
        if not arq:
            print("  nada baixado (pulando).")
            return 1
        if os.path.exists(out_path):
            os.remove(out_path)
        shutil.move(arq, out_path)
    except Exception as e:
        print(f"  não deu pra baixar (pulando): {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if os.path.exists(out_path):
        print(f"OK — salvo em {out_path}")
        return 0
    print("Não foi possível baixar. Tente outra consulta (--query).")
    return 1


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
        if download(url, os.path.join(base_dir, f"{idx}.mp4")) == 0:
            sources.append({"index": idx, "url": url, "title": "(link manual)"})
    else:
        vids = pick_best_videos(query, n=args.n)   # os N melhores pela API
        if vids:
            for i, (vid, title, ch, dur) in enumerate(vids, 1):
                u = f"https://www.youtube.com/watch?v={vid}"
                print(f"[{i}] {title}  (canal: {ch}, {dur}s)")
                if download(u, os.path.join(base_dir, f"{i}.mp4")) == 0:
                    sources.append({"index": i, "url": u, "title": title})
        else:                                 # fallback: 1º resultado do yt-dlp
            if download(f"ytsearch1:{query}", os.path.join(base_dir, "1.mp4")) == 0:
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
