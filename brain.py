#!/usr/bin/env python3
"""Cérebro do Thunder Games — curadoria e roteiros com o Claude LOCAL.

NÃO usa API paga. Usa o Claude Code que já vem com a sua assinatura, em modo
headless (linha de comando: `claude -p "..."`). Ou seja: um agente local é
disparado pra pesquisar jogos e escrever o roteiro.

Toda vez que você manda /simular, o bot chama aqui: o Claude pesquisa jogos
novos (lançamentos/novidades de Steam e Switch, curiosidades), evita repetir o
que já saiu, e devolve 5 ideias JÁ com roteiro pronto no formato do canal.
Também escreve o roteiro de um jogo fora da lista (/jogo <nome>).

Pré-requisito: ter o Claude Code instalado e logado na sua conta. Teste no
terminal:  claude -p "diga oi"
(instalação: https://docs.claude.com/en/docs/claude-code)

Config opcional em secrets/credentials.json:
    "claude_cli": { "command": "claude", "model": "" }
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):        # utf-8: evita quebra ao imprimir acentos/emojis
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import settings
from config import prompts
from services import claude

HERE = os.path.dirname(os.path.abspath(__file__))
IDEIAS = os.path.join(settings.IDEIAS_DIR, "ideias_atual.json")
USADOS = os.path.join(settings.IDEIAS_DIR, "usados.json")
PERSONAGEM = settings.PERSONAGEM


def _expressoes_disponiveis():
    """Nomes das expressões do apresentador (o nome descreve a emoção)."""
    return [os.path.splitext(os.path.basename(p))[0]
            for p in sorted(glob.glob(os.path.join(PERSONAGEM, "*.png")))
            if not os.path.basename(p).startswith("_")]


def _bloco_expressoes():
    disp = _expressoes_disponiveis()
    if not disp:
        return ""
    return (
        "\n\nEXPRESSÕES DO APRESENTADOR: escolha, na ordem em que devem aparecer, "
        "de 6 a 9 expressões que ACOMPANHEM as emoções do roteiro (ex.: um susto -> "
        "'boquiaberto'; algo incrível -> 'muito impressionado'; piada -> 'sorriso engraçado'). "
        "Use SOMENTE estes nomes EXATOS (copie igual):\n" + ", ".join(f"'{d}'" for d in disp) +
        '\nColoque no campo "expressions" como uma lista ordenada de nomes.')

# As regras do canal agora vivem em prompts/roteiro.md (editável sem tocar no código).


def _call(prompt):
    """Manda o prompt (com as regras do canal, de prompts/roteiro.md) pro Claude local."""
    return claude.call(prompt, system=prompts.load("roteiro"))


def _json_do_texto(txt):
    """Extrai o JSON da resposta (tolera cercas ``` e texto em volta)."""
    original = txt
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        return json.loads(txt[a:b + 1])
    a, b = txt.find("["), txt.rfind("]")
    if a >= 0 and b > a:
        return json.loads(txt[a:b + 1])
    raise RuntimeError("A resposta do Claude não continha JSON. Início da resposta:\n"
                       + (original or "").strip()[:500])


def _usados():
    nomes = set()
    if os.path.exists(USADOS):
        try:
            nomes.update(json.load(open(USADOS, encoding="utf-8")))
        except Exception:
            pass
    proj = os.path.join(HERE, "projects")
    if os.path.isdir(proj):
        for d in os.listdir(proj):
            p = os.path.join(proj, d, "plano.json")
            if os.path.exists(p):
                try:
                    nomes.add(json.load(open(p, encoding="utf-8")).get("game", "").strip())
                except Exception:
                    pass
    return sorted(n for n in nomes if n)


def _registrar_usados(games):
    atuais = []
    if os.path.exists(USADOS):
        try:
            atuais = json.load(open(USADOS, encoding="utf-8"))
        except Exception:
            atuais = []
    atuais = list(dict.fromkeys(atuais + list(games)))[-200:]
    os.makedirs(os.path.dirname(USADOS), exist_ok=True)
    json.dump(atuais, open(USADOS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def curar(n=5):
    """Gera n ideias novas com o Claude local, salva em ideias_atual.json e retorna a lista."""
    evitar = _usados()
    lista = "\n".join(f"- {g}" for g in evitar) or "(nenhum ainda)"
    prompt = (
        f"Sugira {n} jogos para vídeos do canal, cada um com roteiro e bloco publish.\n\n"
        f"NÃO repita nenhum destes jogos já usados:\n{lista}"
        + _bloco_expressoes() + "\n\n"
        "Responda SOMENTE com JSON válido (sem comentários, sem texto fora do JSON), no formato:\n"
        '{"sugestoes":[{"n":1,"game":"...","mood":"horror|funny|action|adventure|cozy|epic",'
        '"roteiro":"...","expressions":["nome1","nome2","..."],'
        '"publish":{"title":"... #Shorts","description":"...",'
        '"tags":["..."],"comment":"...","instagram":"@thunder_games_8","tiktok":"@thunder_games_8"}}]}'
    )
    data = _json_do_texto(_call(prompt))
    sug = data.get("sugestoes", data if isinstance(data, list) else [])
    for i, s in enumerate(sug, 1):
        s["n"] = i
    out = {"date": _hoje(), "sugestoes": sug}
    os.makedirs(os.path.dirname(IDEIAS), exist_ok=True)
    json.dump(out, open(IDEIAS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    _registrar_usados([s.get("game", "") for s in sug])
    return sug


def roteiro_para(game, mood="adventure"):
    """Escreve roteiro + publish para um jogo fora da lista (Claude local)."""
    prompt = (
        f"Escreva o roteiro e o bloco publish para o jogo: {game} (mood sugerido: {mood})."
        + _bloco_expressoes() + "\n"
        "Responda SOMENTE com JSON válido (sem texto fora do JSON) no formato:\n"
        '{"game":"...","mood":"...","roteiro":"...","expressions":["nome1","nome2","..."],'
        '"publish":{"title":"... #Shorts",'
        '"description":"...","tags":["..."],"comment":"...","instagram":"@thunder_games_8",'
        '"tiktok":"@thunder_games_8"}}'
    )
    data = _json_do_texto(_call(prompt))
    _registrar_usados([data.get("game", game)])
    return data


def _hoje():
    import datetime
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "roteiro":
        print(json.dumps(roteiro_para(" ".join(sys.argv[2:])), ensure_ascii=False, indent=2))
    else:
        for s in curar():
            print(f"{s['n']}. {s['game']} ({s.get('mood')})")
        print(f"\nSalvo em {IDEIAS}")
