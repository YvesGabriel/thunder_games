"""Adaptador de UPLOAD no YouTube — OAuth + videos.insert.

Roda LOCAL: no 1º uso abre o navegador pro consentimento (você precisa estar
listado como usuário de teste na tela OAuth). Guarda o token pra reusar.

    from services import youtube_upload
    youtube_upload.upload(video, title, description=desc, tags=[...], privacy="private")
"""

import os

from config import secrets, settings

TOKEN = settings.YOUTUBE_TOKEN_FILE
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _client_config():
    y = secrets.youtube()
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


def channel_info():
    """Retorna o dict do canal autenticado (ou None)."""
    yt = _service()
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    return items[0] if items else None


def upload(video, title, description="", tags=None, privacy="private", on_log=print):
    """Sobe o vídeo. Retorna 0 se OK, 1 se o arquivo não existe."""
    from googleapiclient.http import MediaFileUpload
    if not os.path.exists(video):
        on_log(f"Vídeo não encontrado: {video}")
        return 1
    desc = (description or "").strip()
    if "#short" not in desc.lower():            # ajuda o YouTube a classificar como Short
        desc = (desc + "\n\n#Shorts").strip()
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": [t.strip() for t in (tags or []) if t and t.strip()],
            "categoryId": "20",  # Gaming
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video, chunksize=-1, resumable=True, mimetype="video/*")
    on_log(f"Enviando {os.path.basename(video)} ...")
    req = _service().videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            on_log(f"  {int(status.progress() * 100)}%")
    on_log("OK — publicado (privacidade: %s)." % privacy)
    on_log(f"  https://youtu.be/{resp['id']}")
    return 0
