"""Adaptador de download (yt-dlp) — baixa vídeo em até 1080p.

Baixa numa pasta TEMPORÁRIA sem acentos e só depois move pro destino. Motivo: o
yt-dlp chama o ffmpeg pra juntar vídeo+áudio e lê a saída dele; se o caminho tiver
acento ("Área", "ç", "õ"), a leitura quebra no Windows e derruba a thread interna.
"""

import glob
import os
import shutil
import tempfile


def baixar(target, out_path, on_log=print):
    """Baixa `target` (URL ou 'ytsearch1:...') para out_path. Retorna 0 se OK, 1 se falhou."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        on_log("Instale o yt-dlp:  pip install yt-dlp")
        return 1
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
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
    on_log(f"Baixando: {target}")
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([target])
        baixados = sorted(glob.glob(os.path.join(tmp, "dl.*")))
        arq = next((c for c in baixados if c.lower().endswith(".mp4")), baixados[0] if baixados else None)
        if not arq:
            on_log("  nada baixado (pulando).")
            return 1
        if os.path.exists(out_path):
            os.remove(out_path)
        shutil.move(arq, out_path)
    except Exception as e:
        on_log(f"  não deu pra baixar (pulando): {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if os.path.exists(out_path):
        on_log(f"OK — salvo em {out_path}")
        return 0
    on_log("Não foi possível baixar. Tente outra consulta (--query).")
    return 1
