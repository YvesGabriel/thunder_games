# Thunder Games — Guia de Operação

Como instalar, rodar, operar e resolver problemas. Guia prático e consolidado.

---

## 1. Pré-requisitos (software)

Programas de sistema (fora do pip):
- **Python 3** (10+).
- **FFmpeg + ffprobe** — edição e mídia. (`brew install ffmpeg` no Mac; no Windows,
  instalar e pôr no PATH.)
- **Deno** — o yt-dlp usa pros desafios de JavaScript do YouTube (senão baixa em
  qualidade baixa). (`brew install deno` / `winget install DenoLand.Deno`.)
- **Node + Claude Code** — a "IA" da curadoria/roteiro roda local:
  `npm install -g @anthropic-ai/claude-code` e depois `claude` (login). Teste:
  `claude -p "diga oi"`.
- **VoiceBox** — app local da voz clonada (API em `127.0.0.1:17493`). No Windows foi
  configurado com GPU NVIDIA. **É o único componente sensível a plataforma.**

Bibliotecas Python (na venv):
```
python3 -m venv venv
# Windows:  venv\Scripts\Activate.ps1     |  Mac/Linux: source venv/bin/activate
pip install -r requirements.txt          # openai-whisper (puxa PyTorch, grande)
pip install yt-dlp
pip install -r publish/requirements.txt  # libs do YouTube (google-api-python-client etc.)
```

---

## 2. Estrutura de pastas (IMPORTANTE)

O código acha os dados por caminho relativo. Mantenha a `Biblioteca/` **ao lado**
do repositório:

```
Canal de Games/                 (pasta-pai)
├─ video_auto_editor/           (o repositório / código)
│  ├─ config/ services/ channel/ src/ prompts/ Guias/ docs/ publish/
│  ├─ bot.py capture.py brain.py main.py pipeline.py notify.py
│  ├─ secrets/            (fora do Git: credentials.json, youtube_token.json)
│  ├─ projects/           (fora do Git: vídeos em produção — descartável)
│  └─ ideias/             (usados.json, ideias_atual.json)
├─ Biblioteca/                  (fora do Git)
│  ├─ Personagem/  (PNGs das expressões — o nome descreve a emoção)
│  ├─ Musicas/<clima>/  (action, adventure, cozy, epic, funny, horror)
│  └─ Efeitos/     (whooshes .mp3)
└─ Videos prontos/              (saída final)
```

---

## 3. Rodar

O bot é o operador. Com a venv ativa, na pasta do projeto:
```
python bot.py
```
Ele avisa no Telegram "🤖 Bot do Thunder Games online". Deixe **uma** instância só.

---

## 4. Comandos do Telegram

**Fluxo completo:**
- `/simular` — o Claude gera 5 jogos novos (evita repetir) e lista.
- Responder um **número** — inicia o fluxo daquele jogo.
- `/jogo <nome>` — um jogo fora da lista (o Claude escreve o roteiro).
- No **checkpoint** (depois de baixar os trailers): responder `ok` pra seguir,
  colar um **link do YouTube** pra adicionar mais um vídeo à edição, ou `cancelar`.
- `pick N` — marca a versão N como a PRONTA (vai pra `Videos prontos/`).
- Ao terminar, chega o **kit de publicação** (3 mensagens: YT/TikTok/Insta).

**Etapas isoladas (num projeto já criado):**
- `/projetos` — lista os projetos e o status (🎞️ trailers · 🎙️ voz · 🎬 editado).
- `/captar <slug>` — baixa os 4 trailers.
- `/narrar <slug>` — gera a voz (VoiceBox aberto).
- `/editar <slug>` — edita as 4 versões e envia.
- `/kit <slug>` — pega/gera os textos de publicação.

**Manutenção:**
- `/atualizar` (ou `/deploy`, `/update`) — `git pull` + reinicia com o código novo.
- `/ajuda` — lista tudo.

---

## 5. Fluxo típico de um vídeo (o que acontece)

1. `/simular` → escolher um número (ou `/jogo <nome>`).
2. Baixa os melhores trailers → **checkpoint** com os links → você responde `ok`.
3. Gera a narração no VoiceBox (precisa estar aberto).
4. Monta o `roteiro.json` e edita **4 versões** (uma por trailer).
5. As 4 versões chegam no Telegram → você manda `pick N`.
6. Chega o kit de publicação das 3 plataformas.
7. (Opcional) publicar no YouTube: `python pipeline.py publish --project projects/<slug> --privacy public`.

---

## 6. Onde ajustar as coisas (sem mexer no código)

- **Regras do roteiro** (formato, gancho, sem inglês, climas): `prompts/roteiro.md`.
- **Regras do kit de publicação**: `prompts/publicacao.md`.
  (Os dois são lidos a cada uso — editar o `.md` já vale no próximo comando.)
- **Caminhos, porta do VoiceBox, id da voz, climas**: `config/settings.py`.
  (No Mac, o `VOICE_PROFILE_ID` muda — ajustar aqui.)
- **Segredos** (tokens/chaves): `secrets/credentials.json`.
- **Música**: colocar `.mp3` em `Biblioteca/Musicas/<clima>/`.
- **Expressões do apresentador**: PNGs em `Biblioteca/Personagem/` (o **nome do
  arquivo descreve a emoção** — o Claude escolhe pelos nomes).

---

## 7. Deploy (Mac desenvolve, Windows roda)

1. No Mac: `git add . && git commit -m "..." && git push`.
2. No Telegram: `/atualizar` → o Windows faz `git pull` e reinicia.
- Regra: **não editar código no Windows** (só pull), senão o pull dá conflito.
- Use o `/atualizar` com o bot **ocioso**.

---

## 8. Solução de problemas (troubleshooting)

- **"Erro na narração" / VoiceBox travado** → feche e reabra o app VoiceBox e rode
  de novo. A fila do VoiceBox às vezes emperra.
- **"Faltando: música"** → não há `.mp3` no clima; o `resolve_music` já cai em
  `cozy`/`adventure`, mas confira `Biblioteca/Musicas/<clima>/`.
- **Download 403 / vídeo indisponível** → é throttling do YouTube; o sistema pula o
  que falhar e segue. Os retries do yt-dlp costumam resolver.
- **Vídeo em qualidade baixa** → o Deno não está instalado/no PATH (necessário pro
  1080p).
- **Erros de encoding (UnicodeDecode/Encode) / threads _readerthread** → já tratado
  com `errors="replace"` e download em pasta temp sem acento; se voltar, é sinal de
  um subprocesso novo sem esse cuidado.
- **"Comando fantasma" (algo dispara sozinho ao reiniciar)** → era a fila antiga do
  Telegram; o bot agora descarta no boot. Se persistir, confirme que só há **uma**
  instância rodando.
- **WinError 10054 repetido** → duas instâncias do bot. Feche uma.
- **Claude não responde / "não encontrei o Claude Code"** → `claude` não está no
  PATH ou não logado. Teste `claude -p "oi"`.
- **`/kit` "mandou vídeo"** → não é o `/kit`; era um comando anterior na fila sendo
  processado. Rode com o bot ocioso.

---

## 9. Comandos úteis de CLI (sem o bot)

```
python pipeline.py new     --name <slug> --game "<Nome>" --mood adventure
python capture.py          --project projects/<slug>
python pipeline.py narrate --project projects/<slug>      # VoiceBox aberto
python pipeline.py candidatos --project projects/<slug>   # edita as versões
python pipeline.py pick    --num 2 --project projects/<slug>
python pipeline.py publish --project projects/<slug> --privacy public
python publish/youtube_upload.py auth                     # 1ª autenticação YouTube

# Analisar vídeos de referência (ritmo de fala):
python analisar_referencias.py --pasta "<pasta com mp4>" --model small
```
