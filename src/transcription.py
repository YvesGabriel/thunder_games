"""Geração de legendas (.srt).

Duas fontes:
  - script (recomendado): usa o TEXTO do roteiro (sempre correto). O tempo vem
    do alinhamento do texto ao áudio (timestamps do Whisper); se o Whisper não
    estiver disponível ou align=False, usa tempo proporcional ao tamanho da frase.
  - transcribe: transcreve o áudio da narração com o Whisper (pode ter erros).

O texto do roteiro é preferível porque o áudio foi GERADO a partir dele — não
faz sentido reconhecer de volta e arriscar erros.
"""

import difflib
import os
import re
import unicodedata
from typing import List, Optional, Tuple

from .ffmpeg_utils import get_duration
from .logging_utils import get_logger

log = get_logger()

Cue = Tuple[float, float, str]   # (start, end, texto)


# ----------------------------------------------------------------------------
# Utilidades de tempo / escrita
# ----------------------------------------------------------------------------
def _format_ts(seconds: float) -> str:
    """Segundos -> 'HH:MM:SS,mmm' (formato SRT)."""
    if seconds < 0:
        seconds = 0
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(cues: List[Cue], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(cues, start=1):
            f.write(f"{i}\n{_format_ts(start)} --> {_format_ts(end)}\n{text.strip()}\n\n")


# ----------------------------------------------------------------------------
# Preparo do texto do roteiro
# ----------------------------------------------------------------------------
def _normalize_word(w: str) -> str:
    """minúsculas, sem acentos e sem pontuação (para comparar palavras)."""
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", w.lower())


def _split_script_into_lines(text: str, max_chars: int = 50) -> List[str]:
    """Quebra o texto do roteiro em linhas curtas de legenda.

    Divide por pontuação de fim de frase e quebra frases longas por tamanho.
    """
    text = re.sub(r"\s+", " ", text.strip())
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    lines: List[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            lines.append(sent)
            continue
        cur = ""
        for word in sent.split():
            if cur and len(cur) + 1 + len(word) > max_chars:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            lines.append(cur)
    return lines


# ----------------------------------------------------------------------------
# Tempo: proporcional (sem áudio) ou alinhado (com Whisper)
# ----------------------------------------------------------------------------
def _proportional_times(lines: List[str], total: float) -> List[Cue]:
    """Distribui o tempo total proporcional ao tamanho de cada linha."""
    weights = [max(1, len(ln)) for ln in lines]
    soma = sum(weights)
    cues: List[Cue] = []
    t = 0.0
    for ln, w in zip(lines, weights):
        dur = total * (w / soma)
        cues.append((t, t + dur, ln))
        t += dur
    return cues


def _get_word_timestamps(audio_path: str, model_size: str, language: str):
    """Roda o Whisper com timestamps por palavra. Retorna [(palavra, ini, fim), ...]."""
    import whisper  # import tardio
    log.info("Carregando modelo Whisper (%s) para alinhar o tempo...", model_size)
    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, language=language, word_timestamps=True, verbose=False)
    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words.append((w.get("word", ""), float(w.get("start", 0.0)), float(w.get("end", 0.0))))
    return words


def _align_lines_to_words(lines: List[str], words, total: float) -> List[Cue]:
    """Alinha as linhas do roteiro às palavras do áudio (com tempos do Whisper).

    Usa alinhamento de sequência entre as palavras do roteiro e as do Whisper.
    Palavras sem correspondência são interpoladas pelos vizinhos.
    """
    # tokens do roteiro: (indice_da_linha, palavra_normalizada)
    script_tokens: List[Tuple[int, str]] = []
    for li, line in enumerate(lines):
        for w in line.split():
            nw = _normalize_word(w)
            if nw:
                script_tokens.append((li, nw))

    ww_norm = [_normalize_word(w[0]) for w in words]
    sm = difflib.SequenceMatcher(a=[t[1] for t in script_tokens], b=ww_norm, autojunk=False)
    mapping = {}
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            mapping[block.a + k] = block.b + k

    # para cada linha, junta os tempos das palavras que casaram
    raw: List[Optional[Tuple[float, float]]] = []
    for li in range(len(lines)):
        idxs = [i for i, (c, _) in enumerate(script_tokens) if c == li]
        starts = [words[mapping[i]][1] for i in idxs if i in mapping]
        ends = [words[mapping[i]][2] for i in idxs if i in mapping]
        raw.append((min(starts), max(ends)) if starts and ends else None)

    # interpola linhas sem correspondência
    known = [(i, t) for i, t in enumerate(raw) if t is not None]
    if not known:
        return _proportional_times(lines, total)

    cues: List[Cue] = []
    for i, line in enumerate(lines):
        if raw[i] is not None:
            start, end = raw[i]
        else:
            prev = next(((j, raw[j]) for j in range(i - 1, -1, -1) if raw[j]), None)
            nxt = next(((j, raw[j]) for j in range(i + 1, len(raw)) if raw[j]), None)
            if prev and nxt:
                start = prev[1][1]
                end = nxt[1][0]
            elif prev:
                start = prev[1][1]
                end = min(total, start + 1.5)
            else:  # só há próximos
                end = nxt[1][0]
                start = max(0.0, end - 1.5)
        cues.append((start, max(start + 0.3, end), line))

    # garante ordem crescente e não-sobreposição
    for i in range(1, len(cues)):
        s, e, txt = cues[i]
        ps, pe, _ = cues[i - 1]
        if s < pe:
            s = pe
        cues[i] = (s, max(s + 0.3, e), txt)
    return cues


# ----------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------
def subtitles_from_script(
    script_text: str,
    audio_path: str,
    out_srt: str,
    align: bool = True,
    model_size: str = "base",
    language: str = "pt",
) -> str:
    """Gera a .srt a partir do TEXTO do roteiro. Retorna o caminho da .srt."""
    lines = _split_script_into_lines(script_text)
    if not lines:
        raise ValueError("Texto do roteiro vazio para gerar legendas.")

    total = get_duration(audio_path) or 0.0

    if align:
        try:
            words = _get_word_timestamps(audio_path, model_size, language)
            if words:
                cues = _align_lines_to_words(lines, words, total)
                log.info("Legenda alinhada ao áudio (%d linhas).", len(cues))
            else:
                raise RuntimeError("Whisper não retornou palavras.")
        except ImportError:
            log.warning("openai-whisper não instalado — usando tempo proporcional.")
            cues = _proportional_times(lines, total or 1.0)
        except Exception as e:  # falha do alinhamento -> proporcional
            log.warning("Falha ao alinhar (%s) — usando tempo proporcional.", e)
            cues = _proportional_times(lines, total or 1.0)
    else:
        cues = _proportional_times(lines, total or 1.0)

    _write_srt(cues, out_srt)
    log.info("Legenda salva em: %s", out_srt)
    return out_srt


# ----------------------------------------------------------------------------
# Legendas KARAOKÊ (palavra a palavra, estilo CapCut/Shorts)
# ----------------------------------------------------------------------------
def _split_blocks(text: str, words_per_block: int = 3):
    """Quebra o texto em blocos curtos (2–5 palavras) respeitando frases."""
    text = re.sub(r"\s+", " ", text.strip())
    blocks = []
    for sent in re.split(r"(?<=[.!?…])\s+", text):
        words = [w for w in sent.split() if w]
        for i in range(0, len(words), max(1, words_per_block)):
            blocks.append(words[i:i + words_per_block])
    return blocks


def _proportional_blocks(blocks, total: float):
    """Sem áudio: distribui o tempo proporcional ao tamanho das palavras."""
    bw = [sum(len(w) for w in b) or 1 for b in blocks]
    tot = sum(bw) or 1
    t = 0.0
    out = []
    for b, wt in zip(blocks, bw):
        bs, be = t, t + total * wt / tot
        t = be
        ww = [max(1, len(w)) for w in b]
        s2 = sum(ww)
        c = bs
        timed = []
        for w, cw in zip(b, ww):
            ws = c
            we = c + (be - bs) * cw / s2
            c = we
            timed.append((w, ws, max(ws + 0.12, we)))
        out.append(timed)
    return out


def _align_blocks_to_words(blocks, words, total: float):
    """Com áudio: casa as palavras do roteiro às palavras do Whisper (tempos)."""
    tokens = [(bi, w) for bi, b in enumerate(blocks) for w in b]
    ww_norm = [_normalize_word(w[0]) for w in words]
    sm = difflib.SequenceMatcher(a=[_normalize_word(t[1]) for t in tokens],
                                 b=ww_norm, autojunk=False)
    mp = {}
    for bk in sm.get_matching_blocks():
        for k in range(bk.size):
            mp[bk.a + k] = bk.b + k
    times = [None] * len(tokens)
    for i in range(len(tokens)):
        if i in mp:
            times[i] = (words[mp[i]][1], words[mp[i]][2])
    for i in range(len(tokens)):          # interpola faltantes
        if times[i] is None:
            prev = next((times[j] for j in range(i - 1, -1, -1) if times[j]), None)
            nxt = next((times[j] for j in range(i + 1, len(tokens)) if times[j]), None)
            if prev and nxt:
                times[i] = (prev[1], max(prev[1] + 0.1, nxt[0]))
            elif prev:
                times[i] = (prev[1], prev[1] + 0.25)
            elif nxt:
                times[i] = (max(0.0, nxt[0] - 0.25), nxt[0])
            else:
                times[i] = (0.0, total or 1.0)
    # monta blocos garantindo ordem crescente
    out, idx, last = [], 0, 0.0
    for b in blocks:
        timed = []
        for w in b:
            s, e = times[idx]
            idx += 1
            s = max(s, last)
            e = max(s + 0.12, e)
            last = e
            timed.append((w, s, e))
        out.append(timed)
    return out


def _write_karaoke_ass(timed_blocks, out_ass: str, style: dict, width: int, height: int) -> None:
    """Escreve a .ass karaokê: cada palavra falada vira 1 evento (destaque +
    escala), e o bloco surge com efeito 'pop'."""
    bold = -1 if style.get("bold", True) else 0
    hl = style.get("highlight_colour", "&H0000D4FF")
    wscale = int(style.get("word_scale", 114))
    pop = style.get("pop", True)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.get('font_name','Anton')},{style.get('font_size',92)},{style.get('primary_colour','&H00FFFFFF')},&H000000FF,{style.get('outline_colour','&H00000000')},{style.get('back_colour','&HA0000000')},{bold},0,0,0,100,100,0,0,{style.get('border_style',1)},{style.get('outline',8)},{style.get('shadow',3)},{style.get('alignment',2)},60,60,{style.get('margin_v',540)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def esc(s):
        return s.replace("{", "(").replace("}", ")")

    lines = [header]
    for block in timed_blocks:
        for i, (word, s, e) in enumerate(block):
            parts = []
            for j, (w, _, _) in enumerate(block):
                if j == i:   # palavra falada: amarela + maior
                    parts.append("{\\1c%s&\\fscx%d\\fscy%d}%s{\\r}" % (hl, wscale, wscale, esc(w)))
                else:
                    parts.append(esc(w))
            txt = " ".join(parts)
            if pop and i == 0:   # bloco surge com 'pop'
                txt = "{\\fscx82\\fscy82\\t(0,120,\\fscx100\\fscy100)}" + txt
            lines.append(f"Dialogue: 0,{_seconds_to_ass_time(s)},{_seconds_to_ass_time(e)},"
                         f"Default,,0,0,0,,{txt}\n")
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write("".join(lines))


def karaoke_ass_from_script(script_text: str, audio_path: str, out_ass: str,
                            style: dict, width: int, height: int,
                            align: bool = True, model_size: str = "base",
                            language: str = "pt") -> str:
    """Gera a .ass karaokê a partir do texto do roteiro. Retorna o caminho."""
    blocks = _split_blocks(script_text, int(style.get("words_per_block", 3)))
    if not blocks:
        raise ValueError("Texto do roteiro vazio para gerar legendas.")
    total = get_duration(audio_path) or 0.0
    timed = None
    if align:
        try:
            words = _get_word_timestamps(audio_path, model_size, language)
            if words:
                timed = _align_blocks_to_words(blocks, words, total)
                log.info("Karaokê alinhado ao áudio (%d blocos).", len(blocks))
        except ImportError:
            log.warning("openai-whisper ausente — karaokê com tempo proporcional.")
        except Exception as e:
            log.warning("Falha ao alinhar (%s) — karaokê proporcional.", e)
    if timed is None:
        timed = _proportional_blocks(blocks, total or 1.0)
    _write_karaoke_ass(timed, out_ass, style, width, height)
    log.info("Legenda karaokê salva em: %s", out_ass)
    return out_ass


def _seconds_to_ass_time(t: float) -> str:
    """62.5 -> '0:01:02.50' (ASS)."""
    if t < 0:
        t = 0.0
    cs = int(round((t - int(t)) * 100))
    s = int(t) % 60
    m = (int(t) // 60) % 60
    h = int(t) // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_subtitles(
    narration_path: str,
    out_srt: str,
    model_size: str = "base",
    language: str = "pt",
) -> str:
    """Transcreve o ÁUDIO da narração e grava uma .srt (fonte 'transcribe').

    Prefira `subtitles_from_script` quando você tem o texto do roteiro.
    """
    if not os.path.exists(narration_path):
        raise FileNotFoundError(f"Narração não encontrada: {narration_path}")
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "O pacote 'openai-whisper' não está instalado.\n"
            "Instale com:  pip install openai-whisper"
        ) from e

    log.info("Carregando modelo Whisper (%s)...", model_size)
    model = whisper.load_model(model_size)
    log.info("Transcrevendo narração: %s", narration_path)
    result = model.transcribe(narration_path, language=language, verbose=False)
    segments = result.get("segments", [])
    cues = [(float(s["start"]), float(s["end"]), s["text"]) for s in segments]
    if not cues:
        cues = [(0.0, get_duration(narration_path) or 5.0, result.get("text", ""))]
    _write_srt(cues, out_srt)
    log.info("Legenda salva em: %s (%d blocos)", out_srt, len(cues))
    return out_srt
