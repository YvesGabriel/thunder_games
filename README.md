# video_auto_editor

Pipeline **local, programático e determinístico** para montar vídeos verticais
(9:16) de games — sem CapCut, sem navegador, sem upload manual.

Você fornece: vídeo principal + narração + música + imagens + um `roteiro.json`.
O programa gera automaticamente o MP4 final com:

- formato vertical 9:16;
- vídeo principal adaptado para preencher a tela (`cover` ou `blurred`);
- áudio original do vídeo **mutado**;
- narração + música (em volume baixo);
- legendas a partir da narração;
- imagens aparecendo em tempos definidos, no canto inferior direito,
  **deslizando da direita para a esquerda**;
- exportação em MP4.

> Filosofia: **determinístico**. O mesmo `roteiro.json` + os mesmos arquivos
> geram sempre o mesmo vídeo. Nada de arrastar clipes na mão.

---

## 1. Requisitos

- **Python 3.9+**
- **FFmpeg** (com `ffmpeg` e `ffprobe` no PATH)
- (Opcional) **openai-whisper** — só para o comando `transcribe` (gerar legendas).

## 2. Instalar as dependências Python

```bash
pip install -r requirements.txt
```

Isso instala o `openai-whisper` (que puxa o PyTorch — é grande).
Se você já tem uma legenda `.srt` pronta, pode pular o whisper e usar o resto.

## 3. Instalar / verificar o FFmpeg

O FFmpeg **não** é instalado pelo pip. Instale como programa do sistema:

- **Windows:** `winget install Gyan.FFmpeg` (depois feche e reabra o terminal)
- **macOS:** `brew install ffmpeg`
- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`

Verifique:

```bash
ffmpeg -version
ffprobe -version
```

## 4. Estrutura do projeto

```
video_auto_editor/
├── main.py                 # CLI (validate / transcribe / render / inspect / all)
├── requirements.txt
├── roteiro.example.json    # exemplo de roteiro
├── README.md
├── src/
│   ├── logging_utils.py    # logs e "relatórios"
│   ├── ffmpeg_utils.py     # wrappers de ffmpeg/ffprobe
│   ├── models.py           # dataclasses (Project, Overlay)
│   ├── config.py           # lê o roteiro.json -> Project
│   ├── validation.py       # valida arquivos e tempos (relatório)
│   ├── transcription.py    # narração -> legenda .srt (Whisper)
│   ├── render.py           # monta o filtergraph e chama o FFmpeg
│   └── inspect_output.py   # inspeciona o MP4 + frames de revisão
└── projects/
    └── video_001/
        ├── roteiro.json
        ├── assets/         # seus arquivos entram aqui
        └── output/         # gerado automaticamente
```

## 5. Como organizar os arquivos

Dentro de `projects/<seu_video>/assets/` coloque:

- `video.mp4`  — o vídeo principal (ex.: trailer);
- `narration.wav` — a narração (ex.: exportada do VoiceBox);
- `music.mp3` — a trilha sonora;
- `personagem/*.png` — as imagens (ex.: expressões do personagem).

Depois edite `projects/<seu_video>/roteiro.json` apontando para esses arquivos
(caminhos **relativos à pasta do roteiro**).

## 6. O `roteiro.json`

```json
{
  "project": "video_001",
  "resolution": { "width": 1080, "height": 1920 },
  "fps": 30,
  "layout": "cover",                       // "cover" ou "blurred"
  "video": { "path": "assets/video.mp4", "start": 3.8 },
  "narration": "assets/narration.wav",
  "music": { "path": "assets/music.mp3", "volume": 0.12 },
  "duration": null,                          // null = usa a duração da narração
  "subtitles": {
    "enabled": true,
    "mode": "karaoke",                       // "static" (presets) ou "karaoke" (palavra a palavra)
    "source": "script",                      // "script" (recomendado) ou "transcribe"
    "text_path": "assets/narration.txt",     // texto do roteiro (ou use "text": "...")
    "align": true,                           // alinhar o tempo ao áudio (Whisper)
    "karaoke": { "font_name": "Anton", "margin_v": 540 },  // opções do modo karaokê
    "path": "output/subtitles.srt"
  },
  "animation": { "slide_seconds": 0.28, "easing": "ease_out" },
  "overlay_sfx": [ "assets/whoosh1.mp3", "assets/whoosh2.mp3" ],  // sons de entrada (ciclados)
  "overlays": [
    { "id": "confuso", "path": "assets/personagem/confuso.png",
      "start": 0.3, "end": 6.0, "width_frac": 0.32,
      "slide_in": true, "exit": "none" }
  ]
}
```

Campos dos overlays:

- `start` / `end`: quando a imagem aparece/some (segundos, na linha final);
- `width_frac`: largura da imagem como fração da largura do vídeo (0.46 = 46%);
- `position`: `"left"`, `"right"` ou `"center"` (personagem "apresentador");
- `enter`: `"left"`/`"right"`/`"top"`/`"bottom"` (de onde entra; vazio = derivado da posição);
- `slide_in`: entra com animação (true/false);
- `sfx`: som ao entrar (se vazio, usa a lista `overlay_sfx` ciclada);
- `exit`: `"none"` (só some) ou `"slide"` (sai deslizando).

### Legendas: modo `karaoke` vs `static`

- **`karaoke`** (estilo CapCut/Shorts): fonte pesada, blocos de 2–3 palavras e a
  **palavra falada destacada em amarelo** com efeito "pop". Precisa do texto do
  roteiro; com `align: true` + Whisper a sincronia é palavra a palavra exata
  (sem Whisper, cai para tempo proporcional). Opções em `subtitles.karaoke`:
  `font_name`, `font_size`, `outline`, `margin_v`, `highlight_colour`,
  `words_per_block`, `word_scale`. Instale a fonte **Anton** para o visual clássico.
- **`static`**: legenda por linha usando um dos presets (`bold_yellow`, `boxed`…).

### Personagem "apresentador" (posição + entrada)

Alterne `position` entre `left` / `right` / `center` ao longo do vídeo (ex.: ~40%
esquerda, 40% direita, 20% centro em momentos de impacto). Cada aparição entra de
fora da tela na direção do lado, com `easing: "ease_out"` e um `whoosh` (via
`overlay_sfx`). Mantenha `width_frac` e `margin_v` da legenda de forma que o
personagem nunca cubra o texto.

> Dica: use imagens PNG **com fundo transparente** (recortadas). Para a imagem
> ficar sempre em tela trocando só de expressão, deixe os overlays **contíguos**
> (`end` de um = `start` do próximo) e ligue `slide_in` só no primeiro.

### Presets de legenda

Escolha em `subtitles.preset` (e ajuste com `subtitles.style`):

- `classic` — branco com contorno preto (limpo);
- `bold_yellow` — amarelo negrito com contorno grosso (bem "viral");
- `boxed` — texto branco dentro de caixa preta semitransparente;
- `outline_heavy` — branco com contorno bem grosso;
- `shadow_pop` — branco com sombra marcada.

`margin_v` (em `style`) sobe/desce a legenda (maior = mais alta). Cores em
formato ASS `&HAABBGGRR` (AA = transparência, 00 = opaco).

## 7. Comandos

Aponte para o projeto com `--project` (a pasta que contém o `roteiro.json`).

### validate — confere tudo antes de renderizar
```bash
python main.py validate --project projects/video_001
```
Mostra um relatório com os arquivos encontrados e os problemas.

### transcribe — gera a legenda .srt
```bash
python main.py transcribe --project projects/video_001 --model base
```
A fonte da legenda depende do `roteiro.json`:

- **`source: "script"` (recomendado):** usa o **texto do roteiro** (`text` ou
  `text_path`). Como o áudio foi gerado a partir desse texto, as palavras saem
  sempre corretas. O tempo de cada legenda vem do **alinhamento** do texto ao
  áudio (timestamps do Whisper). Se `align: false` ou o Whisper não estiver
  instalado, o tempo é distribuído de forma **proporcional** ao tamanho das
  frases (sem depender do Whisper).
- **`source: "transcribe"`:** transcreve o áudio da narração com o Whisper
  (pode conter erros de reconhecimento). Use só se não tiver o texto.

Modelos Whisper: `tiny`, `base`, `small`, `medium` (maior = melhor e mais lento).

### render — gera o vídeo final
```bash
python main.py render --project projects/video_001
```
Cria `projects/video_001/output/final.mp4`.

### inspect — confere o resultado e extrai frames de revisão
```bash
python main.py inspect --project projects/video_001
```
Imprime resolução, duração, fps, tamanho, se tem áudio, se a duração bate com
a narração, a lista de overlays, e extrai frames em
`output/review_frames/` (início, meio e fim de cada imagem).

### all — faz tudo em sequência
```bash
python main.py all --project projects/video_001
```

## 8. Frames de revisão (e futuro MCP)

O `inspect` extrai, para cada imagem do roteiro, 3 frames do vídeo final:
início, meio e pouco antes do fim da aparição. Eles ficam em
`output/review_frames/<id>_<inicio|meio|fim>.png`.

A ideia é que, no futuro, uma IA (via MCP) possa **olhar esses frames** e sugerir
correções (ex.: "a imagem está cobrindo a legenda", "entrou tarde demais").

## 9. Decisões técnicas

- **Python + FFmpeg**: simples, confiável, sem servidor nem GUI. Um único
  `filter_complex` monta tudo numa passada — rápido e reprodutível.
- **Legenda a partir do roteiro (não do áudio)**: como o áudio é gerado a
  partir do texto escrito, usamos esse texto para as palavras (sempre corretas)
  e o áudio só para o tempo (alinhamento). Transcrever de volta seria redundante
  e introduziria erros. Fallback proporcional funciona sem Whisper.
- **Legendas via .ass**: o programa converte a `.srt` em `.ass` com
  `PlayResX/PlayResY` iguais à resolução do vídeo. Assim `FontSize`, `MarginV`
  e contorno ficam em **pixels reais** e o resultado é determinístico (o
  `force_style` direto na `.srt` depende da resolução interna do libass e é
  imprevisível).
- **Animação por expressão**: o deslizar é feito com expressões no `x` do filtro
  `overlay` (usando `t`, `W`, `w`), sem keyframes — 100% determinístico.
- **Caminho da legenda**: rodamos o FFmpeg com `cwd` na pasta da legenda e
  passamos só o nome do arquivo, evitando problemas de escape com espaços,
  acentos e `C:` no Windows.
- **Módulos separados**: cada etapa (validar, transcrever, renderizar,
  inspecionar) é uma função isolada — fácil de testar e de expor como *tool* MCP.

## 10. Limitações da primeira versão

- O vídeo principal precisa ser **pelo menos tão longo** quanto a duração final
  (não há loop automático se ele for curto).
- As legendas seguem os tempos do Whisper (pode precisar de ajuste fino).
- Um estilo de legenda por vídeo (sem estilos por trecho).
- Overlays são imagens estáticas (PNG/JPG). Sem vídeo como overlay ainda.
- Uma trilha de música e uma de narração (sem SFX pontuais ainda — planejado).
- `blurred` e `cover` cobrem os casos comuns; efeitos mais elaborados ficam para depois.

## 11. Como evoluir para MCP depois

O código já está modular. Para expor como MCP, basta criar um servidor fino que
chame estas funções:

- `config.load_project(path)` → carrega o roteiro;
- `validation.validate_project(project)` → relatório de validação;
- `transcription.generate_subtitles(...)` → gera a .srt;
- `render.render(project)` → gera o MP4;
- `inspect_output.inspect_output(project)` → relatório + frames de revisão.

Cada uma vira uma *tool*. Como o `inspect` já produz frames em disco, a IA pode
lê-los e sugerir correções no `roteiro.json`, fechando o ciclo de revisão visual.

## 12. Erros comuns (troubleshooting)

- **"FFmpeg não encontrado"** → instale o FFmpeg e reabra o terminal (seção 3).
- **"O pacote 'openai-whisper' não está instalado"** → `pip install openai-whisper`
  (ou forneça uma `.srt` pronta e pule o `transcribe`).
- **Legenda não aparece** → rode `transcribe` antes do `render`, ou confira o
  caminho em `subtitles.path`. O `render` avisa se a `.srt` não existe.
- **"fim ultrapassa a duração final"** → algum overlay tem `end` maior que a
  duração da narração; ajuste os tempos no `roteiro.json`.
- **Imagem fora do lugar** → ajuste `width_frac`; imagens muito largas invadem o
  centro. Uma boa faixa é 0.28–0.36.
- **Vídeo termina antes da narração** → o vídeo principal é mais curto que a
  narração; use um vídeo mais longo ou defina `duration` menor.
```
