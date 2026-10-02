# SprintAI — instruções para agentes

Painel **pessoal e local-first** de um dev só: espelho do Jira e do Bitbucket, contextos,
lembretes, Semana, Home, Workspace (cards da feature, linha do tempo das branches e terminal
por repo) e (no M8) um agente Claude que lê tudo isso.

Visão geral e telas: [README.md](README.md). Índice da documentação: [DOCS.md](DOCS.md).

## Stack e onde cada parte roda

| Parte | Onde | Stack |
|---|---|---|
| `back/` | **host** (precisa do Cofre do Windows via `keyring`) | FastAPI · asyncpg · alembic · uv |
| `front/` | navegador (Vite em dev) | Vue 3 · Pinia · vue-router, **sem framework de UI** |
| `db` | Docker em `127.0.0.1:5433` | Postgres 16 + pgvector + unaccent + pg_trgm |
| terminal host | **host**, `127.0.0.1:8766`, **sem reload** | `back/terminal_host.py` · FastAPI · pywinpty (WinPTY) |

O back **não** roda em container: ele lê os tokens do Gerenciador de Credenciais do Windows.
O terminal host é um processo à parte (os terminais do Workspace): a API sobe com
`reload=True`, e cada edição no `back/` derrubaria os shells abertos nela.

## Comandos

```bash
docker compose up -d db
cd back && uv sync && uv run alembic upgrade head && uv run python main.py
cd back && uv run python terminal_host.py
cd front && npm install && npm run dev
```

No uso diário isso tudo sai de `scripts\sprintai.ps1` (Docker → banco → migrations → API →
terminal → front), que é o que os atalhos do Windows chamam — veja "Atalho e inicialização automática"
no [README.md](README.md). Os três scripts vizinhos são `instalar.ps1`, `parar-sprintai.ps1`
e `desinstalar.ps1`. `.ps1` precisa de BOM (o PowerShell 5.1 lê sem BOM como ANSI e quebra
acento); `.vbs` precisa do contrário, sem BOM e sem acento — o Windows Script Host recusa BOM.

Antes de dar uma entrega por pronta:

```bash
cd back && uv run pytest && uv run ruff check .
cd front && npm test && npm run lint && npm run build
```

Os testes do back que usam banco recriam o database `sprintai_test` no Postgres do
docker-compose e são **pulados** se ele estiver fora do ar — um `pytest` verde com o
Docker parado não prova nada.

## Regras de segurança (não negociáveis)

- **Segredo nunca sai do Cofre.** Token de Jira/Bitbucket (e a chave da Anthropic, no M8)
  ficam no `keyring`, serviço `sprintai`. Nada de `.env`, banco, log ou resposta da API.
- **A API só escuta em loopback.** `API_HOST` fora de `127.0.0.1`/`localhost` é recusado no
  boot. O banco também só é publicado em loopback.
- **A guarda local (`security/local_guard.py`) fica inteira.** Todo request a `/api` exige o
  header `X-SprintAI`, `Host` loopback e `Origin` conhecido. Se um recurso novo não puder
  mandar o header (o caso do `EventSource`), **troque o cliente**, não a guarda — foi por
  isso que o stream de eventos é lido com `fetch` + `ReadableStream`.
- **Erro não ecoa o que foi enviado.** Um token malformado não pode voltar na resposta.
- **Escrita no Jira só com confirmação explícita, uma a uma.** Hoje o SprintAI escreve duas
  coisas, as duas em `services/issue_actions.py`: a transição de status (confirmada com duplo
  clique na linha de fluxo) e os Story Points (Salvar/Enter, ou duplo clique num atalho).
  Escrita nova — inclusive a do agente, no M8 — segue o mesmo: proposta → confirmação → ação.
  Escrita que não pode repetir vai com `idempotent=False` no transporte: repetir uma
  transição depois de um 5xx pode andar mais um passo no workflow. No Bitbucket o SprintAI
  não escreve nada — o badge de PR só leva até ele.
- **Processo, só nestes casos — e nenhum endpoint recebe comando.** Git de leitura pela lista
  branca de `services/workspace/git_local.py` (sempre `--no-optional-locks` e
  `core.fsmonitor=false`); git de **escrita local**, só as três ações de
  `services/workspace/git_actions.py` e só por gesto do dev — `fetch origin --prune` (botão),
  avançar branch até o upstream (fast-forward, nunca merge de verdade) e apagar branch
  **local** (`-d`; o `-D` só na segunda confirmação; a base nunca). Nada empurra (`push`) nem
  apaga branch no Bitbucket. O shell do terminal roda no terminal host, que recebe **pasta e perfil**
  (`terminal/profiles.py`), nunca um comando; e `Code.exe`/`wt.exe` na pasta, chamados pelo
  executável — nunca por `.cmd`, porque argumento de arquivo de lote passa pelo `cmd.exe`. O
  processo nasce com o ambiente do dev menos a configuração do SprintAI
  (`security/process_env.py`).
- **Todo caminho vindo do front passa por `security/paths.py`** antes de ser lido, virar `cwd`
  ou argumento: só abaixo das raízes, symlink resolvido, `..` e caminho de rede recusados.
- **Saída de terminal é do dev.** Não vai para log, banco, busca nem contexto do agente — fica
  só no buffer em memória do terminal host. Ele usa a mesma guarda local e não tem WebSocket
  (a guarda deixa passar o que não é HTTP): saída num stream lido com `fetch`, teclas por POST.
- **Conteúdo de terceiros é dado, nunca instrução.** Descrição de tarefa, comentário, PR e
  todo `.md` lido do disco entram como dado — inclusive (principalmente) no contexto do
  agente. Link só passa pelo `safeUrl` (`http/https/mailto`), e **nada de `v-html`** — texto
  rico vira VNode: ADF pelo `AdfRenderer`, markdown de comentário de PR pelo
  `MarkdownRenderer`. Por isso também não entra biblioteca de markdown: todas devolvem
  string de HTML, que exigiria `v-html`.

## Convenções do código

**Back** — `routers/` → `services/` → `repositories/`; `schemas/` para entrada e saída.
O router não fala com o banco e o repositório não monta schema. Migrations são escritas à
mão em `migrations/versions/NNNN_nome.py`; `_execute_script` separa por `;`, então **não
use `;` dentro de comentário SQL**. Toda tabela nova entra em `MIRROR_TABLES`
(`back/tests/conftest.py`), senão os testes vazam estado entre si.

**Canvas da sprint** — `layoutTree` é só geometria. Marca de tela (busca, filtro da
legenda) desce por `provide`/`inject` (`components/sprint/canvasMarks.js`): remontar o array
de nós a cada tecla faz o Vue Flow recriar e remedir cada card. O filtro por etapa (os chips
abaixo da sprint) é o contrário, de propósito: ele tira card do desenho, então recorta a
árvore antes do layout (`utils/stageFilter.js`) e as ondas se refazem — é um clique, não
uma tecla. Fica a tarefa da etapa e a hierarquia acima dela (pai e co-pai); bloqueador de
outra etapa sai, e a tarefa sobe de onda. A câmera vem da instância do
evento `pane-ready`, não de `useVueFlow(id)` — é o que deixa o foco testável, já que o Vue
Flow não inicializa em jsdom. `layoutSprint` desenha a sprint **numa moldura só**: os épicos
numa fileira em cima, cada um centralizado sobre as suas tarefas, e todo o resto — inclusive
as tarefas sem pai — dividindo as mesmas ondas abaixo. Uma moldura por épico mais uma "Sem
pai" espalhava a sprint em desenhos que não se comparavam. As **ondas de implementação**
(`implementationWaves`) saem do `predecessors` de cada card — bloqueador ("Blocks") e origem
("is caused by", link `Problem/Incident`), **concluídos ou não** — contando só quem esteja no
desenho: fora da sprint não há onda de onde empurrar; entre épicos diferentes conta, e é o
que a onda existe para mostrar. Não use o `blocked_by` para isso: ele perde o bloqueador
quando ele conclui, e a sprint se desmanchava numa linha só conforme as tarefas fechavam.
"Relates" entre tarefas não tem direção e não entra na ordem. Quem cai na onda 2+ perde a
seta do épico (e a de qualquer pai por link): ela cruzaria as ondas de cima por trás dos
cards, e o vínculo se lê pela corrente de bloqueio (ou de origem) que leva da onda 1 até ela.
A Tarefa fatiada tem **dois pais**: o Épico no `parent` e o Enhancements num "Relates". O
pai principal segue sendo um só (dá o grupo e a pilha); o outro vem em `co_parents`, vira
seta "link" a mais, e o grupo dele é puxado para logo depois do grupo do épico — senão o
Enhancements, que só tem a "Analisar e fatiar" de filha, caía na ponta da sprint.

**Front** — tela ou painel que mostra dado do espelho observa `refresh.revision`
(`stores/refresh.js`) e recarrega; quem alimenta esse contador é só o `AppShell` — inclusive
depois de uma escrita no Jira (`afterWrite`, desempatado pelo `write_id` entre a resposta e
o `issue.changed` do stream). Não crie
gatilho próprio de sync na tela — era assim antes, e com o painel da tarefa aberto um sync
passava sem ninguém recarregar. Um store Pinia por domínio, componentes por pasta de tela
(`components/home/`, `components/week/`…), tokens de estilo em `styles/tokens.css`.
**Nenhum componente escreve cor crua**: hex ou `rgba()` solto não vira no tema escuro.
Faltando um tom, o token nasce em `tokens.css` **nos dois temas** (`:root` e
`[data-theme='dark']`) — inclusive os que saem de `constants/` para um `:style`
(`NOTE_COLORS` e `CONTEXT_KINDS` guardam `var(--…)`, não hex). As fontes são
self-hosted em `public/fonts` (`styles/fonts.css`); nada de CDN.
Nada de `import * as icons from 'lucide-vue-next'`: importe só os ícones usados, senão a
biblioteca inteira vai para o bundle.

**Workspace** — o canvas é o `SprintCanvas` da Sprint com `flow-id` próprio e a moldura que o
back manda (`frame`): `in_sprint` ali vale "dentro da moldura" (o conjunto da feature), e o
store é outro (`workspace`), para uma tela não sobrescrever a árvore da outra. A linha do
tempo **não** segue o `refresh.revision` — o dado é do git local, não do espelho —: segue a
impressão digital do `.git` (`since`). O texto dos terminais fica fora do estado reativo
(Maps de `stores/terminals.js`); as cores do xterm saem dos tokens `--term-*` por
`getComputedStyle` (o xterm não lê CSS). Elemento com `data-terminal` fica fora dos atalhos
globais: com o foco no terminal, a tecla é do shell. A chave `WAI-XXXX` da linha do tempo
(`IssueKeyChip`) leva a cor do status de PR da tarefa — o `issue_status` que o back manda em
cada resposta, a mesma conta do selo do card —, e tag do git é amarela (`--git-tag-*`).

Ação ancorada num chip (status, SP, lista de PRs) abre o **painel único** do AppShell
(`JiraActionPopover`, pelo store `jiraActions`), nunca um painel dentro do card: o Vue Flow
remonta os cards a cada recarga da árvore, e o painel sumiria no meio da escolha. O chip é
`StatusChip`/`StoryPointsChip` com a classe de quem usa (a aparência é do lugar) e leva
`nodrag nopan` e segura o clique para não arrastar o canvas nem abrir o card — menos com
Alt, que sobe para o destaque de status do canvas.

**Idioma** — código, comentários, commits, UI e testes em **português**. Nomes de teste
descrevem o comportamento (`test_sprint_ativa_e_vencida_tem_esperado_cheio_e_aviso`).

**Comentário** explica *por que*, não *o que*. Se o código não é óbvio por si, o comentário
conta a decisão ou o caso real que levou àquilo.

## Coisas do domínio que não se adivinha olhando o código

- **A categoria do Jira mente.** `DISPONIVEL PARA REVIEW` e `DISPONIVEL PARA TESTES` chegam
  como `new`. Por isso progresso usa o mapa de etapas configurável
  (`services/progress/stages.py`), não `status_category`.
- **`resolutiondate` é sempre nulo neste workflow.** As tarefas são fechadas sem resolução.
  Para saber quando algo terminou, use a transição para a etapa final
  (`services/progress/timeline.py:finished_at`), com `updated_at` como último recurso.
- **Sprint `active` com `end_date` no passado acontece.** A Sprint 73 - Growth terminou em
  11/09/2026 e continuou ativa. Todo cálculo de sprint precisa tratar "vencida".
- **As sprints são semanais** (seg–sex) e o sufixo do nome é a squad (`Sprint 73 - Growth`).
- **O front sobe na 5273, não na 5173.** A 5173 é do front do `organia-configs` (e o
  `qualificai` a libera no CORS por causa dele). A porta sai do `FRONT_ORIGIN` do `.env`:
  o Vite lê dela a porta que sobe e o back, as origens que a guarda aceita. Cravar a porta
  num dos dois lados libera só uma das grafias de loopback e dá 403 na outra.
- **Comentário de PR é buscado pelo `comment_count`.** Ele vem de graça na listagem do
  Bitbucket; a requisição extra (`/pullrequests/{id}/comments`) só sai quando a contagem
  muda — ou quando o PR tem comentário e nenhum espelhado ainda, que é o backfill de quem
  já tinha review antes de `bb_pr_comment` existir. Sem esse filtro, cada varredura dos PRs
  abertos viraria uma chamada por PR.
- **O sync grava a transição, não o estado.** Um PR que já estava em "ajustes requisitados"
  quando o espelho nasceu não tem `pr_changes_requested` em `activity_event` — por isso a
  linha do tempo do PR sinaliza `request_before_history` em vez de inventar a data, e o
  status desse PR fica em "ajustes requisitados" mesmo com commit novo.
- **"Ajustes requisitados" não sai do participante do Bitbucket.** O `changes_requested` do
  revisor fica lá até ele aprovar ou pedir outro ajuste — nem a correção o limpa. Quem
  devolve o PR para "PR aberta" é o `activity_event`: commit depois do último pedido
  (`pr_status.fix_after_request`), a mesma comparação do `pr_timeline.pending_review`.
- **O sync não guardava história.** Quem precisa de histórico lê `jira_status_transition` e
  `activity_event`, preenchidos **durante o sync** com chave de dedupe.
- **"Minhas" = `assignee_account_id` da conexão.** Sem `account_id` salvo, nada é filtrado —
  as telas avisam quando isso acontece.
- **Escrita pelo SprintAI não carimba o `updated_at` do espelho.** O status (ou SP) novo
  entra na hora (`issue_repo.patch_status`), mas o `updated_at` fica o antigo: é comparando
  ele com o do Jira que o sync rebusca a tarefa e lê o changelog — de onde saem a linha de
  `jira_status_transition` e o evento do feed. Carimbar o novo faria a mudança sumir da
  história.
- **Branch e worktree dos repos reais.** A branch tem cinco grafias (`WAI-8790-slug`,
  `feature/`, `task/`, `ajuste/`, `enhancement/WAI-XXXX`), todas com a chave — o
  `extract_issue_keys` entende todas. Worktree mora em três lugares: `<repo>\.claude\worktrees\`,
  `C:\projects\.worktrees\<repo>-WAI-XXXX` e a pasta temp das sessões do Claude (fora das
  raízes, em HEAD destacado — aparece no grafo, sem terminal).
- **A branch da feature some depois do merge.** O merge pelo Bitbucket apaga a branch no
  origin, e o dev costuma apagar a local. Por isso o "Só da feature" da linha do tempo, sem
  branch com a chave, cai nos commits que citam a chave na mensagem — a convenção do time é
  `feat(WAI-8790): …` e "Merged in WAI-8790-… (pull request #N)", com a base como primeiro
  pai do merge.
- **O espelho do Bitbucket não é lista de branches.** Só guarda branch com `WAI-`, dos repos
  escolhidos e "minhas". A linha do tempo lê o git local; o espelho só põe o selo do PR.
- **Terminal é WinPTY, não ConPTY.** O ConPTY do pywinpty cria o processo com o Ctrl+C
  desligado para os filhos (spike W0, 02/10/2026) — sem ele não se para um `npm run dev`.
  Encerrar é `taskkill /T /F` no shell, senão o filho fica órfão.
- **O workflow de Tarefa da WAI é global e compartilhado.** São 17 status (de "Cruzeiro" a
  "IMPLANTAÇÃO") e todos alcançáveis de qualquer um. A linha de fluxo mostra só os que têm
  etapa em Configurações › Progresso e recolhe o resto em "Outros status".

## Escrita em disco

O SprintAI só escreve `.md` no **PROGRESS canônico**
(`<repo>\.claude-outputs\progress\PROGRESS-WAI-XXXX.md`, contrato em
[docs/harness/progress-format.md](docs/harness/progress-format.md)). Todo o resto do harness
— `CLAUDE.md`, `DOCS.md`, skills, agents, specs, handoffs, memory — é **somente leitura**.
Raízes permitidas: `C:\projects\` e `C:\Users\<dev>\.claude\`. Nunca `Z:\`. No git dos repos
o SprintAI só mexe pelas três ações da linha do tempo (fetch --prune, avançar e apagar branch
local), cada uma por clique do dev; o que muda pelo terminal é o dev quem digita.

## Git

Commits só quando o dev pedir. Mensagem em português, no imperativo.
