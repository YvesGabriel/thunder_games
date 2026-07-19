#!/usr/bin/env python3
"""Telegram do Thunder Games — enviar mensagens/vídeos e ler respostas.

Usa só a biblioteca padrão (urllib). Lê o token/chat_id de secrets/credentials.json.
Roda na SUA máquina (rede sem restrição).

Teste rápido:
    python notify.py "Thunder Games conectado! 🎮"
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from config import secrets as _secrets


def _creds():
    return _secrets.telegram()


def _api(method):
    token, _ = _creds()
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(text, chat_id=None, retries=4):
    _, chat = _creds()
    data = urllib.parse.urlencode({"chat_id": chat_id or chat, "text": text}).encode()
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(_api("sendMessage"), data=data), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            raise RuntimeError(
                f"Telegram recusou (HTTP {e.code}): {body}\n"
                "Dica: se disser 'chat not found', abra o SEU bot no Telegram e clique em Iniciar/Start.")
        except Exception as e:                       # reset de conexão / rede instável
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Telegram inacessível após {retries} tentativas: {last}")


def send_video(path, caption="", chat_id=None, retries=3):
    _, chat = _creds()
    fname = os.path.basename(path)
    file_bytes = open(path, "rb").read()
    last = None
    for i in range(retries):
        b = uuid.uuid4().hex
        body = b""
        for k, v in {"chat_id": chat_id or chat, "caption": caption}.items():
            body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"video\"; "
                 f"filename=\"{fname}\"\r\nContent-Type: video/mp4\r\n\r\n").encode()
        body += file_bytes + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(_api("sendVideo"), data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except Exception as e:                       # reset de conexão no upload → tenta de novo
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Não consegui enviar o vídeo após {retries} tentativas: {last}")


def get_updates(offset=0, timeout=30):
    """Lê mensagens novas (long polling). Retorna a lista de updates."""
    url = _api("getUpdates") + f"?offset={offset}&timeout={timeout}"
    with urllib.request.urlopen(url, timeout=timeout + 10) as r:
        return json.loads(r.read()).get("result", [])


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Thunder Games conectado! 🎮⚡"
    print(send_message(msg))
