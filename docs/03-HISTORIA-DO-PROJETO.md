# Thunder Games — A História do Projeto

O relato de como o projeto foi se construindo ao longo da conversa: cada etapa,
cada virada de rumo, e o raciocínio por trás das decisões. Serve para entender
não só *o que* existe, mas *por que* ficou assim.

---

## Capítulo 1 — A visão inicial

O ponto de partida foi uma ambição clara: um **canal automatizado de vídeos curtos
sobre jogos**, publicando em YouTube Shorts, Reels e TikTok, com o mínimo de
trabalho manual e o dono no controle. A ideia era planejar tudo primeiro e depois
executar, usando referências de inspiração.

As primeiras decisões definiram a identidade técnica:
- Foco em **Steam e Nintendo Switch** (lançamentos/novidades indie, curiosidades).
- **Sem rosto** — nada de gravar a si mesmo.
- **Voz clonada** (não uma voz genérica de TTS) — daí a escolha do **VoiceBox**.
- **Português**, tom empolgado.
- Usar **trailers oficiais** como base de imagem (as publishers costumam liberar).
- Ritmo de ~3 vídeos por semana.

Desse período nasceu o formato **"Apresentação de Jogo"**, destilado a partir de
transcrições de vídeos de referência: um gancho forte, o desenvolvimento explicando
a graça do jogo, uma chamada pra marcar um amigo, e um fecho padrão com o nome do
jogo. Esse molde virou a espinha do roteiro.

---

## Capítulo 2 — A grande virada: o editor local

O primeiro grande *pivot* veio quando ficou claro que **editar com IA + CapCut era
lento, impreciso e caro**. A decisão foi ousada e definiu o projeto: **construir um
editor de vídeo local e programático** (Python + FFmpeg), determinístico e
reutilizável. Em vez de arrastar coisas numa timeline, o vídeo passaria a ser
descrito por um `roteiro.json` e renderizado por código — mesmo roteiro, mesmo
vídeo, sempre.

Um insight importante apareceu aqui: como o áudio é **gerado a partir do texto** do
roteiro, não fazia sentido transcrever o áudio de volta pra fazer a legenda. Melhor
usar o **texto original** e só pegar o *tempo* das palavras via Whisper. Isso deixou
o karaokê preciso (o texto é sempre correto).

Vieram então os elementos visuais da identidade:
- **Legenda karaokê** palavra por palavra (fonte Anton, pesada, posicionada alta),
  com destaque amarelo e "pop".
- Um **apresentador desenhado** (PNGs, o "Golden Boy"/Kintaro) que entra deslizando
  de fora da tela, com som de *whoosh*, e alterna posições.
- A regra de posições: **esquerda / direita / centro**, com viés ~40/40/20, sem
  repetir a posição em seguida.

Tudo isso foi consolidado dentro do editor, e depois o **fluxo inteiro** foi
amarrado num orquestrador — o embrião do que hoje é o `channel/pipeline`.

---

## Capítulo 3 — Captação, publicação e as dores do OAuth

Com o editor de pé, o foco virou pra **alimentar** e **publicar**:
- `capture.py` nasceu pra baixar os trailers com **yt-dlp**, ranqueando os melhores
  pela **API de dados do YouTube**.
- O comando `publish` pra subir no YouTube.

A integração com o YouTube teve seu quinhão de sofrimento, documentado aqui pra
ninguém repetir: o `redirect_uri_mismatch` exigiu criar um cliente OAuth do tipo
**Desktop**; o `access_denied` exigiu se adicionar como **usuário de teste**; e,
depois de subir, o vídeo **não foi classificado como Short** — a correção foi
garantir o `#Shorts` na descrição automaticamente. Também entraram descrição
caprichada, comentário pra fixar e os links de Instagram/TikTok.

Um detalhe de qualidade: os vídeos baixavam em resolução baixa até instalarmos o
**Deno** (o yt-dlp precisa dele pros desafios de JavaScript do YouTube). E ficou a
lição de que o vídeo-base devia ser **definido automaticamente** pela busca, não
colado à mão.

O nome do canal foi batizado: **Thunder Games**.

---

## Capítulo 4 — Escrever tudo em guias

Antes de automatizar mais, veio um pedido sábio: **tirar todo o conhecimento da
cabeça e botar em arquivos** — como criar o roteiro, como editar, tudo. Nasceram os
`Guias/`, pra que qualquer agente (ou pessoa) pudesse seguir o padrão sem depender
da memória da conversa.

---

## Capítulo 5 — A automação via Telegram

Aqui o projeto deu seu maior salto de ambição: um fluxo quase autônomo, comandado
pelo **Telegram**. A visão: a cada período, o sistema sugere jogos; você escolhe um
(ou manda outro); ele escreve o roteiro, gera a voz, capta os **4 melhores**
trailers, edita as **4 versões** e te manda; você escolhe a melhor e posta.

Montou-se o **bot** (`bot.py`), o helper de Telegram (`notify.py`), e as duas
funcionalidades pedidas: escolher da lista **ou** mandar outro jogo, e um comando de
**simulação** pra iniciar o fluxo na hora.

O primeiro teste real foi um festival de bugs instrutivos: a palavra "oi" foi
tratada como nome de jogo (criou lixo e baixou trailers de Netflix); a captação
quebrou num vídeo indisponível; e apareceu o `WinError 10054` por rodar **duas
instâncias** do bot. As correções ensinaram regras que valem até hoje: exigir
`/jogo` pra jogo fora da lista, pular downloads que falham, e **uma instância só**.

---

## Capítulo 6 — "É pago": o pivot pro Claude local

Chegou a hora de fazer o `/simular` gerar ideias **novas de verdade** a cada uso. A
primeira ideia foi chamar a **API da Anthropic** — mas veio a objeção certeira:
**é pago**. O *pivot* foi elegante: usar o **Claude Code local** (a assinatura que
já existe), em modo headless (`claude -p`), sem custo por chamada. Nasceu o
`brain.py`.

Esse caminho teve um bug memorável: o prompt chegava **cortado** ("terminou em de")
— porque, no Windows, passar um texto grande com quebras de linha como *argumento*
de linha de comando trunca no primeiro `\n`. A solução foi mandar o prompt pela
**entrada padrão (stdin)**. Detalhe pequeno, lição grande.

---

## Capítulo 7 — Expressões que casam com o roteiro

Um refinamento importante de qualidade: as expressões do apresentador eram
**aleatórias** e repetiam a mesma ordem. A sacada foi que **os nomes dos arquivos
já descrevem a emoção** ("boquiaberto", "muito impressionado"...). Então o próprio
Claude, ao escrever o roteiro, passou a **escolher a ordem das expressões casando
com o texto**. As posições continuam variando automaticamente, mas *quais* e *em
que ordem* passou a acompanhar a narração.

---

## Capítulo 8 — A maratona de bugs de robustez

Uma sequência de problemas reais, cada um deixando o sistema mais robusto:
- **Motor de voz inválido** (`qwen3_tts`) → usar o motor padrão do perfil.
- **Bot caindo em reset de conexão** (10054) → *retry* no envio de mensagem/vídeo.
- **VoiceBox fechado** → o bot detecta e **espera** você abrir, em vez de quebrar.
- **Busca trazendo trailer de filme** ("The Northman", "Devil's Mouth") → filtro
  anti-cinema no ranqueamento.
- **`KeyError 'image'`** → as expressões escolhidas pelo Claude vinham como `{name}`,
  e a checagem antiga exigia `image`.
- **Encoding no Windows** (a saga): threads do subprocesso quebrando ao decodificar a
  saída do ffmpeg/yt-dlp como utf-8, e depois o inverso (não conseguir *imprimir* o
  `→`). Solução dupla: `errors="replace"` em toda captura de saída **e**
  `sys.stdout.reconfigure(utf-8)` em todos os scripts.
- **yt-dlp e acentos** → o ffmpeg interno do yt-dlp quebrava com o caminho "Área de
  Trabalho"; a solução foi baixar numa **pasta temporária sem acento** e mover.
- **403/throttling** do YouTube → *retries* no yt-dlp.

Também aqui o fluxo foi **quebrado em etapas** (`/captar`, `/narrar`, `/editar`) pra
testar sem refazer tudo, e ganhou um **checkpoint**: depois de baixar, o bot mostra
os **links** dos vídeos-base, pergunta se pode seguir e aceita **links extras** pra
entrar na edição.

---

## Capítulo 9 — Pensando grande (e com os pés no chão)

Houve momentos de estratégia, não só de código. Sobre **escalar**, a conclusão foi
que o ativo real é a *fábrica* (o pipeline), não os vídeos; que consistência é
necessária mas não suficiente; e que o maior salto é **fechar o ciclo** com
feedback de métricas. Sobre ideias como "revender o VoiceBox" ou "rodar vários
canais", a análise foi franca: não revender (risco de licença, sem fosso) e
**desacoplar** o motor pra, no futuro, um canal virar só uma *config* — resolvendo a
organização e a expansão de uma vez.

---

## Capítulo 10 — Aprendendo com quem funciona

Um pedido inteligente: **analisar os criadores que dão certo**. Foi criado o
`analisar_referencias.py`, que transcreve uma pasta de vídeos com **timing** (velocidade
de fala, pausas, duração de cada frase). Rodou em **20 vídeos** de um criador de
referência (fernandosev7n), e a partir dos dados + do detalhamento manual da edição
de dois deles, nasceu um **modelo descritivo** (`Guias/08`): fala rápida (~3.8
palavras/s) e sem pausas, gancho com superlativo nos 3 primeiros segundos, e edição
em **camadas sincronizadas à fala** — gameplay ao fundo, mão apontando, pop de
palavra-chave, facecam no rodapé, áudio do jogo nos momentos de humor. Esse é o
norte de qualidade que o projeto ainda vai perseguir.

---

## Capítulo 11 — A grande refatoração

Com o sistema funcionando mas crescido "orgânico", veio a decisão de **arrumar a
casa**. O diagnóstico: o motor (`src/`) estava bom, mas a automação era uma pilha de
scripts soltos, com o `pipeline.py` virando um "módulo-deus" (556 linhas) e os
segredos/caminhos espalhados.

A refatoração foi feita **em fases, cada uma preservando o comportamento e virando um
commit** — a regra de ouro pra não quebrar o que funcionava:
- **Fase 1** — `config/` central (`settings` + `secrets`): um lugar só pra caminhos,
  porta do VoiceBox, id da voz e leitura dos segredos.
- **Fase 2** — `services/`: extrair os adaptadores externos (voicebox, telegram,
  claude) — o cliente do VoiceBox saiu de dentro do `pipeline`.
- **Fase 3** — completar os `services` (youtube de busca + download via yt-dlp),
  deixando o `capture.py` fino.
- **Fase 4a** — o **upload** virou `services/youtube_upload`; o `pipeline` passou a
  publicar em processo, e o `publish/` ficou como CLI fino.
- **Fase 4b** — quebrar o `pipeline.py` em `channel/` (`common`, `roteiro`,
  `pipeline`); o `pipeline.py` da raiz virou um **atalho** de 14 linhas, então o bot
  nem precisou mudar. Foi de 454 linhas pra 14.

Cada fase foi validada por *import test* e a estrutura em camadas ficou limpa.

Antes disso, houve a limpeza das pastas (auditoria do que era lixo/regenerável) e a
entrada no **Git** — com `.gitignore` (protegendo segredos, dados e mídia) e
`.gitattributes` (fins de linha). Também foram feitos diagramas pra visualizar as
tecnologias e as camadas (o primeiro saiu com cores invisíveis e teve que ser
repintado — pequeno perrengue de contraste).

---

## Capítulo 12 — Publicação, prompts e deploy

Depois da refatoração, os últimos incrementos:
- Um **bug de música** ("chill" sem pasta) revelou um descompasso antigo entre os
  climas que o Claude oferecia e as pastas reais. A correção deixou o `resolve_music`
  **tolerante** (aliases + fallback) e alinhou o vocabulário.
- O módulo **`channel/publicacao.py`** + o comando **`/kit`**: ao terminar a edição,
  o bot gera e manda o kit das 3 plataformas (YT/TikTok/Insta), e o `/kit <slug>`
  pega isso a qualquer hora.
- Um susto: `/kit` parecia "mandar vídeos". A investigação revelou o culpado — ao
  **reiniciar**, o bot reprocessava a **fila antiga** do Telegram (um `/editar`
  velho). A correção foi **descartar a fila no boot**. Um bug sutil que explicava
  vários "comandos fantasmas" do passado.
- **Externalizar os prompts**: as regras que comandam o Claude (roteiro e
  publicação) saíram do código pra `prompts/*.md`, lidos em runtime — agora se
  ajusta o "molde" sem tocar em `.py`.

Por fim, o tema do **deploy**: como o VoiceBox depende de GPU, o plano é **Mac =
desenvolver, Windows = rodar**. A solução mais simples: **Git** como mecanismo de
deploy (o `.gitignore` garante que segredos/dados não são tocados no pull), com um
comando **`/atualizar`** no Telegram que faz `git pull` + auto-restart. Push no Mac,
`/atualizar` no Telegram, pronto.

---

## Onde paramos

A base técnica está sólida e organizada (config + services + channel + editor), com
os prompts externalizados e o deploy pelo Telegram. As frentes abertas, por ordem de
impacto:
1. Os **elementos de edição** do estilo fernandosev7n (corte por frase, mão, pop de
   palavra) — o maior ganho de qualidade.
2. A **fila com worker + `/status`** — pra ter visibilidade do que o bot está fazendo
   (hoje ele é single-thread e some da vista durante uma edição).
3. O **manifesto de proveniência** + **feedback de métricas** — pra fechar o ciclo e,
   depois, um **pool selecionável de prompts** versionados.
4. A **curadoria agendada** e o **auto-post**.

O fio condutor de tudo: transformar uma ideia de canal numa **fábrica organizada,
barata e rastreável** — e, a partir daqui, fazê-la **aprender**.
