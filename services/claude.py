"""Adaptador do Claude Code local (CLI headless) — NÃO usa API paga.

Só sabe "falar com o claude": recebe um prompt (e um system opcional), roda
`claude -p --output-format json` mandando o texto pela stdin (no Windows, passar
como argumento corta textos longos) e devolve o texto da resposta.

Quem decide O QUE perguntar é o brain (camada de canal), não este adaptador.
"""

import json
import os
import shutil
import subprocess

from config import settings


def _cfg():
    from config import secrets
    return secrets.claude_cli()


def _resolve(cmd):
    for c in (cmd, cmd + ".cmd", cmd + ".exe"):
        found = shutil.which(c)
        if found:
            return found
    return None


def call(prompt, system=None, timeout=240):
    """Roda o Claude local e devolve o texto da resposta. Levanta RuntimeError em falha."""
    cmd, model = _cfg()
    exe = _resolve(cmd)
    if not exe:
        raise RuntimeError(
            f"Não encontrei o Claude Code ('{cmd}') no PATH. Instale e faça login: "
            "https://docs.claude.com/en/docs/claude-code — teste com: claude -p \"oi\"")
    full = (system + "\n\n---\n\n" + prompt) if system else prompt
    args = [exe, "-p", "--output-format", "json"]
    if model:
        args += ["--model", model]
    p = subprocess.run(args, input=full, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    raw = (p.stdout or "")
    # guarda a resposta crua pra diagnóstico
    try:
        os.makedirs(settings.IDEIAS_DIR, exist_ok=True)
        with open(os.path.join(settings.IDEIAS_DIR, "_debug_resposta.txt"), "w", encoding="utf-8") as f:
            f.write(f"returncode={p.returncode}\n\n--- STDOUT ---\n{raw}\n\n--- STDERR ---\n{p.stderr or ''}")
    except Exception:
        pass
    if p.returncode != 0:
        raise RuntimeError(f"claude CLI falhou (returncode {p.returncode}): "
                           f"{(p.stderr or raw).strip()[:400]}")
    out = raw.strip()
    if not out:
        raise RuntimeError(f"claude não retornou nada no stdout. stderr: {(p.stderr or '').strip()[:400]}")
    try:                                   # --output-format json envelopa em {"result": "..."}
        env = json.loads(out)
        if isinstance(env, dict) and "result" in env:
            return env["result"]
    except Exception:
        pass
    return out
