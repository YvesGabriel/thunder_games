"""Modelos de dados (dataclasses) que representam um projeto de vídeo.

Todos os caminhos ficam ABSOLUTOS depois do carregamento (ver config.py),
para o render/validação não dependerem do diretório de execução.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Overlay:
    """Uma imagem que aparece por cima do vídeo por um intervalo de tempo."""
    id: str
    path: str
    start: float                 # segundos (na linha do tempo final)
    end: float                   # segundos
    width_frac: float = 0.30     # largura da imagem como fração da largura do vídeo
    slide_in: bool = True        # entra com animação (senão, aparece parada)
    exit: str = "none"           # "none" (só some) ou "slide" (sai deslizando)
    position: str = "right"      # "left" | "right" | "center"
    enter: str = ""              # "left"|"right"|"top"|"bottom" (vazio = derivado da posição)
    sfx: Optional[str] = None    # som ao entrar (ex.: whoosh); se vazio, usa overlay_sfx

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def enter_from(self) -> str:
        """Direção de entrada; se não definida, vem do lado da posição."""
        if self.enter:
            return self.enter
        return {"left": "left", "right": "right", "center": "bottom"}.get(self.position, "right")


@dataclass
class Project:
    """Descrição completa e resolvida de um projeto de vídeo."""
    name: str
    root: str                    # pasta do projeto (absoluta)

    video_path: str
    video_start: float           # de que ponto do vídeo principal começar (s)

    narration_path: str
    music_path: Optional[str]
    narration_volume: float
    music_volume: float

    width: int
    height: int
    fps: int
    layout: str                  # "cover" | "blurred"
    duration: Optional[float]    # None => usar a duração da narração

    subtitles_enabled: bool
    subtitle_style: dict
    subtitles_path: str          # .srt (gerado pelo transcribe ou fornecido)
    # Fonte da legenda:
    #  "script"     -> usa o texto do roteiro (recomendado; sem erros de ASR)
    #  "transcribe" -> transcreve o áudio da narração (Whisper)
    subtitles_source: str = "script"
    subtitles_text: Optional[str] = None   # texto do roteiro (se source="script")
    subtitles_align: bool = True           # alinhar ao áudio via Whisper (senão, proporcional)
    slide_seconds: float = 0.25            # duração da animação de entrada/saída das imagens
    subtitles_mode: str = "static"         # "static" (presets) ou "karaoke" (palavra a palavra)
    easing: str = "ease_out"               # "ease_out" (impacto) ou "linear"
    overlay_sfx: List[str] = field(default_factory=list)  # sons de entrada ciclados
    cut_seconds: float = 0.0               # >0 = montagem com cortes a cada N s (dinâmico)

    overlays: List[Overlay] = field(default_factory=list)

    output_dir: str = ""
    output_name: str = "final.mp4"

    @property
    def output_path(self) -> str:
        import os
        return os.path.join(self.output_dir, self.output_name)

    @property
    def review_frames_dir(self) -> str:
        import os
        return os.path.join(self.output_dir, "review_frames")
