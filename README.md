# SprintAI

Painel **pessoal e local-first** do dev: uma Home que mostra o dia (progresso das sprints, pendências, feed de atividade e timeline), a sprint do Jira em árvore Pai → Filhas com o status dos PRs do Bitbucket, contextos persistidos por tarefa, lembretes/post-its pesquisáveis de qualquer tela e, por último, uma IA que relaciona tudo isso.

Como mexer no código: [CLAUDE.md](CLAUDE.md). Índice da documentação: [DOCS.md](DOCS.md).
Plano completo e ordem das entregas: `C:\Users\Matheus Bacca\.claude\plans\gostaria-de-planejar-um-snuggly-bubble.md`.

## Arquitetura

| Parte | Onde roda | Stack |
|---|---|---|
| `back/` | **Host** (precisa do Cofre do Windows via `keyring`) | FastAPI · asyncpg · alembic · uv |
| `front/` | Navegador (Vite em dev) | Vue 3 · Pinia · vue-router |
| `db` | Docker (`127.0.0.1:5433`) | Postgres 16 + pgvector + unaccent + pg_trgm |

Segurança local:
- a API só escuta em loopback (`API_HOST` diferente de `127.0.0.1`/`localhost` é recusado);
- o banco só é publicado em loopback;
- **tokens do Jira e Bitbucket nunca vão para `.env`, banco, logs ou para o front** — ficam no Cofre do Windows (serviço `sprintai` no Gerenciador de Credenciais), cadastrados em Configurações › Conexões e só salvos depois de testados;
- a API recusa (403) requests sem o header `X-SprintAI`, com `Host` fora de loopback (DNS rebinding) ou com `Origin` que não seja o front;
- erros de validação não ecoam o valor enviado (um token malformado não volta na resposta).

## Setup

Pré-requisitos: Python 3.11, Node 20+, Docker Desktop, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up -d db
```

Back:

```bash
cd back
uv sync
uv run alembic upgrade head
uv run python main.py
```

Front (outro terminal):

```bash
cd front
npm install
npm run dev
```

Abra http://127.0.0.1:5273. O indicador no topo mostra se API e banco estão conectados.

### Atalho e inicialização automática

Para o uso diário não é preciso abrir dois terminais. O `scripts/` tem o launcher:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
```

Isso não instala nada no sistema — só gera o ícone e cria três atalhos apontando para
este repositório:

| Atalho | O que faz |
|---|---|
| Área de Trabalho e Menu Iniciar → **SprintAI** | sobe tudo e abre a tela no navegador |
| Menu Iniciar → **Parar SprintAI** | derruba API e front (o banco fica de pé) |
| Inicialização do Windows | sobe tudo no logon com `-NoBrowser`, sem roubar o foco |

O `scripts/sprintai.ps1` é o que todos chamam, e é idempotente: abre o Docker Desktop se
estiver fechado e espera o engine, sobe o container do banco e espera o healthcheck,
aplica as migrations, e só sobe API e front se a porta de cada um estiver livre. Rodar
duas vezes não duplica nada — dá para clicar no atalho da Área de Trabalho a qualquer
hora só para abrir a tela. Na primeira execução ele também cria o `.env` a partir do
`.env.example` e roda `uv sync` / `npm install` se faltarem.

API e front sobem como processos ocultos e escrevem em `.logs/` (`back.log`, `front.log`,
`launcher.log` e os `.err.log` de cada um) — é lá que se olha quando algo não sobe.

`desinstalar.ps1` remove os atalhos. Para parar pela linha de comando:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\parar-sprintai.ps1 -PararBanco
```

Duas coisas que o launcher resolve e não são óbvias: o Docker Desktop é aberto **pelo
`explorer.exe`**, porque como filho do PowerShell ele herda o ambiente de quem chamou e
morre em `initializing Inference manager`; e o atalho passa pelo `sprintai-oculto.vbs`
em vez de chamar o `powershell.exe` direto, senão um console preto pisca no logon.

### Portas

| Porta | Quem | Onde muda |
|---|---|---|
| 5273 | front (Vite) | `FRONT_ORIGIN` no `.env` da raiz — o Vite lê a porta dela |
| 8765 | API local | `API_PORT` |
| 5433 | Postgres (Docker) | `DB_PORT` |

O front **não** usa a 5173, padrão do Vite: ela é do front do `organia-configs` (e o
`qualificai` libera `http://localhost:5173` no CORS por causa dele). Sair da faixa
5173-5180 também evita que dois Vites disputem a mesma porta.

`FRONT_ORIGIN` é a única fonte da verdade da porta do front: o Vite tira dela a porta que
sobe e o back tira dela as origens que a guarda local aceita (`localhost` **e** `127.0.0.1`).
O `strictPort` fica ligado de propósito — se a porta estiver ocupada, é melhor o Vite falhar
do que subir na porta seguinte e tomar 403 da guarda no primeiro request.

## Endpoints de descoberta (só leitura)

| Rota | O que devolve |
|---|---|
| `GET /api/jira/fields` | IDs dos campos Sprint e Story Points desta instância |
| `GET /api/jira/boards?project_key=WAI` | boards (scrum/kanban) do projeto |
| `GET /api/jira/boards/{id}/sprints?state=active,future` | sprints do board, com a squad pelo sufixo do nome (`Sprint 73 - Growth`) |
| `GET /api/bitbucket/repositories?limit=50` | repositórios do workspace, mais recentes primeiro |

## Sincronização (espelho local)

A API sincroniza sozinha a cada `interval_minutes` (padrão 5) e sob demanda pelo indicador no topo.
O escopo é configurado em **Configurações › Sincronização**:

- **Jira:** board (padrão Engenharia/144), squads pelo sufixo da sprint (`Sprint 73 - Growth`), baldes sem squad, quantas sprints fechadas espelhar (congeladas depois da primeira carga) e as minhas tarefas fora das sprints.
- **Dono (padrão "só o que é meu"):** no Jira, tarefas em que você é o Responsável + os épicos/enhancements pais delas; no Bitbucket, PRs em que você é autor ou revisor, ou ligados a tarefas suas. Dá para ampliar para "sprint inteira" / "todos os PRs" — ampliar recarrega o que foi pulado; restringir poda o espelho.
- **Bitbucket:** só os repositórios **escolhidos pelo dev**, agrupados por projeto. PRs incrementais a cada ciclo, varredura dos PRs abertos a cada 30 min (aprovações), build só quando o commit muda, branches só quando há push.

| Rota | O que faz |
|---|---|
| `GET/PUT /api/sync/scope` | lê/grava o escopo |
| `GET /api/sync/status` | execução atual, última execução, contagens do espelho |
| `GET /api/sync/sprints` | sprints no escopo com nº de tarefas |
| `POST /api/sync` | dispara agora (409 se já estiver rodando) |

## Home (`/`)

O painel do dia a dia. Atualiza sozinha pelo stream de eventos local — um lembrete criado
noutra aba ou um sync que termina aparecem sem recarregar (o indicador "ao vivo" no topo
mostra se o stream está de pé). O stream vale para todas as telas: ver
[Recarregar](#recarregar-sync-e-botão-valem-para-tudo-que-está-aberto).

- **Progresso da sprint:** uma barra por sprint que ainda tem **tarefa sua em aberto**, com o
  **real** (média dos pesos das etapas, ponderada por Story Points; tarefa sem SP conta 1)
  contra o **esperado** (fração de dias úteis já decorrida). Sprint `active` cujo fim já passou
  é marcada como **vencida**, tem esperado 100% e **continua aparecendo** enquanto sobrar
  trabalho seu; sprint ativa sem nada seu por fazer sai da Home. O nome da sprint leva para a
  árvore dela em `/sprints`.
- **Mexeram nestas:** logo abaixo de cada sprint, uma linha rolável com as suas tarefas
  daquela sprint em que **outra pessoa** mexeu nas últimas 48h — com quem mexeu, o que fez e
  quantas mexidas houve. Clicar abre o painel da tarefa na aba do evento. As das sprints
  ativas também chegam pelo [sino do topo](#notificações-o-sino-no-topo), de qualquer tela.
- **Pendências da semana:** o topo de cada bloco da Semana (atrasadas, prazo, "Analisar e
  fatiar", sem sprint), com link para a tela inteira.
- **Lembretes relevantes:** vencidos não vistos, das próximas 48h, fixados e os ligados a uma
  tarefa da sprint ativa.
- **Atividade:** o que mudou nas suas tarefas e nos seus PRs, do mais novo para o mais antigo,
  agrupado por dia, com filtros Jira/Bitbucket/"só de outros" e paginação por cursor. Clicar
  abre o painel da tarefa na aba certa (comentário → Histórico, PR → PRs).
- **Timeline:** no formato da do Jira (Plans) — faixa de meses e dias, linha das sprints com a
  atual destacada, marcador de hoje, grupos recolhíveis por pai e uma barra por tarefa,
  **segmentada pelos status por que ela passou**. Rolagem horizontal própria; CSS grid e SVG,
  sem biblioteca.
- **Checklist de configuração:** só aparece enquanto estiver incompleto.

Regras que valem a pena saber:

- A **etapa** de cada status é configurável em **Configurações › Progresso** (padrão: análise
  0 · desenvolvimento 0.4 · review 0.7 · testes 0.85 · concluído 1). A categoria do Jira só é
  usada para status que ninguém mapeou — ela mente para `DISPONIVEL PARA REVIEW` e
  `DISPONIVEL PARA TESTES`, que chegam como `new`.
- A barra de uma tarefa começa na **primeira transição para fora da análise** e termina
  quando ela chegou à etapa final. Como este workflow fecha as tarefas **sem resolução**
  (`resolutiondate` nunca vem preenchido), o fim sai da transição de status, com `updated_at`
  como último recurso. Não terminou? A barra vai até o fim da sprint ou até hoje, o que for
  mais tarde, e o trecho futuro aparece listrado.

| Rota | O que devolve |
|---|---|
| `GET /api/home?tz=` | progresso das sprints ativas, topo das pendências da semana e lembretes relevantes |
| `GET /api/home/timeline?tz=&include_next=` | faixas de sprint, linhas agrupadas por pai com barras segmentadas e setas de bloqueio |
| `GET /api/activity?cursor=&limit=&source=&only_others=` | feed de atividade, do mais novo para o mais antigo |
| `GET /api/events` | stream de eventos locais (`sync.finished`, `activity.new`, `note.changed`, `context.changed`, `progress.changed`) |
| `GET/PUT /api/progress/stages` | etapas do progresso e em qual delas cai cada status do espelho |

O `GET /api/events` é `text/event-stream`, mas **não** é consumido por `EventSource`: a API
exige o header `X-SprintAI` e o `EventSource` não manda header nenhum. O front lê com `fetch`
+ `ReadableStream`, e a guarda local fica inteira.

### Recarregar: sync e botão valem para tudo que está aberto

O stream é do **app**, não de uma tela — ele conecta no `AppShell` e continua de pé em
qualquer rota. Quando uma sincronização termina, ou quando você clica em **Recarregar**
(Home, Semana, Sprints ou o botão do painel da tarefa), um contador só (`stores/refresh.js`)
avança e **tudo que está aberto se refaz**: a tela, o painel da tarefa, a aba que estiver
nele (PRs, Histórico) e as contagens.

Três detalhes que fazem isso não incomodar:

- **Nada pisca.** O cache do painel segura o que já está na tela enquanto busca, e a aba
  aberta continua a mesma.
- **Uma execução, um recarregamento.** O fim do sync chega por dois caminhos — o stream
  avisa na hora e o polling do status é a rede de segurança quando ele cai. O `refresh`
  desempata pelo id da execução, senão a mesma sincronização recarregaria tudo duas vezes.
- **Cache com carimbo.** Cada entrada guarda em que revisão foi buscada; reabrir o painel de
  uma tarefa vista antes do sync busca de novo em vez de servir o estado velho.

### Histórico do espelho

O sync não guardava história — feed e timeline dependem dela, então ela é registrada
**durante a sincronização**:

- `jira_status_transition`: uma linha por mudança de status (chave `changelog_id` única);
- `activity_event`: um evento por acontecimento do Jira ou do Bitbucket (chave `dedupe_key`
  única), com retenção de 90 dias.

A primeira execução faz **backfill de 14 dias**, só das suas tarefas mexidas na janela. A
primeira carga de um repositório do Bitbucket não gera evento nenhum, senão o feed nasceria
com todo o histórico de PRs de uma vez. Rodar o sync de novo não duplica nada.

## Árvore da sprint (`/sprints`)

- Seletor de sprint (ativas, futuras, fechadas) com contadores: tarefas, pais, bloqueios, concluídas e SP.
- Pai de uma tarefa: campo `parent` (Épico → Tarefa → Subtarefa) ou, sem ele, link Relates / Divisão do ticket / implements para um Épico ou Enhancements (`back/services/hierarchy.py`).
- **Uma moldura só para a sprint** ("N tarefa(s) na sprint"): os épicos ficam numa fileira em
  cima, cada um centralizado sobre as suas tarefas, e **as tarefas sem pai entram na mesma
  linha das outras** em vez de numa caixa à parte. Quem diz de quem a tarefa é continua sendo
  a seta que desce do épico.
- Cards com tipo, título, chave, SP, status do Jira e badge de PR; borda vermelha quando há bloqueador não concluído; seta "bloqueia" entre tarefas.
- **Ondas de implementação**: quando há bloqueio entre as tarefas do desenho, a linha
  única vira faixas separadas por um pontilhado — "Onda de implementação 1" são as tarefas
  que ninguém bloqueia, e cada tarefa desce para a onda seguinte à do seu bloqueador mais
  tardio, na coluna dele. Dá para ler o que dá para começar hoje sem seguir seta por seta.
  Duas tarefas liberadas pela mesma ficam lado a lado na onda seguinte. Como a sprint é um
  desenho só, bloqueio entre épicos diferentes também conta. Sprint sem bloqueio nenhum
  continua em linha única, sem faixa.
- **Marcador no canto superior direito do card**, para varrer o canvas sem ler o rodapé de
  cada um: check verde em **Aprovada**, check roxo em **Mergeada** e o ícone laranja em
  **Ajustes requisitados**. Os outros status continuam só na cor da borda e no badge.
- **Busca no canvas** (canto superior direito): casa por chave ou título, sem acento nem
  caixa. Todo resultado fica marcado e a câmera pousa no da vez; `Enter` vai para o
  próximo, `Shift+Enter` volta, `Esc` limpa. O contador mostra `2/7`.
- **Legenda clicável**: cada status liga e desliga. Filtrando, os cards do status ligado
  crescem um pouco e os do desligado perdem cor; `Alt+clique` isola um status e desligar o
  último volta a mostrar todos. Pai e card fora da sprint nunca são apagados — sem eles a
  árvore perde a estrutura.
- Clique no card abre o **painel lateral da tarefa** (`?tarefa=WAI-XXXX`, Esc fecha) e
  **centraliza o card** quando ele está cortado ou atrás do painel — valendo também para a
  tarefa aberta de fora do canvas, pela busca global ou pelo sino:
  - **Detalhes:** descrição do Jira (ADF renderizado em componentes Vue, sem `v-html`; links só http/https/mailto), campos, hierarquia e "Bloqueia (n)";
  - **Dependências:** pai, filhas e links agrupados, com status de PR — clicar numa tarefa do espelho troca o painel; fora do espelho abre no Jira;
  - **PRs:** por repositório — branch, aprovações, pedidos de ajuste, revisores, build, branches sem PR;
  - **Histórico:** comentários (espelho) + mudanças de campos buscadas ao vivo no Jira (200 mais recentes).
- A barra lateral recolhe para só ícones (preferência salva no navegador).

| Rota | O que devolve |
|---|---|
| `GET /api/sprints` | sprints do escopo com contagem total, minhas e concluídas |
| `GET /api/sprints/{id}/tree?only_mine=` | nós, arestas (parent/link/blocks), grupos e contadores |
| `GET /api/issues/{key}` | detalhe da tarefa (espelho): campos, descrição ADF, dependências, comentários, PRs |
| `GET /api/issues/{key}/changelog` | histórico de mudanças, ao vivo do Jira |

## Lembretes (`/lembretes`)

- Post-its com título, texto, cor, tags, fixar, arquivar e **horário de lembrete** (atalhos "em 1 hora", "amanhã 9h", "segunda 9h").
- Vinculáveis a tarefas (`WAI-1234`): aparecem na aba **Lembretes** do painel da tarefa, que também cria já vinculado.
- Busca própria no Postgres: português **sem acento** ("integracao" acha "Integração"), **trecho parcial** ("exponen"), tag e chave de tarefa; título pesa mais que o texto; fixados primeiro.
- Na hora marcada: o lembrete vira **notificação no sino do topo** (veja abaixo) e uma notificação do Windows, se você permitir no primeiro lembrete com horário.
- **Concluir dá para fazer de três lugares**: o card no mural, o painel do sino e a própria
  modal do lembrete. Na modal o botão salva o que está na tela antes de concluir — o PATCH
  reenvia o horário e no back isso rearma a notificação, então a ordem inversa desfaria o
  concluir. Mexeu no horário, o lembrete volta a ficar em aberto (é a mesma regra do back).

| Rota | O que faz |
|---|---|
| `GET /api/notes?q=&tag=&issue_key=&pinned=&archived=&due=` | lista/busca |
| `POST /api/notes` · `PATCH/DELETE /api/notes/{id}` | cria, edita (parcial), exclui |
| `GET /api/notes/tags` | tags com contagem |
| `GET /api/notes/reminders/due` | lembretes vencidos ainda não vistos |
| `POST /api/notes/{id}/reminder/ack` · `/snooze` | concluir · adiar |

### Notificações (o sino no topo)

O sino, à direita do botão de lembretes, junta as duas coisas que chegam sem você pedir:
**lembrete vencido** e **mexida nas suas tarefas da sprint**. Lembrete vencido não abre
mais cartão flutuante em cima da tela.

- **Selo abaixo do sino** com quantas notificações ainda não foram vistas. Abrir o painel
  zera a contagem; um lembrete que vence depois (ou que volta de um "adiar") e uma mexida
  nova somam de novo. Fecha com `Esc` ou clique fora.
- **Lembretes** (os amarelos) trazem horário, tarefas ligadas e as ações
  *Abrir · Adiar 10 min · 1 h · Concluir* — as mesmas de antes. Vêm primeiro na lista: são
  cobrança, e ficariam enterrados embaixo do que acabou de acontecer.
- **Tarefas** são as mesmas mexidas da linha "Mexeram nestas" da Home — suas
  tarefas das sprints **ativas** em que **outra pessoa** mexeu nas últimas 48h, com quem
  mexeu, o que fez e quantas mexidas houve. **Abrir na sprint** leva ao canvas *daquela*
  sprint com o card em foco e o painel da tarefa aberto na aba do evento (comentário →
  Histórico, PR → PRs). Elas não tocam a notificação do Windows: a primeira leitura traz
  48h de uma vez, e isso viraria uma saraivada de avisos por algo que já passou.
- **Filtro por tipo**, logo abaixo do título: *Lembretes* e *Tarefas*, cada um com a sua
  contagem. Ligar um mostra só ele, ligar os dois mostra tudo, e desligar o último tira o
  filtro. O que o filtro esconde **continua somando no selo** — visto é o que apareceu na
  tela, e marcar tudo apagaria em silêncio a novidade que você não viu.
- **Fixar (📌)** sobe só o **título** do lembrete para o topo de todas as telas; clicar nesse
  título abre a **modal do lembrete**, e o `X` do chip desafixa. Concluir solta o pin sozinho.
  O "Abrir" do painel e o clique na notificação do Windows levam ao mesmo lugar. Notificação
  de tarefa não se fixa: ela é notícia, e o lugar de acompanhá-la é o canvas da sprint.
- O que está fixado e o que já foi visto é preferência **desta máquina** (`localStorage`), não
  campo do lembrete: o `pinned` da nota continua sendo o fixar do mural. O filtro vale só
  para a sessão — recarregar a página volta a mostrar tudo.

| Rota | O que devolve |
|---|---|
| `GET /api/notifications/updates` | tarefas suas das sprints ativas que outra pessoa mexeu nas últimas 48h |

### Modal de lembretes por atalho

Em qualquer tela (inclusive com o foco num campo de texto):

- **`Ctrl+Shift+L`** abre a busca de lembretes já preenchida com o **texto selecionado**; sem seleção, com a tarefa aberta no painel. Se nenhuma nota tem todas as palavras da seleção, mostra as que têm alguma. Teclado: ↑/↓, Enter abre, Ctrl+Enter cria, Esc fecha. Também pelo botão ao lado da busca no topo.
- **`Ctrl+Shift+A`** abre um lembrete novo com a seleção no texto e as tarefas citadas (ou a aberta) vinculadas.

Os atalhos mudam em **Configurações › Atalhos** (gravados no banco, `GET/PUT /api/preferences/shortcuts`). A tela recusa atalho repetido entre ações, `Ctrl`+tecla (edição/navegador), `Ctrl+Alt` (é o AltGr) e os que o navegador não entrega à página — por isso o padrão não é `Ctrl+Shift+N`, que no Chrome/Edge abre a janela anônima.

## Semana (`/semana`)

Segunda a domingo no fuso do navegador, com navegação entre semanas (`?dia=AAAA-MM-DD`). Duas colunas:

- **Com data:** *Prazo nesta semana* (campo "Data limite" do Jira, por dia, com as **atrasadas** em cima) e *Lembretes da semana* (por dia, com os pendentes de semanas anteriores e "Concluir").
- **Sem data:** *Analisar e fatiar* (cards em aberto + concluídos na semana) e *Minhas sem sprint* (em aberto, fora de sprint ativa/futura; o que **sobrou de sprint fechada** vem primeiro).
- "Minhas" = Responsável é você (accountId salvo na conexão). Cada tarefa mostra status, sprint, pai, pontos em aberto dos contextos e o badge de PR; clicar abre o painel.

| Rota | O que faz |
|---|---|
| `GET /api/week?day=&tz=America/Sao_Paulo` | os quatro blocos da semana que contém `day` (padrão: hoje) |

## Contextos (`/contextos`)

- Por tarefa: **Achado**, **Correção**, **Decisão**, **Ponto em aberto** e **Resumo**, com título, detalhes, tags, tarefas relacionadas e "continua a tarefa".
- Aba **Contextos** no painel da tarefa, em três blocos: os desta tarefa, os de outras tarefas que citam esta (relação ou resolvido nela) e os **pontos em aberto de tarefas próximas** (mesmo pai, pai/filhas ou vínculo no Jira), cada um com "Resolver aqui".
- **Resolver** um ponto em aberto registra em qual tarefa e como; reabrir desfaz. Ponto resolvido não muda de tipo sem reabrir.
- Tela `/contextos` agrupada por tarefa: começa em "Pontos em aberto"; filtros por tipo e resolvidos; busca sem acento e por trecho.

| Rota | O que faz |
|---|---|
| `GET /api/contexts?q=&issue_key=&kind=&status=&tag=` | lista/busca |
| `POST /api/contexts` · `PATCH/DELETE /api/contexts/{id}` | cria, edita (parcial), exclui |
| `POST /api/contexts/{id}/resolve` · `/reopen` | resolve numa tarefa · reabre |
| `GET /api/issues/{key}/contexts` | aba do painel: próprios, citados e pontos próximos |
| `GET /api/contexts/counts` | pontos em aberto e total por tipo |

## Busca global (`Ctrl+K`)

- Pelo campo do topo ou `Ctrl+K` (configurável em Configurações › Atalhos), já com o texto selecionado na tela.
- Procura em **tarefas, comentários, PRs, contextos e lembretes**, agrupados nessa ordem, com o termo destacado. Filtros por tipo (com contagem) e período.
- Sem acento, por trecho de palavra e por chave (`WAI-8295` traz a tarefa e o que cita ela, com a própria tarefa no topo).
- Abrir um resultado leva ao painel da tarefa na aba certa (comentário → Histórico, PR → PRs, contexto → Contextos); lembrete abre o editor; PR fora do espelho abre o Bitbucket.
- Índice em `search_document`, mantido **por triggers do Postgres**: o sync e qualquer escrita de contexto/lembrete atualizam na mesma transação. A busca por semelhança (embeddings locais) entra na B6 sobre a mesma tabela.

| Rota | O que faz |
|---|---|
| `GET /api/search?q=&type=&period=any\|7d\|30d\|90d\|365d&limit=&offset=` | resultados por tipo (`offset` só com um tipo) |

## Status de PR por tarefa

Regras em `back/services/pr_status.py` (funções puras, 100% de cobertura):

- **Por PR:** Mergeada · Recusada · Substituída · Rascunho (draft) · Ajustes requisitados (algum *changes requested*) · Aprovada (≥1 aprovação) · PR aberta.
- **Por repositório:** PR aberto prevalece sobre mergeado; recusado só conta se for tudo que há. Branch com a chave e sem PR no repo = Branch sem PR.
- **No card (agregado):** o que pede atenção vence — Sem PR < Branch sem PR < Ajustes requisitados < Rascunho < PR aberta < Aprovada < Mergeada. Repositório só com PR recusado e branch antiga (anterior à última atividade de PR) não puxam o card para baixo.
- **Vínculo:** chave no nome da branch (`feature/WAI-7120`) ou citada no título (PR que entrega várias tarefas); o detalhe informa qual.

### Histórico da PR

Dentro da aba **PRs** do painel da tarefa, cada PR mostra a própria linha do tempo — sempre
aberta, no formato do Bitbucket (trilho vertical com um marcador por acontecimento) e **da
última atualização para a mais antiga**, como o feed da Home e a aba Histórico. Ela junta
duas fontes:

- **comentários da review** (espelhados em `bb_pr_comment`), com o arquivo e a linha quando
  o comentário é inline;
- **os eventos do PR** que já alimentam o feed da Home (abriu, subiu commit, aprovou, pediu
  ajustes, build, mergeou).

O commit que entra **depois do último pedido de ajuste** é marcado como *"subiu a correção"*;
enquanto ele não vem, o topo da linha avisa que o ajuste está pendente. Um novo pedido de
ajuste reabre a pendência.

O comentário é **markdown renderizado** — título, ênfase, código, lista, citação e link. O
parser é próprio (`utils/markdown.js` → `MarkdownRenderer.js`) e devolve **VNodes**, nunca
HTML: o corpo vem do Bitbucket e é dado de terceiro, então não entra `v-html` nem biblioteca
de markdown (todas devolvem string de HTML). Link só passa pelo `safeUrl`; o resto do texto
aparece como texto, inclusive se vier `<script>` no meio.

O botão no canto superior direito de cada comentário **copia nos dois formatos**: o HTML
renderizado (colar no Jira ou no Slack sai formatado) e o markdown original como texto puro.
Onde a Clipboard API é negada, cai para a seleção temporária e copia só o texto.

> Pedido de ajuste anterior a este espelho não tem evento (o sync grava a *transição*, não o
> estado), então a marcação de correção vale a partir do próximo — a linha do tempo avisa
> quando esse é o caso.

| Rota | O que devolve |
|---|---|
| `GET /api/issues/{key}/pull-requests` | detalhe por repositório: PRs, aprovações, ajustes, build, branches sem PR |
| `GET /api/pull-requests/{repo}/{id}/timeline` | histórico do PR: comentários da review + eventos |
| `POST /api/pr-status` `{"keys": [...]}` | status agregado de várias tarefas (cards da árvore) |

## Tema e tipografia

O botão ao lado de **Recolher menu**, no rodapé da sidebar, alterna claro ↔ escuro. Sem
escolha salva o painel segue o `prefers-color-scheme` do Windows — e passa a acompanhar as
mudanças do sistema em tempo real; no primeiro clique a escolha vira preferência e fica no
`localStorage` (`sprintai.theme`) — **Shift+clique** apaga a escolha e volta a seguir o
Windows. Um script inline no `index.html` aplica o tema antes do Vue montar, por isso não há
flash branco ao abrir no escuro.

As três fontes são **self-hosted** em `front/public/fonts` (woff2 variáveis, ~186 KB) — o
painel é local-first e não pede fonte a CDN nenhuma: `Hanken Grotesk` na interface,
`Source Serif 4` na marca e nos títulos de tela, `JetBrains Mono` nos atalhos e trechos de
código.

## Testes e lint

Os testes do back que usam banco recriam o database `sprintai_test` no Postgres do docker-compose
(e são pulados se ele estiver fora do ar).

```bash
cd back && uv run pytest && uv run ruff check .
cd front && npm test && npm run lint
```

## Estrutura

```
back/
  main.py            app FastAPI (routers com prefixo /api)
  config.py          settings do .env da raiz
  core/              logger com máscara de segredos
  database/          pool asyncpg sob demanda
  security/          cofre de credenciais (keyring) e guarda da API local
  integrations/      clientes Jira/Bitbucket (retry, paginação, erros sem segredo)
  routers/ → services/ → repositories/ ; schemas/
  migrations/        alembic async, migrations escritas à mão
front/
  src/layouts/       AppShell (sidebar + topbar)
  src/router/        rotas + itens de navegação (com a entrega de cada tela)
  src/services/api.js cliente HTTP da API local
  src/stores/        Pinia
  src/styles/        tokens (claro e escuro), @font-face e base
  public/fonts/      as três fontes self-hosted (woff2 variáveis)
  realtime/          barramento de eventos em memória (pub/sub asyncio)
db/init/             extensões criadas no primeiro start do volume
docs/                arquitetura, contrato do PROGRESS.md e do contexto do agente
```
