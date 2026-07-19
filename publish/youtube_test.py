#!/usr/bin/env python3
"""Teste rápido da API do YouTube usando a API KEY (somente leitura).

Não precisa de OAuth: valida se a chave funciona e já serve de base para a
busca de trailers (etapa de captação). Uso:

    pip install -r publish/requirements.txt
    python publish/youtube_test.py "Core Keeper trailer"
"""

import json
import os
import sys

from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.path.join(HERE, "..", "secrets", "credentials.json")


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Core Keeper trailer"
    with open(CREDS, encoding="utf-8") as f:
        api_key = json.load(f)["youtube"]["api_key"]

    yt = build("youtube", "v3", developerKey=api_key)
    print(f"Buscando: {query!r} ...\n")
    resp = yt.search().list(q=query, part="snippet", type="video", maxResults=5).execute()

    for item in resp.get("items", []):
        vid = item["id"]["videoId"]
        sn = item["snippet"]
        print(f"- {sn['title']}")
        print(f"    canal: {sn['channelTitle']}")
        print(f"    https://www.youtube.com/watch?v={vid}\n")

    print("OK — a API KEY do YouTube está funcionando.")


if __name__ == "__main__":
    main()
