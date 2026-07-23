#!/usr/bin/env python3
"""Bot do Telegram — o operador do Thunder Games no seu PC.

Escuta o Telegram e comanda o fluxo local (captação → voz → 4 edições → envio).

Mensagens que ele entende:
  /simular  (ou /ideias)  → manda as sugestões de hoje na hora (sem esperar 8h)
  <número>                → escolhe a sugestão N da lista
  <nome de um jogo>       → faz um jogo fora da lista (custom)
  pick N                  → marca a versão N como o vídeo PRONTO
  /ajuda                  → lista os comandos

Rode assim (deixe aberto):
    python bot.py
"""

import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import notify
import brain
from channel import publicacao

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
IDEIAS = os.path.join(HERE, "ideias", "ideias_atual.json")
VOICEBOX = "http://127.0.0.1:17493"


def voicebox_up():
    try:
        with urllib.request.urlopen(VOICEBOX + "/profiles", timeout=5):
            return True
    except Exception:
        return False


def esperar_voicebox(timeout=600):
    """Se o VoiceBox estiver fechado, avisa e aguarda você abrir (não trava o fluxo)."""
    if voicebox_up():
        return True
    notify.send_message("🎙️ O VoiceBox está fechado. Abra ele que eu continuo automaticamente...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if voicebox_up():
            notify.send_message("✅ VoiceBox detectado — seguindo com a narração.")
            return True
        time.sleep(5)
    notify.send_message("⌛ Não detectei o VoiceBox a tempo. Fluxo pausado — mande o número de novo quando abrir.")
    return False

_state = {}   # lembra o projeto atual para o "pick N"
_offset = 0   # posição do getUpdates, compartilhada entre o loop e as esperas


def slugify(name):
    s = re.sub(r"[^\w]+", "_", name.strip().lower(), flags=re.UNICODE).strip("_")
    return s or "jogo"


def load_sugestoes():
    if os.path.exists(IDEIAS):
        try:
            return json.load(open(IDEIAS, encoding="utf-8")).get("sugestoes", [])
        except Exception:
            return []
    return []


def enviar_sugestoes():
    notify.send_message("🧠 Consultando o Claude por ideias novas...")
    try:
        sug = brain.curar()                 # curadoria FRESCA a cada /simular
    except Exception as e:
        notify.send_message(f"⚠️ Não consegui gerar ideias novas ({e}).\nUsando a última lista salva.")
        sug = load_sugestoes()
    if not sug:
        notify.send_message("Não há sugestões disponíveis. Mande '/jogo <nome>' que eu começo por aí.")
        return
    linhas = ["🎮 Ideias de hoje — responda com o NÚMERO da opção que quiser:\n"]
    for s in sug:
        linhas.append(f"{s['n']}. {s['game']}  ({s.get('mood', '')})")
    linhas.append("\n📌 Quer um jogo que NÃO está na lista? Mande:  /jogo <nome do jogo>")
    linhas.append("Ex.: responda '2', ou escreva '/jogo Hollow Knight Silksong'.")
    notify.send_message("\n".join(linhas))


def run(args):
    return subprocess.run([PY, *args], cwd=HERE).returncode


def run_capture(args):
    """Roda e captura a saída (pra mostrar o erro real no Telegram)."""
    p = subprocess.run([PY, *args], cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")   # console do Windows não é utf-8
    return p.returncode, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()


def _wait_file(path, timeout=1800, interval=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(path):
            return True
        time.sleep(interval)
    return False


def aguardar_mensagem(timeout=1800):
    """Espera a PRÓXIMA mensagem de texto do usuário (usada nos checkpoints)."""
    global _offset
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for up in notify.get_updates(offset=_offset, timeout=25):
                _offset = up["update_id"] + 1
                txt = (up.get("message", {}) or {}).get("text") or ""
                if txt.strip():
                    return txt.strip()
        except Exception:
            time.sleep(2)
    return None


def _extrair_url(txt):
    m = re.search(r"https?://\S+", txt)
    return m.group(0) if m else None


_OK = {"ok", "sim", "segue", "seguir", "pode", "continuar", "continua", "vai", "bora", "manda", "beleza"}
_NAO = {"cancelar", "cancela", "não", "nao", "parar", "para", "stop", "aborta", "abortar"}


def checkpoint_videos(rel):
    """Mostra os links dos vídeos-base, pergunta se segue e aceita links extras."""
    proj = os.path.join(HERE, rel)
    srcs = []
    sp = os.path.join(proj, "base", "sources.json")
    if os.path.exists(sp):
        try:
            srcs = json.load(open(sp, encoding="utf-8"))
        except Exception:
            srcs = []
    if srcs:
        linhas = ["🎞️ Vídeos-base que vão pra edição:\n"]
        for s in srcs:
            linhas.append(f"{s.get('index', '?')}. {s.get('title', '')}\n{s.get('url', '')}")
        notify.send_message("\n".join(linhas))
    else:
        notify.send_message("🎞️ Baixei os trailers (sem lista de links registrada).")
    notify.send_message("Posso seguir pra edição?\n"
                        "• 'ok' → continua\n"
                        "• cole um link do YouTube → ADICIONA esse vídeo à edição (pode mandar vários)\n"
                        "• 'cancelar' → para o fluxo")
    while True:
        resp = aguardar_mensagem(timeout=1800)
        if resp is None:
            notify.send_message("⌛ Sem resposta — fluxo pausado. Recomece quando puder.")
            return False
        low = resp.strip().lower()
        if low in _OK:
            return True
        if low in _NAO:
            return False
        url = _extrair_url(resp)
        if url:
            notify.send_message("⬇️ Adicionando esse vídeo à edição...")
            if run(["capture.py", "--project", rel, "--url", url, "--append"]) == 0:
                notify.send_message("✅ Adicionado. Manda outro link, ou 'ok' pra seguir.")
            else:
                notify.send_message("⚠️ Não consegui baixar esse link. Tenta outro, ou 'ok' pra seguir.")
            continue
        notify.send_message("Não entendi 🤔 Responda 'ok', cole um link do YouTube, ou 'cancelar'.")


def start_flow(game, mood="adventure", roteiro=None, publish=None, expressions=None):
    slug = slugify(game)
    proj = os.path.join(HERE, "projects", slug)
    rel = f"projects/{slug}"
    notify.send_message(f"▶️ Iniciando: {game}  (pasta: {slug})")

    run(["pipeline.py", "new", "--name", slug, "--game", game, "--mood", mood])

    # roteiro: se veio pronto (da lista), grava; se for custom, espera o Claude escrever
    narr_txt = os.path.join(proj, "assets", "narration.txt")
    if roteiro:
        os.makedirs(os.path.join(proj, "assets"), exist_ok=True)
        open(narr_txt, "w", encoding="utf-8").write(roteiro)
    if publish or expressions:
        try:
            p = json.load(open(os.path.join(proj, "plano.json"), encoding="utf-8"))
            if publish:
                p["publish"] = publish
            if expressions:            # ordem/expressões escolhidas pelo Claude junto do roteiro
                p["expressions"] = [{"name": e} for e in expressions]
            json.dump(p, open(os.path.join(proj, "plano.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass

    # captação (4 trailers) — não depende do roteiro
    notify.send_message("⬇️ Baixando os 4 melhores trailers...")
    run(["capture.py", "--project", rel])

    # checkpoint: mostra os links, confirma e aceita vídeos extras antes de editar
    if not checkpoint_videos(rel):
        notify.send_message("⏸️ Fluxo cancelado antes da edição. Os arquivos ficam salvos.")
        return

    if not os.path.exists(narr_txt):
        notify.send_message("✍️ Jogo fora da lista — preciso do roteiro. "
                            "Escreva o roteiro em assets/narration.txt (ou peça ao Claude). "
                            "Vou aguardar...")
        if not _wait_file(narr_txt):
            notify.send_message("⌛ Não recebi o roteiro a tempo. Fluxo pausado.")
            return

    if not narrar(rel):
        return
    editar_e_enviar(rel, game)


# ---------------------------------------------------------------------------
# Etapas isoladas (pra testar sem refazer tudo)
# ---------------------------------------------------------------------------
def _resolve_rel(slug_or_rel):
    """Aceita 'thank_goodness' ou 'projects/thank_goodness' e retorna (rel, proj, game)."""
    slug = slug_or_rel.strip().replace("projects/", "").replace("projects\\", "").strip("/\\")
    slug = slugify(slug) if slug else slug
    rel = f"projects/{slug}"
    proj = os.path.join(HERE, "projects", slug)
    game = slug
    try:
        game = json.load(open(os.path.join(proj, "plano.json"), encoding="utf-8")).get("game", slug)
    except Exception:
        pass
    return rel, proj, game


def captar(rel):
    notify.send_message("⬇️ Baixando os 4 melhores trailers...")
    run(["capture.py", "--project", rel])
    return True


def narrar(rel):
    proj = os.path.join(HERE, rel)
    if not os.path.exists(os.path.join(proj, "assets", "narration.txt")):
        notify.send_message(f"⚠️ Falta o roteiro em {rel}/assets/narration.txt.")
        return False
    if not esperar_voicebox():
        return False
    notify.send_message("🎙️ Gerando a narração (VoiceBox)...")
    rc, out = run_capture(["pipeline.py", "narrate", "--project", rel])
    if rc != 0:
        notify.send_message("⚠️ Erro na narração:\n" + (out[-700:] or "(sem detalhes)") +
                            "\n\nDica: se a fila do VoiceBox travou, feche e reabra o app.")
        return False
    return True


def editar_e_enviar(rel, game=None):
    proj = os.path.join(HERE, rel)
    slug = os.path.basename(rel)
    game = game or slug
    if not os.path.exists(os.path.join(proj, "assets", "narration.wav")):
        notify.send_message(f"⚠️ Falta a narração (assets/narration.wav) em {rel}. "
                            "Rode a voz antes (/narrar " + slug + ").")
        return
    if not glob.glob(os.path.join(proj, "base", "*.mp4")):
        notify.send_message(f"⚠️ Não há trailers em {rel}/base/. Rode /captar {slug} antes.")
        return
    notify.send_message("🎬 Editando as 4 versões...")
    rc, out = run_capture(["pipeline.py", "candidatos", "--project", rel])
    if rc != 0:
        notify.send_message("⚠️ Erro na edição:\n" + (out[-700:] or "(sem detalhes)"))
        return
    vids = sorted(glob.glob(os.path.join(proj, "candidatos", "*.mp4")))
    enviados = 0
    for i, v in enumerate(vids, 1):
        try:
            notify.send_video(v, caption=f"{game} — versão {i}")
            enviados += 1
        except Exception as e:
            notify.send_message(f"⚠️ Falhei ao enviar a versão {i} ({e}). "
                                f"Ela está salva em {rel}/candidatos/.")
    _state["proj"], _state["game"] = rel, game
    if enviados:
        notify.send_message(f"✅ {enviados} de {len(vids)} versões enviadas. "
                            "Responda 'pick N' com a melhor (ex.: pick 2).")
    else:
        notify.send_message(f"⚠️ Não enviei as versões, mas estão em {rel}/candidatos/. "
                            "Responda 'pick N' pra marcar a melhor.")
    enviar_kit(rel, game)


def enviar_kit(rel, game):
    """Gera título/descrição/tags/comentário das 3 plataformas e manda no Telegram."""
    proj = os.path.join(HERE, rel)
    roteiro_txt = ""
    p = os.path.join(proj, "assets", "narration.txt")
    if os.path.exists(p):
        roteiro_txt = open(p, encoding="utf-8").read().strip()
    notify.send_message("📝 Gerando os textos de publicação (YouTube, TikTok, Instagram)...")
    try:
        kit = publicacao.gerar_kit(game, roteiro_txt)
    except Exception as e:
        notify.send_message(f"⚠️ Não consegui gerar os textos de publicação ({e}).")
        return
    try:
        json.dump(kit, open(os.path.join(proj, "publicacao.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)   # salva na pasta do jogo pra não perder
    except Exception:
        pass
    for msg in publicacao.formatar_telegram(kit, game):
        notify.send_message(msg)


def handle_pick(num):
    proj = _state.get("proj")
    if not proj:
        notify.send_message("Não tenho vídeos em espera. Escolha um jogo primeiro.")
        return
    if run(["pipeline.py", "pick", "--num", str(num), "--project", proj]) == 0:
        notify.send_message(f"🏆 Versão {num} marcada como PRONTA — na pasta do jogo e em 'Videos prontos'.")
    else:
        notify.send_message("⚠️ Não consegui marcar essa versão.")


def listar_projetos():
    proj = os.path.join(HERE, "projects")
    slugs = sorted(d for d in os.listdir(proj)
                   if os.path.isdir(os.path.join(proj, d))) if os.path.isdir(proj) else []
    if not slugs:
        notify.send_message("Nenhum projeto ainda. Comece com /simular ou /jogo <nome>.")
        return
    linhas = ["📁 Projetos (etapas por comando):"]
    for s in slugs:
        p = os.path.join(proj, s)
        tem_base = "🎞️" if glob.glob(os.path.join(p, "base", "*.mp4")) else "▫️"
        tem_voz = "🎙️" if os.path.exists(os.path.join(p, "assets", "narration.wav")) else "▫️"
        tem_cand = "🎬" if glob.glob(os.path.join(p, "candidatos", "*.mp4")) else "▫️"
        linhas.append(f"{tem_base}{tem_voz}{tem_cand}  {s}")
    linhas.append("\n🎞️=trailers 🎙️=voz 🎬=editado")
    linhas.append("Use: /captar <slug>, /narrar <slug>, /editar <slug>")
    notify.send_message("\n".join(linhas))


def handle_atualizar():
    """git pull + reinicia o bot com o código novo (deploy pelo Telegram)."""
    notify.send_message("⬇️ Puxando atualização (git pull)...")
    p = subprocess.run(["git", "pull"], cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    if p.returncode != 0:
        notify.send_message("⚠️ git pull falhou:\n" + (out[-800:] or "(sem detalhes)") +
                            "\n\nSe houver edição local no Windows, ela dá conflito — "
                            "esta máquina deve ser só 'pull'.")
        return
    if "up to date" in out.lower() or "atualizado" in out.lower():
        notify.send_message("✅ Já estava na última versão — nada pra reiniciar.")
        return
    notify.send_message("✅ Atualizado:\n" + out[-800:] + "\n\n🔄 Reiniciando o bot...")
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)   # recarrega o código novo
    except Exception as e:
        notify.send_message(f"⚠️ Puxei a atualização, mas falhei ao reiniciar sozinho ({e}). "
                            "Feche e reabra o bot manualmente.")


def handle(text):
    t = text.strip().lower()
    if t in ("/start", "/ajuda", "/help"):
        notify.send_message(
            "Comandos:\n"
            "/simular — ver as ideias\n"
            "<número> — escolher da lista (fluxo completo)\n"
            "/jogo <nome> — um jogo fora da lista (fluxo completo)\n"
            "— etapas isoladas (num projeto já criado) —\n"
            "/projetos — lista os projetos e o que já têm\n"
            "/captar <slug> — baixa os trailers\n"
            "/narrar <slug> — gera a voz (VoiceBox aberto)\n"
            "/editar <slug> — edita as 4 versões e envia\n"
            "/kit <slug> — pega os textos de publicação (YT/TikTok/Insta)\n"
            "/atualizar — git pull + reinicia (deploy do código novo)\n"
            "pick N — marca a melhor versão")
        return
    if t in ("/simular", "/ideias", "/sugestoes"):
        enviar_sugestoes()
        return
    if t in ("/projetos", "/projs", "/lista"):
        listar_projetos()
        return
    if t in ("/atualizar", "/deploy", "/update"):
        handle_atualizar()
        return
    mc = re.match(r"/captar\s+(.+)", text.strip(), re.IGNORECASE)
    if mc:
        rel, _, _ = _resolve_rel(mc.group(1))
        captar(rel)
        notify.send_message(f"✅ Captação feita. Agora /narrar {os.path.basename(rel)} ou /editar {os.path.basename(rel)}.")
        return
    mn = re.match(r"/narrar\s+(.+)", text.strip(), re.IGNORECASE)
    if mn:
        rel, _, _ = _resolve_rel(mn.group(1))
        if narrar(rel):
            notify.send_message(f"✅ Voz pronta. Agora /editar {os.path.basename(rel)}.")
        return
    me = re.match(r"/editar\s+(.+)", text.strip(), re.IGNORECASE)
    if me:
        rel, _, game = _resolve_rel(me.group(1))
        editar_e_enviar(rel, game)
        return
    mk = re.match(r"/kit\s+(.+)", text.strip(), re.IGNORECASE)
    if mk:
        rel, proj, game = _resolve_rel(mk.group(1))
        saved = os.path.join(proj, "publicacao.json")
        if os.path.exists(saved):        # reenvia o já gerado (sem chamar o Claude)
            try:
                kit = json.load(open(saved, encoding="utf-8"))
                for msg in publicacao.formatar_telegram(kit, game):
                    notify.send_message(msg)
                return
            except Exception:
                pass
        enviar_kit(rel, game)            # não existe ainda -> gera na hora
        return
    m = re.match(r"pick\s+(\d+)", t)
    if m:
        handle_pick(int(m.group(1)))
        return
    if text.strip().isdigit():
        s = next((x for x in load_sugestoes() if str(x["n"]) == text.strip()), None)
        if s:
            start_flow(s["game"], s.get("mood", "adventure"), s.get("roteiro"),
                       s.get("publish"), s.get("expressions"))
        else:
            notify.send_message("Esse número não está na lista. Use '/jogo <nome>' pra um jogo fora dela.")
        return
    m2 = re.match(r"/jogo\s+(.+)", text.strip(), re.IGNORECASE)
    if m2:
        game = m2.group(1).strip()
        notify.send_message(f"🧠 Escrevendo o roteiro de {game}...")
        try:
            d = brain.roteiro_para(game)
        except Exception as e:
            notify.send_message(f"⚠️ Não consegui escrever o roteiro ({e}). "
                                "Confira se o Claude Code está instalado/logado (claude -p \"oi\").")
            return
        start_flow(game, d.get("mood", "adventure"), d.get("roteiro"),
                   d.get("publish"), d.get("expressions"))
        return
    # qualquer outra coisa NÃO dispara fluxo (evita reagir a mensagem casual)
    notify.send_message("Não entendi 🤔 Veja /ajuda. Atalhos: /simular, um número, "
                        "/jogo <nome>, /projetos, /editar <slug>, pick N.")


def main():
    global _offset
    # descarta a fila antiga: ao reiniciar, o Telegram reentrega mensagens não
    # confirmadas (ex.: um /editar velho reprocessado como se fosse agora). Aqui
    # a gente pula pro fim da fila e só processa o que chegar DAQUI pra frente.
    try:
        pendentes = notify.get_updates(offset=-1, timeout=0)
        if pendentes:
            _offset = pendentes[-1]["update_id"] + 1
    except Exception:
        pass
    try:
        notify.send_message("🤖 Bot do Thunder Games online. Manda /simular pra ver as ideias.")
    except Exception:
        pass   # se a rede estiver instável no boot, segue mesmo assim
    while True:
        try:
            for up in notify.get_updates(offset=_offset, timeout=30):
                _offset = up["update_id"] + 1
                text = (up.get("message", {}) or {}).get("text") or ""
                if text:
                    handle(text)
        except KeyboardInterrupt:
            break
        except Exception:
            # reset de conexão no long-poll é normal — só espera e tenta de novo
            time.sleep(3)


if __name__ == "__main__":
    main()
