#!/usr/bin/env python3
"""CLI de publicação no YouTube — a lógica agora vive em services/youtube_upload.py.

Mantém os comandos manuais funcionando:

    # 1) autenticar e confirmar o canal (guarda o token):
    python publish/youtube_upload.py auth

    # 2) enviar um vídeo (privado por padrão):
    python publish/youtube_upload.py upload --video "projects/x/output/final.mp4" \
        --title "..." --description-file "..." --tags "a,b,c" --privacy private
"""

import argparse
import os
import sys

# garante que a raiz do projeto está no path (pra achar o pacote services/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import youtube_upload  # noqa: E402


def cmd_auth(_args):
    ch = youtube_upload.channel_info()
    if not ch:
        print("Autenticado, mas nenhum canal encontrado nesta conta.")
        return 1
    print("OK — autenticado.")
    print(f"  Canal: {ch['snippet']['title']}")
    print(f"  Inscritos: {ch['statistics'].get('subscriberCount', '?')}")
    return 0


def cmd_upload(args):
    if args.description_file:
        with open(args.description_file, encoding="utf-8") as f:
            desc = f.read().strip()
    else:
        desc = args.description or ""
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    return youtube_upload.upload(args.video, args.title, description=desc,
                                 tags=tags, privacy=args.privacy)


def main():
    p = argparse.ArgumentParser(description="YouTube: autenticar e enviar vídeos.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth").set_defaults(func=cmd_auth)
    up = sub.add_parser("upload")
    up.add_argument("--video", required=True)
    up.add_argument("--title", required=True)
    up.add_argument("--description", default="")
    up.add_argument("--description-file", dest="description_file", default=None)
    up.add_argument("--tags", default="")
    up.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    up.set_defaults(func=cmd_upload)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
