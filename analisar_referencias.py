#!/usr/bin/env python3
"""Analisador de referências — extrai o RITMO de fala de vídeos de criadores.

Pega uma pasta cheia de vídeos e, pra cada um, transcreve as falas com o Whisper
guardando o TIMING: início/fim de cada frase, duração, velocidade (palavras por
segundo) e o tamanho das PAUSAS entre frases (o silêncio é onde mora o corte).

Pra cada vídeo gera dois arquivos na pasta de saída:
  <nome>.json  -> dados estruturados (pra a IA ler depois e montar o modelo de edição)
  <nome>.txt   -> versão legível, com um campo "edição:" em cada frase pra VOCÊ
                  anotar à mão o que está vendo na tela (corte, zoom, meme, etc.)

E um resumo agregado 'RESUMO_geral.json' com as médias de cada vídeo.

Uso:
    python analisar_referencias.py --pasta "C:\\caminho\\dos\\videos"
    python analisar_referencias.py --pasta ... --model medium --idioma pt
    python analisar_referencias.py --pasta ... --out "C:\\saida" --forcar

Modelos (mais lento = mais preciso, importante porque tem música por baixo):
    tiny · base · small (padrão) · medium · large
"""

import argparse
import glob
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):        # utf-8: console cp1252 do Windows quebra com acentos
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpg", ".mpeg")


def _fmt(t):
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def transcrever(video_path, model, idioma):
    """Roda o Whisper e devolve as frases com timing + o resumo do vídeo."""
    import whisper
    m = whisper.load_model(model) if isinstance(model, str) else model   # aceita nome ou modelo já carregado
    res = m.transcribe(video_path, language=idioma, word_timestamps=True, verbose=False)

    frases = []
    prev_end = 0.0
    for i, seg in enumerate(res.get("segments", []), 1):
        ini = float(seg.get("start", 0.0))
        fim = float(seg.get("end", ini))
        texto = (seg.get("text") or "").strip()
        if not texto:
            continue
        dur = max(fim - ini, 0.001)
        palavras = [{"p": (w.get("word") or "").strip(),
                     "ini": round(float(w.get("start", 0.0)), 2),
                     "fim": round(float(w.get("end", 0.0)), 2)}
                    for w in seg.get("words", [])]
        n_pal = len(palavras) or len(texto.split())
        frases.append({
            "n": i,
            "inicio": round(ini, 2),
            "fim": round(fim, 2),
            "duracao": round(dur, 2),
            "pausa_antes": round(max(ini - prev_end, 0.0), 2),
            "n_palavras": n_pal,
            "palavras_por_seg": round(n_pal / dur, 2),
            "texto": texto,
            "palavras": palavras,
        })
        prev_end = fim

    resumo = _resumir(frases, video_path)
    return frases, resumo


def _resumir(frases, video_path):
    if not frases:
        return {"arquivo": os.path.basename(video_path), "n_frases": 0}
    durs = [f["duracao"] for f in frases]
    wps = [f["palavras_por_seg"] for f in frases]
    pausas = [f["pausa_antes"] for f in frases[1:]]     # ignora a 1ª (não tem pausa antes)
    fala_total = sum(durs)
    fim_ultima = frases[-1]["fim"]
    return {
        "arquivo": os.path.basename(video_path),
        "n_frases": len(frases),
        "duracao_falada_seg": round(fala_total, 1),
        "duracao_ate_ultima_fala_seg": round(fim_ultima, 1),
        "silencio_total_seg": round(max(fim_ultima - fala_total, 0.0), 1),
        "velocidade_media_pal_seg": round(sum(wps) / len(wps), 2),
        "frase_media_seg": round(sum(durs) / len(durs), 2),
        "frase_min_seg": round(min(durs), 2),
        "frase_max_seg": round(max(durs), 2),
        "pausa_media_seg": round(sum(pausas) / len(pausas), 2) if pausas else 0.0,
        "pausa_max_seg": round(max(pausas), 2) if pausas else 0.0,
    }


def _escrever_txt(frases, resumo, out_txt):
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"# {resumo.get('arquivo')}\n")
        f.write(f"# frases: {resumo.get('n_frases')} | "
                f"velocidade média: {resumo.get('velocidade_media_pal_seg')} pal/s | "
                f"frase média: {resumo.get('frase_media_seg')}s | "
                f"pausa média: {resumo.get('pausa_media_seg')}s\n")
        f.write("# Preencha 'edição:' com o que você VÊ na tela (corte, zoom, meme, "
                "b-roll, texto na tela...).\n\n")
        for fr in frases:
            f.write(f"[{fr['n']:>3}] {fr['inicio']:.2f}s–{fr['fim']:.2f}s  "
                    f"({fr['duracao']:.2f}s · {fr['n_palavras']} pal · "
                    f"{fr['palavras_por_seg']:.1f} pal/s · pausa antes {fr['pausa_antes']:.2f}s)\n")
            f.write(f'      "{fr["texto"]}"\n')
            f.write("      edição: \n\n")


def main():
    ap = argparse.ArgumentParser(description="Extrai o ritmo de fala (timing) de uma pasta de vídeos.")
    ap.add_argument("--pasta", required=True, help="pasta com os vídeos de referência")
    ap.add_argument("--out", default=None, help="pasta de saída (padrão: <pasta>/analise)")
    ap.add_argument("--model", default="small", help="modelo Whisper: tiny/base/small/medium/large")
    ap.add_argument("--idioma", default="pt", help="idioma da fala (padrão: pt)")
    ap.add_argument("--forcar", action="store_true", help="reprocessa mesmo se o .json já existir")
    args = ap.parse_args()

    try:
        import whisper  # noqa: F401
    except ImportError:
        print("Falta o Whisper. Instale:  pip install openai-whisper")
        return 1

    pasta = os.path.abspath(args.pasta)
    if not os.path.isdir(pasta):
        print(f"Pasta não encontrada: {pasta}")
        return 1
    out_dir = os.path.abspath(args.out) if args.out else os.path.join(pasta, "analise")
    os.makedirs(out_dir, exist_ok=True)

    videos = sorted(f for f in glob.glob(os.path.join(pasta, "*"))
                    if f.lower().endswith(VIDEO_EXT))
    if not videos:
        print(f"Nenhum vídeo em {pasta} (extensões: {', '.join(VIDEO_EXT)})")
        return 1

    print(f"{len(videos)} vídeo(s). Carregando o modelo Whisper '{args.model}' uma única vez...")
    import whisper
    modelo = whisper.load_model(args.model)   # carrega 1x e reaproveita em todos

    resumos = []
    for k, vid in enumerate(videos, 1):
        nome = os.path.splitext(os.path.basename(vid))[0]
        out_json = os.path.join(out_dir, nome + ".json")
        out_txt = os.path.join(out_dir, nome + ".txt")
        if os.path.exists(out_json) and not args.forcar:
            print(f"[{k}/{len(videos)}] pulando (já existe): {nome}")
            try:
                resumos.append(json.load(open(out_json, encoding="utf-8")).get("resumo", {}))
            except Exception:
                pass
            continue
        print(f"[{k}/{len(videos)}] transcrevendo: {nome} ...")
        try:
            frases, resumo = transcrever(vid, modelo, args.idioma)
        except Exception as e:
            print(f"   ⚠️ falhou ({e}) — pulando")
            continue
        json.dump({"arquivo": os.path.basename(vid), "resumo": resumo, "frases": frases},
                  open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        _escrever_txt(frases, resumo, out_txt)
        resumos.append(resumo)
        print(f"   ✓ {resumo.get('n_frases')} frases · "
              f"{resumo.get('velocidade_media_pal_seg')} pal/s · "
              f"pausa média {resumo.get('pausa_media_seg')}s")

    if resumos:
        json.dump({"videos": resumos, "n": len(resumos)},
                  open(os.path.join(out_dir, "RESUMO_geral.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    print(f"\nPronto. Arquivos em: {out_dir}")
    print("Agora anote o campo 'edição:' nos .txt e depois peça pra IA ler os .json + RESUMO_geral.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
