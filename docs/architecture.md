# Arquitetura

## Camadas

```
front/ (Vue 3 + Pinia)
   │  fetch com header X-SprintAI
   ▼
LocalGuardMiddleware ──► routers/ ──► services/ ──► repositories/ ──► Postgres
                                          │
                                          ├─► integrations/ (Jira, Bitbucket)
                                          ├─► security/credential_store (Cofre do Windows)
                                          └─► realtime/bus ──► GET /api/events (SSE)
```

Regras da divisão:

- **`routers/`** valida entrada e traduz exceção de domínio em HTTP. Não fala com o banco.
- **`services/`** tem a regra. É onde mora tudo que vale testar sem banco — as funções puras
  de `pr_status.py`, `progress/stages.py`, `progress/timeline.py`, `activity/*_events.py`.
- **`repositories/`** só SQL. Devolve `dict`, não schema.
- **`schemas/`** é o contrato com o front (pydantic).

## Guarda local

Uma API em `127.0.0.1` é alcançável por qualquer página aberta no navegador. Três camadas
fecham isso (`security/local_guard.py`):

1. `Host` precisa ser loopback — barra DNS rebinding;
2. `Origin`, quando presente, precisa estar na lista do front; sem `Origin`, um
   `Sec-Fetch-Site: cross-site` é recusado;
3. `/api` exige o header `X-SprintAI` — header customizado força preflight de CORS, então
   um `<form>` ou `fetch` "simples" de outro site não passa.

**Consequência prática:** `EventSource` não manda header nenhum e por isso **não** é usado
para o stream de eventos. O front lê o `text/event-stream` com `fetch` + `ReadableStream`
(`front/src/stores/realtime.js`) e a guarda fica intacta.

## Uma sincronização

`services/sync/engine.py` roda **uma execução por vez** (lock), registra em `sync_run` e é
acordado por um laço asyncio dentro da própria API. Jira e Bitbucket rodam em sequência; a
falha de um não impede o outro (a execução termina como `partial`).

**Jira** (`services/sync/jira_sync.py`):

1. boards e sprints do escopo → marca `in_scope`;
2. lista só `key + updated` das sprints-alvo e das minhas tarefas;
3. busca completa só do que mudou (compara `updated` com o espelho);
4. busca os pais que faltam, para a árvore ficar inteira;
5. recalcula os membros das sprints ativas/futuras;
6. poda o que não é meu (com `assignee_scope = "mine"`);
7. **registra a atividade** (`services/activity/recorder.py`).

**Bitbucket** (`services/sync/bitbucket_sync.py`): PRs incrementais por cursor, varredura
dos abertos a cada 30 min (aprovação nem sempre mexe no `updated_on`), build só quando o
commit muda, branches só quando houve push. O **diff que vira evento acontece antes do
upsert** — depois dele a linha anterior já foi sobrescrita.

## Histórico: como o feed e a timeline existem

O espelho guarda o **estado atual**. Feed e timeline precisam de **história**, e ela é
construída durante o sync (migration `0007`):

- `jira_status_transition` — uma linha por mudança de status, chave `changelog_id` única.
  É o que segmenta as barras da timeline.
- `activity_event` — uma linha por acontecimento (Jira ou Bitbucket), chave `dedupe_key`
  única. Rodar o sync de novo sobre o mesmo changelog não duplica nada.

Primeira execução faz **backfill de 14 dias** só das minhas tarefas mexidas na janela; a
primeira carga de um repositório do Bitbucket **não** gera evento, senão o feed nasceria
com todo o histórico de PRs de uma vez. Retenção de 90 dias, aplicada a cada ciclo.

## Progresso

Dois passos, ambos em `services/progress/`:

1. **etapa** — `stages.py` mapeia status → etapa (ordem, peso, cor), salvo em
   `app_setting.progress_stages` e editável em Configurações › Progresso. A categoria do
   Jira é só o plano B, porque ela mente para `REVIEW`/`TESTES` (chegam como `new`).
2. **fonte** — `sources.py` define a interface `ProgressSource`. Hoje só existe `status`;
   `checklist` (itens do PROGRESS.md) entra na F13 e passa a ter prioridade.

`real` da sprint é a média ponderada por Story Points (tarefa sem SP conta 1) das minhas
tarefas não-épico; `esperado` é a fração de dias úteis já decorrida. Sprint `active` com
`end_date` no passado é **vencida**: o esperado vira 100% e a Home avisa.

A Home só mostra a sprint enquanto ela tiver **tarefa minha em aberto** (`status_category <>
'done'`, sem épico). É isso que faz uma sprint que estourou o prazo continuar na tela até o
trabalho acabar, e uma sprint ativa já resolvida sair dela. O filtro é do serviço
(`home_service._has_open_mine`), não da consulta: as mesmas linhas já vêm do banco para o
progresso e para os lembretes.

A regra de "outra pessoa mexeu na minha tarefa nas últimas 48h" mora em
`services/sprint_updates.py` porque tem dois consumidores: a linha "Mexeram nestas" de cada
sprint da Home, agrupada por sprint, e as notificações de tarefa do sino
(`GET /api/notifications/updates`), que devolve as sprints **ativas** numa lista só.

## Tempo real

`realtime/bus.py` é um pub/sub `asyncio` em memória — um processo, um dev, sem broker.
Quem escreve publica (`note.changed`, `context.changed`, `activity.new`, `progress.changed`,
`sync.finished`, `issue.changed`); `GET /api/events` transmite para as abas abertas.

A fila de cada assinante tem teto: uma aba lenta descarta o evento mais antigo em vez de
segurar o publicador — perder um aviso não corrompe nada, porque a tela recarrega do
servidor quando o recebe.

O stream fica aberto de propósito, então `uvicorn.run` usa
`timeout_graceful_shutdown=5`: sem teto, cada reload esperaria por ele para sempre.

## Escrita no Jira

`services/issue_actions.py` é o único lugar que escreve no Jira, e só duas coisas, cada uma
disparada por um gesto explícito do dev (duplo clique no status, Salvar nos pontos):

1. **Transição de status** — `GET /api/issues/{key}/transitions` lê *ao vivo* o status atual,
   as transições (com os campos de tela, `expand=transitions.fields`) e os status do workflow
   do tipo da tarefa (`/project/{key}/statuses`), e monta a linha na ordem das etapas de
   progresso. O `POST` relê as transições antes de aplicar: é o Jira quem diz para onde ela
   leva, e ela pode ter sumido se alguém mexeu na tarefa depois que a lista abriu.
2. **Story Points** — o campo gravado é o primeiro candidato (na prioridade do sync) que o
   `editmeta` da tarefa aceita; projeto team-managed usa "Story point estimate".

Depois que o Jira aceita:

- o **espelho** recebe o valor novo na hora, **sem** carimbar o `updated_at` — o próximo sync
  vê o `updated` do Jira mais novo, rebusca a tarefa e grava a transição e o evento a partir
  do changelog, como qualquer outra mudança;
- a **foto do card** (`issue_seen`) recebe só o campo mexido, para a mudança do próprio dev
  não acender a bolinha — sem engolir outra mudança que ele ainda não viu;
- o barramento publica `issue.changed` com um `write_id`, e o front recarrega uma vez só
  (a resposta do POST e o evento do stream trazem o mesmo id).

A transição vai com `idempotent=False`: o transporte só tenta de novo em 429 e falha de
conexão, quando o pedido com certeza não chegou. Um 5xx ou timeout de leitura vira erro com
"confira no Jira se a mudança entrou", em vez de uma segunda transição.

## Escrita em disco

Só o **PROGRESS canônico**, em `<repo>\.claude-outputs\progress\`, com escrita atômica e
hash otimista ([contrato](harness/progress-format.md)). Raízes permitidas: `C:\projects\` e
`C:\Users\<dev>\.claude\`. Todo o resto do harness é somente leitura.

## Workspace: disco, git e terminal

O Workspace (`/workspace`) é a única parte do SprintAI que lê o disco e roda processo. Três
peças, cada uma com o seu limite:

```
front/ ──► /api/workspace/*  (API :8765)
              ├─ services/workspace/discovery.py   lê .git/config e .git/HEAD — sem git
              ├─ services/workspace/git_local.py   git só leitura, lista branca
              └─ services/workspace/launcher.py    Code.exe / wt.exe na pasta
      └──► /api/terminal/*   (terminal host :8766, sem reload)
              └─ terminal/sessions.py ──► winpty (WinPTY) ──► powershell.exe
```

**Guarda de caminho** (`security/paths.py`). Todo caminho vindo do front passa por ela antes
de virar leitura, `cwd` de processo ou argumento do `code`/`wt`: só abaixo de `C:\projects\`
(e `~\.claude\`), symlink e junção resolvidos antes da comparação, `..` recusado mesmo que
resolva para dentro, caminho de rede recusado. A mensagem de erro não repete o caminho.

**Git só leitura** (`services/workspace/git_local.py`). Subcomandos `for-each-ref`, `log`,
`show`, `status` e `worktree` — nada mais passa. Sempre com `--no-optional-locks` (o
`status` normal pega o `index.lock` e brigaria com o git do terminal), `core.fsmonitor=false`
(o fsmonitor do `.git/config` é um comando que o `status` executaria) e, no `show`,
`--no-ext-diff --no-textconv`. Roda por `subprocess.run` numa thread: com `reload=True` o
uvicorn usa o `SelectorEventLoop` no Windows, onde `create_subprocess_exec` não existe. A
tela pergunta a cada 5 s com a impressão digital do `.git` (mtime de HEAD, index, refs,
packed-refs, FETCH_HEAD e worktrees); sem mudança, o git não roda. `fetch` nunca é automático.

**Git de escrita local** (`services/workspace/git_actions.py`). Três ações, cada uma por
clique do dev no painel de branches, serializadas por repo (`branch_service`, um lock por
slug):

| Ação | Comando | Recusa |
|---|---|---|
| Fetch | `git fetch origin --prune` | — (só traz; o ssh vai em `BatchMode`, sem pedir senha) |
| Avançar | aberta numa worktree: `merge --ff-only <upstream>` lá dentro; fechada: `fetch . <upstream>:refs/heads/<branch>` | divergiu, alteração no caminho, sem upstream, worktree fora das raízes |
| Apagar | `git branch -d` (`-D` só com `force`, a segunda confirmação) | a base, a aberta numa worktree |

Escrita precisa do lock, então aqui não vai `--no-optional-locks`; o resto da proteção fica
(`core.fsmonitor=false`, sem prompt, timeout, sem janela). O stderr do git não vai para a
tela: os casos conhecidos viram mensagem pronta com um `code` (`unmerged`, `diverged`,
`checked_out`, `auth`…), e é pelo `code` que a tela decide o que oferecer. Nada empurra nem
apaga no Bitbucket.

**Terminal host** (`terminal_host.py`, `terminal/`). Processo à parte, sem reload — cada
edição no `back/` derrubaria os shells da API. Não abre banco nem Cofre. Sem WebSocket, para
a guarda ficar inteira: a saída de todas as sessões vem num stream só
(`GET /api/terminal/stream`, `fetch` + `ReadableStream`) e as teclas vão por POST com o
`X-SprintAI`. A saída é numerada por sessão e guardada num buffer circular em memória; a
reconexão manda `since=<id>:<offset>` e recebe só o que falta (ou um `reset` com o buffer).
A API recebe **pasta e perfil** — nunca um comando — e o shell nasce com o ambiente do dev
menos a configuração do SprintAI (`security/process_env.py`). A saída não vai para log,
banco, busca nem contexto do agente.

O backend é o **WinPTY**, não o ConPTY: o spike W0 mostrou que o ConPTY do pywinpty cria o
processo com o Ctrl+C desligado para os filhos. Encerrar um terminal é `taskkill /T /F` no
shell — a árvore inteira.
