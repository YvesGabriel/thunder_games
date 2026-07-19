"""Adaptador do VoiceBox — a voz clonada, via API local (127.0.0.1:17493).

API assíncrona: POST /generate devolve um id; a gente faz polling em /history até
ficar "completed" e baixa o WAV em /audio/{id}. Algumas versões devolvem o áudio
direto (RIFF) — os dois casos são tratados aqui.

Uso:
    from services import voicebox
    pid = voicebox.resolve_profile_id(plano["voicebox"])
    wav_bytes = voicebox.gerar(texto, pid, language="pt", on_log=print)
"""

import json
import time
import urllib.error
import urllib.request

from config import settings

URL = settings.VOICEBOX_URL
_DONE = {"completed", "done", "success", "finished"}


def _noop(*_a):
    pass


def profiles():
    """Lista os perfis de voz (GET /profiles)."""
    with urllib.request.urlopen(f"{URL}/profiles", timeout=30) as r:
        data = json.loads(r.read())
    if isinstance(data, list):
        return data
    for k in ("profiles", "data", "items"):
        if isinstance(data.get(k), list):
            return data[k]
    return []


def resolve_profile_id(vb):
    """Descobre o profile_id: usa o informado, ou acha pelo nome em /profiles."""
    if vb.get("profile_id"):
        return vb["profile_id"]
    name = vb.get("profile", "")
    try:
        profs = profiles()
    except Exception as e:
        raise RuntimeError(f"Não consegui listar os perfis do VoiceBox: {e}")
    for p in profs:
        if str(p.get("name", "")).strip().lower() == name.strip().lower():
            return p.get("id") or p.get("profile_id")
    nomes = [p.get("name") for p in profs]
    raise RuntimeError(
        f"Perfil '{name}' não encontrado no VoiceBox. Disponíveis: {nomes}\n"
        "Ajuste 'voicebox.profile' (nome exato) ou 'voicebox.profile_id' no plano.json.")


def _history(req_timeout=15):
    with urllib.request.urlopen(f"{URL}/history", timeout=req_timeout) as r:
        d = json.loads(r.read())
    return d.get("items", []) if isinstance(d, dict) else d


def _wait_generation(gen_id, on_log=_noop, timeout=420, interval=3):
    """Espera a geração terminar. Enquanto o VoiceBox está ocupado, o /history
    pode dar timeout — nesses casos ignoramos e tentamos de novo."""
    t0 = time.time()
    last_log = 0
    while time.time() - t0 < timeout:
        try:
            for it in _history():
                if it.get("id") == gen_id:
                    if it.get("error"):
                        raise RuntimeError(f"VoiceBox falhou: {it['error']}")
                    if str(it.get("status", "")).lower() in _DONE:
                        return True
                    break
        except RuntimeError:
            raise
        except Exception:
            pass  # servidor ocupado gerando; segue tentando
        if time.time() - last_log > 15:
            on_log(f"  ...ainda gerando ({int(time.time()-t0)}s)")
            last_log = time.time()
        time.sleep(interval)
    raise RuntimeError(
        "Tempo esgotado esperando o VoiceBox. A fila pode ter travado — "
        "FECHE e reabra o app VoiceBox e rode o `narrate` UMA vez só.")


def gerar(text, profile_id, language="pt", engine=None, instruct=None, on_log=_noop):
    """Gera a narração e retorna os BYTES do WAV. Levanta RuntimeError em falha."""
    payload = {"text": text, "language": language, "profile_id": profile_id}
    if engine:
        payload["engine"] = engine
    if instruct:
        payload["instruct"] = instruct

    on_log(f"Gerando narração no VoiceBox (perfil {profile_id})...")
    req = urllib.request.Request(f"{URL}/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"VoiceBox recusou (HTTP {e.code}): {body[:600]}")
    except Exception as e:
        raise RuntimeError(f"Falha ao falar com o VoiceBox: {e}\n"
                           "Confirme que o app VoiceBox está aberto (API 127.0.0.1:17493).")

    if data[:4] == b"RIFF":            # algumas versões devolvem o áudio direto
        return data
    # API assíncrona: JSON com o id -> espera terminar -> baixa o áudio
    try:
        gen_id = json.loads(data).get("id")
    except Exception:
        gen_id = None
    if not gen_id:
        raise RuntimeError("Resposta inesperada do VoiceBox:\n" + data.decode("utf-8", "ignore")[:300])
    on_log(f"Geração enfileirada ({gen_id}). Aguardando o VoiceBox terminar...")
    _wait_generation(gen_id, on_log=on_log)
    with urllib.request.urlopen(f"{URL}/audio/{gen_id}", timeout=180) as r:
        return r.read()
