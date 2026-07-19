"""Adaptador do YouTube Data API — busca e ranqueia vídeos (trailers).

Só faz a parte de LEITURA (busca + ranqueamento). O download é do services.download
e o upload (publicação) virá em services.youtube_upload numa fase futura.
"""

import re

from config import secrets

# palavras que indicam vídeo que NÃO queremos (reação, gameplay longo, live)
_BAD = ["react", "reaç", "gameplay", "walkthrough", "playthrough", "longplay",
        "full game", "speedrun", "live", "ao vivo", "análise", "analise", "review"]

# indícios de que é FILME/série, não jogo (a busca às vezes traz trailer de cinema)
_MOVIE = ["prime video", "netflix", "in theaters", "only in theaters", "movie",
          "the movie", "hbo", "max original", "disney", "episode", "season",
          "film", "cinema", "box office", "streaming now"]

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


def melhores_videos(query, n=4, max_results=15):
    """Retorna os N melhores como [(videoId, título, canal, dur), ...]."""
    key = secrets.youtube().get("api_key")
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
