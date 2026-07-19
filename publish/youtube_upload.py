#!/usr/bin/env python3
"""Autenticação (OAuth) e upload de vídeos no YouTube.

Precisa rodar NA SUA MÁQUINA (abre o navegador para o consentimento). Você
precisa estar listado como "usuário de teste" na tela de consentimento OAuth.

    pip install -r publish/requirements.txt

    # 1) autenticar e confirmar o canal (guarda o token):
    python publish/youtube_upload.py auth

    # 2) enviar um vídeo (privado por padrão — troque depois para public):
    python publish/youtube_upload.py upload \
        --video "projects/core_keeper/output/final.mp4" \
        --title "Core Keeper: Terraria + Stardew debaixo da terra" \
        --description "#CoreKeeper #jogosindie #coop" \
        --tags "core keeper,jogos,indie,coop" \
        --privacy private
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(HERE, "..", "secrets")
CREDS = os.path.join(SECRETS, "credentials.json")
TOKEN = os.path.join(SECRETS, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _client_config():
    with open(CREDS, encoding="utf-8") as f:
        y = json.load(f)["youtube"]
    return {
        "installed": {
            "client_id": y["oauth_client_id"],
            "client_secret": y["oauth_client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def _service():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=get_credentials())


def cmd_auth(_args):
    yt = _service()
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        print("Autenticado, mas nenhum canal encontrado nesta conta.")
        return 1
    ch = items[0]
    print("OK — autenticado.")
    print(f"  Canal: {ch['snippet']['title']}")
    print(f"  Inscritos: {ch['statistics'].get('subscriberCount', '?')}")
    print(f"  Token salvo em: {TOKEN}")
    return 0


def cmd_upload(args):
    from googleapiclient.http import MediaFileUpload
    if not os.path.exists(args.video):
        print(f"Vídeo não encontrado: {args.video}")
        return 1
    # Descrição: de um arquivo (--description-file) ou string (--description).
    if getattr(args, "description_file", None):
        with open(args.description_file, encoding="utf-8") as f:
            desc = f.read().strip()
    else:
        desc = args.description or ""
    # Garante o #Shorts na descrição (ajuda o YouTube a classificar como Short;
    # o vídeo também precisa ser vertical e ter até ~3 min — o nosso é 9:16, ~42s).
    if "#short" not in desc.lower():
        desc = (desc + "\n\n#Shorts").strip()

    body = {
        "snippet": {
            "title": args.title,
            "description": desc,
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            "categoryId": "20",  # Gaming
        },
        "status": {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(args.video, chunksize=-1, resumable=True, mimetype="video/*")
    print(f"Enviando {os.path.basename(args.video)} ...")
    req = _service().videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")
    vid = resp["id"]
    print("OK — publicado (privacidade: %s)." % args.privacy)
    print(f"  https://youtu.be/{vid}")
    return 0


def main():
    p = argparse.ArgumentParser(description="YouTube: autenticar e enviar vídeos.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth").set_defaults(func=cmd_auth)
    up = sub.add_parser("upload")
    up.add_argument("--video", required=True)
    up.add_argument("--title", required=True)
    up.add_argument("--description", default="")
    up.add_argument("--description-file", dest="description_file", default=None,
                    help="lê a descrição de um arquivo .txt (recomendado)")
    up.add_argument("--tags", default="")
    up.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    up.set_defaults(func=cmd_upload)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
