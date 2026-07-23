"""Configuração central — caminhos, URLs e constantes usados por todo o projeto.

Único lugar onde caminhos e endereços ficam definidos. Se algo mudar (pasta da
Biblioteca, porta do VoiceBox, id da voz), muda-se AQUI e todos os módulos seguem.
"""

import os

# --- Raiz do código (a pasta video_auto_editor) --------------------------
# settings.py fica em config/, então a raiz é dois níveis acima.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Dados (hoje ainda ao lado do código; na Fase 4 migram para data/) ----
BIBLIOTECA = os.path.join(os.path.dirname(ROOT), "Biblioteca")
PERSONAGEM = os.path.join(BIBLIOTECA, "Personagem")
MUSICAS = os.path.join(BIBLIOTECA, "Musicas")
EFEITOS = os.path.join(BIBLIOTECA, "Efeitos")
PROJECTS_DIR = os.path.join(ROOT, "projects")
IDEIAS_DIR = os.path.join(ROOT, "ideias")
PROMPTS_DIR = os.path.join(ROOT, "prompts")

# --- Segredos ------------------------------------------------------------
SECRETS_FILE = os.path.join(ROOT, "secrets", "credentials.json")
YOUTUBE_TOKEN_FILE = os.path.join(ROOT, "secrets", "youtube_token.json")

# --- VoiceBox (voz clonada) ----------------------------------------------
VOICEBOX_URL = "http://127.0.0.1:17493"
VOICE_PROFILE_NAME = "Yves"
VOICE_PROFILE_ID = "01d97944-3ffc-48ff-9a3a-704b2ccf434b"
