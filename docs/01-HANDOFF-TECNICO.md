# Thunder Games — Handoff Técnico

Documento de transferência: estado técnico completo do projeto, para continuar o
trabalho em outra máquina (ou por outra pessoa/agente) sem perder contexto.

---

## 1. O que é o projeto

**Thunder Games** (@thunder_games_8) é um canal automatizado de **vídeos curtos
sobre jogos** (YouTube Shorts, Reels, TikTok). O objetivo é automatizar a
"fábrica" inteira — curadoria → roteiro → voz → captação de clipes → edição →
publicação — com o humano no controle via **Telegram**, e quase tudo rodando
**localmente** no PC (baixo custo, independência).

Formato do conteúdo: "Apresentação de Jogo" — apresenta um jogo (lançamento/
novidade indie de Steam/Switch ou curiosidade) num Short vertical (1080×1920),
com narração em voz clonada, legenda karaokê e um apresentador desenhado (PNGs).

---

## 2. Arquitetura em camadas

O projeto foi refatorado para um desenho em camadas com uma regra: **as
dependências apontam pra baixo**. Quem está em cima conhece quem está embaixo,
nunca o contrário. O motor de edição é puro e não sabe de Telegram/APIs.

```
Entradas:   bot.py (Telegram) · pipeline.py (atalho CLI) · main.py (CLI do editor)
                    │
channel/    orquestração do canal + montagem do roteiro
            ├─ pipeline.py   (new, narrate, auto, candidatos, pick, publish + CLI)
            ├─ roteiro.py    (build_roteiro, expressões, música por clima)
            ├─ publicacao.py (kit YT/TikTok/Insta)
            └─ common.py     (log, _abs, load_plano, ffprobe_dur)
                    │
services/   adaptadores externos (cada um fala com UMA integração)
            ├─ voicebox.py        (voz clonada — API local)
            ├─ telegram.py        (mensagens/vídeos/updates)
            ├─ claude.py          (Claude Code CLI headless)
            ├─ youtube.py         (busca/ranqueamento via YouTube Data API)
            ├─ download.py        (yt-dlp)
            └─ youtube_upload.py  (OAuth + upload)
                    │
editor (src/)  o motor determinístico (FFmpeg + Whisper)
            ├─ render.py         (monta o filter_complex do FFmpeg)
            ├─ transcription.py  (Whisper: legenda karaokê alinhada)
            ├─ ffmpeg_utils.py   (roda ffmpeg/ffprobe)
            ├─ validation.py · models.py · config.py · inspect_output.py · logging_utils.py
                    │
config/     transversal — usado por todas as camadas
            ├─ settings.py  (caminhos, URL do VoiceBox, id da voz, PROMPTS_DIR)
            ├─ secrets.py   (leitura única do credentials.json)
            └─ prompts.py   (carrega prompts/*.md em runtime)

dados (fora do Git):  Biblioteca/ (Personagem, Musicas, Efeitos) · projects/ · ideias/ · secrets/
```

**Princípio-chave:** trocar a porta do VoiceBox, o id da voz, a pasta da
Biblioteca ou o formato do segredo se faz **num lugar só** (`config/`). Trocar de
serviço externo = trocar um adaptador em `services/`. Ajustar o "molde" dos
prompts = editar um `.md` em `prompts/`.

---

## 3. Módulos, arquivo por arquivo

### Entradas
- **`bot.py`** — o operador no Telegram. Laço de long-polling que lê comandos e
  dispara o fluxo. Contém: `start_flow` (fluxo completo), etapas isoladas
  (`captar`, `narrar`, `editar_e_enviar`), `checkpoint_videos`, `enviar_kit`,
  `handle_atualizar`, `enviar_sugestoes`, `handle`/`main`. Usa `_offset` global
  (posição do getUpdates) e `_state` (lembra o projeto pro `pick`).
- **`pipeline.py`** (raiz) — **atalho** de ~14 linhas que delega pra
  `channel.pipeline.main`. Mantém `python pipeline.py ...` e a invocação do bot
  por subprocesso funcionando.
- **`main.py`** — CLI do motor de edição: `validate → transcribe → render →
  inspect` (e `all`). Chamado por `channel.pipeline.run_editor` via subprocesso.
- **`notify.py`** (raiz) — **atalho** de compatibilidade que reexporta
  `services.telegram` (mantém `import notify` e `python notify.py`).

### channel/
- **`common.py`** — utilitários: `log`, `_abs` (resolve caminho relativo ao
  projeto), `load_plano`, `ffprobe_dur`, e a constante `BIBLIOTECA`.
- **`roteiro.py`** — o "o quê" da edição: `build_roteiro` (monta o `roteiro.json`),
  seleção de expressões (`_normalizar_expressoes`, `escolher_expressoes`,
  `_posicoes_variadas`, `_resolve_expr_path`), `resolve_music` (música por clima,
  com aliases e fallback), e as constantes STD (legenda, animação, cortes).
- **`pipeline.py`** — orquestração: `cmd_new`, `cmd_narrate` (usa services.voicebox),
  `cmd_auto`, `cmd_candidatos`, `cmd_pick`, `cmd_publish` (usa services.youtube_upload),
  `missing_prerequisites`, `run_editor`, `_copy_final`, e o `main()` com o argparse.
- **`publicacao.py`** — `gerar_kit(game, roteiro)` (chama Claude com o prompt de
  publicação) e `formatar_telegram(kit, game)` (3 mensagens, uma por plataforma).

### services/
- **`voicebox.py`** — API local (127.0.0.1:17493). `resolve_profile_id(vb)`,
  `gerar(text, profile_id, ...) -> bytes` (POST /generate → polling /history →
  baixa /audio/{id}; trata resposta síncrona RIFF e assíncrona por id).
- **`telegram.py`** — `send_message` (retry 4x), `send_video` (multipart, retry 3x),
  `get_updates` (long polling). Lê token/chat via `config.secrets`.
- **`claude.py`** — `call(prompt, system=None) -> texto`. Roda `claude -p
  --output-format json` mandando o prompt pela **stdin** (no Windows, passar como
  argumento corta textos longos). Salva a resposta crua em `ideias/_debug_resposta.txt`.
- **`youtube.py`** — `melhores_videos(query, n)` (busca + ranqueamento com
  `_score`; penaliza filme/série e reação/gameplay; favorece "official/trailer/game").
- **`download.py`** — `baixar(target, out_path)` via yt-dlp. Baixa numa pasta
  **temporária sem acentos** e move (senão o ffmpeg do yt-dlp quebra no Windows).
  Retries contra 403/throttling; até 1080p (precisa de FFmpeg + Deno).
- **`youtube_upload.py`** — OAuth (`get_credentials`, guarda `youtube_token.json`),
  `channel_info()`, `upload(video, title, description, tags, privacy)` (categoria
  Gaming, garante `#Shorts`).

### editor (src/)
- **`render.py`** — coração da edição. Monta um `filter_complex` grande do FFmpeg:
  recorte vertical (cover crop), montagem de cortes, overlays do personagem com
  entrada deslizante (ease-out) + whoosh, legenda karaokê queimada (ASS/libass),
  mixagem narração + música + efeitos.
- **`transcription.py`** — Whisper com timestamps por palavra; alinha o **texto do
  roteiro** ao áudio (karaokê). Fallback proporcional se o Whisper faltar.
- **`ffmpeg_utils.py`** — roda ffmpeg/ffprobe (com `encoding="utf-8", errors="replace"`).
- **`validation.py`, `models.py`, `config.py`, `inspect_output.py`, `logging_utils.py`** —
  validação do roteiro.json, modelos de dados, parsing do roteiro em `Project`,
  extração de frames de revisão, logging.

### config/
- **`settings.py`** — `ROOT`, `BIBLIOTECA`, `PERSONAGEM`, `MUSICAS`, `EFEITOS`,
  `PROJECTS_DIR`, `IDEIAS_DIR`, `PROMPTS_DIR`, `SECRETS_FILE`, `YOUTUBE_TOKEN_FILE`,
  `VOICEBOX_URL`, `VOICE_PROFILE_NAME`, `VOICE_PROFILE_ID`.
- **`secrets.py`** — leitura única/caching do `credentials.json`. Acessores:
  `telegram()`, `youtube()`, `pixabay_key()`, `tiktok()`, `claude_cli()`.
- **`prompts.py`** — `load(name)` lê `prompts/<name>.md` **a cada chamada** (editar
  o .md tem efeito no próximo uso, sem reiniciar).

### Utilitários e dados
- **`brain.py`** — a "curadoria": `curar()` (5 jogos + roteiros + expressões,
  evita repetir) e `roteiro_para(game)`. Monta o prompt (regras + jogos usados +
  expressões disponíveis) e chama `services.claude`. Usa `prompts/roteiro.md`.
- **`capture.py`** — script de captação: monta a query, chama `youtube.melhores_videos`
  + `download.baixar`, registra `base/sources.json`, copia o 1º pro `assets/video.mp4`.
- **`analisar_referencias.py`** — ferramenta separada: transcreve uma pasta de
  vídeos de referência com timing (velocidade de fala, pausas) por frase → JSON + TXT.
- **`prompts/roteiro.md`**, **`prompts/publicacao.md`** — os "moldes" do Claude.
- **`Guias/00..08`** — documentação de referência (roteiro, edição, etc.). O 08 é o
  modelo de edição do criador de referência (fernandosev7n).

---

## 4. Fluxo de dados (o pipeline completo)

1. **Telegram** (`/simular` ou `/jogo`) → `bot.py`.
2. **Curadoria/roteiro:** `brain.py` → `services.claude` (Claude Code local) →
   roteiro + expressões (na ordem) + bloco publish → grava `assets/narration.txt`
   e o `plano.json`.
3. **Captação:** `capture.py` → `youtube.melhores_videos` (ranqueia) +
   `download.baixar` (yt-dlp) → `base/1.mp4..N.mp4` + `base/sources.json`.
4. **Checkpoint (Telegram):** mostra os links, pergunta se segue; aceita links
   extras (`--append`) ou `cancelar`.
5. **Voz:** `channel.pipeline.cmd_narrate` → `services.voicebox` → `assets/narration.wav`.
6. **Roteiro técnico:** `channel.roteiro.build_roteiro` → mede a narração (ffprobe),
   escolhe expressões, música por clima, cortes → grava `roteiro.json`.
7. **Edição:** `main.py all` (validate → transcribe → render → inspect) →
   `candidatos/candidatoN.mp4` (uma versão por trailer de `base/`).
8. **Entrega:** bot manda as versões no Telegram; `pick N` → `PRONTO - <jogo>.mp4`
   na pasta do jogo + em `Videos prontos/`.
9. **Kit de publicação:** `channel.publicacao` → 3 mensagens (YT/TikTok/Insta) +
   salva `projects/<slug>/publicacao.json`.
10. **Publicação (opcional):** `cmd_publish` → `services.youtube_upload` (OAuth).

---

## 5. Formatos de dados

- **`plano.json`** (por projeto) — config do vídeo: game, mood da música,
  `video_start`, `expressions` (nomes escolhidos pelo Claude), `voicebox`
  (profile/profile_id/language), bloco `publish`.
- **`roteiro.json`** (por projeto) — a "receita" que o motor executa: resolução,
  fps, layout, vídeo base, narração, música, legenda (STD), animação, cortes,
  overlays (cada expressão com start/end/position), overlay_sfx.
- **`base/sources.json`** — URLs baixadas (pro checkpoint mostrar os links).
- **`ideias/ideias_atual.json`** — as sugestões atuais do `/simular`.
- **`ideias/usados.json`** — jogos já usados (anti-repetição).
- **`publicacao.json`** (por projeto) — o kit das 3 plataformas.
- **`Catalogo.xlsx`** — catálogo (ainda **não** integrado ao fluxo).

---

## 6. Integrações externas e credenciais

`secrets/credentials.json` (fora do Git) tem:
- **youtube**: `api_key` (busca), `oauth_client_id` + `oauth_client_secret` (upload).
- **telegram**: `bot_token`, `chat_id`.
- **pixabay**: `api_key` (assets).
- **tiktok**: `client_key`, `client_secret` (postagem ainda manual).
- **claude_cli**: `command` (default "claude"), `model` (vazio = padrão do Claude Code).

Também em `secrets/`: `youtube_token.json` (token OAuth do YouTube).

**Quase tudo pesado roda local:** Claude Code, VoiceBox, FFmpeg, Whisper. APIs
externas: Telegram (controle), YouTube (buscar/subir), Pixabay (assets).

---

## 7. Comandos

### Telegram (bot.py)
- `/simular` — gera 5 ideias novas (Claude) e lista.
- `<número>` — escolhe uma ideia da lista (fluxo completo).
- `/jogo <nome>` — jogo fora da lista (Claude escreve o roteiro) (fluxo completo).
- checkpoint: `ok` / colar link do YouTube (adiciona) / `cancelar`.
- `pick N` — marca a versão N como PRONTA.
- `/projetos` — lista projetos e o que cada um já tem (🎞️ voz 🎬).
- `/captar <slug>` · `/narrar <slug>` · `/editar <slug>` — etapas isoladas.
- `/kit <slug>` — pega/gera o kit de publicação (reenvia o salvo, se houver).
- `/atualizar` (`/deploy`, `/update`) — `git pull` + auto-restart (deploy).
- `/ajuda` — lista os comandos.

### CLI (pipeline.py / channel.pipeline)
`new`, `narrate`, `plan`, `auto`, `candidatos`, `pick`, `publish`.

---

## 8. Convenções e armadilhas conhecidas (IMPORTANTE)

- **OneDrive + sandbox:** a pasta está no OneDrive. Em ambientes de sandbox, o
  `bash`/`python` podem ver cópias truncadas de arquivos recém-escritos; a máquina
  real do usuário está OK. (Ao editar via ferramentas, validar por import test.)
- **Encoding no Windows:** todos os scripts fazem `sys.stdout.reconfigure(utf-8,
  errors="replace")`, e todo subprocesso que captura saída usa `errors="replace"`.
  Sem isso, o console cp1252 quebra ao imprimir `→`/emojis/acentos.
- **Download sem acento:** o yt-dlp baixa numa pasta temp ASCII e move — o ffmpeg
  interno dele quebra com caminho acentuado ("Área de Trabalho").
- **VoiceBox assíncrono:** POST /generate devolve id; fazer polling /history até
  "completed". Se a fila travar → fechar e reabrir o app VoiceBox.
- **Claude via stdin:** o prompt vai pela stdin (arg longo com `\n`/emoji é cortado
  no Windows).
- **Música por clima tolerante:** `resolve_music` mapeia sinônimos (chill→cozy) e
  cai em `adventure` / qualquer faixa. Climas válidos = pastas em `Biblioteca/Musicas`
  (`action, adventure, cozy, epic, funny, horror`). O prompt do roteiro oferece
  exatamente esses.
- **Fila do Telegram no boot:** ao iniciar, o bot **descarta a fila antiga**
  (offset=-1) — senão reprocessa comandos velhos (ex.: um `/editar` antigo). Isso
  já foi causa de "comando fantasma".
- **Uma instância só do bot:** o Telegram só permite um listener de getUpdates.
  Dois `python bot.py` = erros de conexão (WinError 10054).
- **Não sobrescrever `Biblioteca/Personagem`:** as imagens são do usuário
  (substituídas manualmente). Nunca copiar por cima.

---

## 9. Estado atual e pendências (roadmap)

**Refatoração (concluída):** `config/` + `services/` + `channel/` + editor (`src/`),
com o bot funcionando igual. Prompts externalizados em `prompts/*.md`.

**Pendências (por impacto):**
1. **Elementos de edição estilo fernandosev7n** (maior ganho): corte por frase
   sincronizado à fala (usar timestamps do Whisper), **mão apontando**, **pop de
   palavra-chave**, zoom (Ken Burns), áudio do jogo em momentos de humor.
   Pré-requisitos (Fase 0): testar a voz no ritmo rápido (~3.8 pal/s) e conseguir
   um set de PNGs de mãos. Ver `Guias/08` e `docs/03` para o modelo.
2. **Fila com worker + `/status` + `/fila` + aviso de "ocupado"** — resolve a
   visibilidade (hoje o bot é single-thread e bloqueante; durante uma edição ele
   nem lê mensagens novas).
3. **Manifesto de proveniência** — registrar por vídeo qual prompt (nome+versão/hash),
   modelo, mood, trailers usados. Base pro pool de prompts e pro feedback.
4. **Feedback de métricas** — puxar retenção/views do YouTube e casar com o
   manifesto (fechar o ciclo). `Catalogo.xlsx` seria a tabela.
5. **Pool selecionável de prompts** (roteiro/edição/voz) + seleção via Telegram.
6. **Curadoria agendada (8h)** — reabastecer as ideias sozinha.
7. **Auto-post TikTok/Instagram** (hoje manual).
8. **Opcionais de refatoração:** separar dados em `data/`; renomear `src/ → editor/`;
   `publish/youtube_test.py` ainda lê credenciais direto; unificar `Guias` com os prompts.
9. **Migração pro Mac:** código é portável; o risco é o VoiceBox (GPU/plataforma).
   Fluxo pretendido: Mac = desenvolver, Windows = rodar, deploy via `/atualizar`.

---

## 10. Git / deploy

- Repo: `video_auto_editor` (GitHub: YvesGabriel/thunder_games).
- `.gitignore` mantém fora: `secrets/`, `projects/`, mídia, `venv/`, caches,
  `ideias/_debug_resposta.txt`, `ideias/usados.json`, `Catalogo.xlsx`.
- `.gitattributes` normaliza fins de linha (evita o aviso LF/CRLF).
- **Deploy:** editar no Mac → `git push`; no Telegram → `/atualizar` (o Windows
  faz `git pull` + reinicia). Regra: Windows é **pull-only** (não editar lá).
