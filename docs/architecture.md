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
`sync.finished`); `GET /api/events` transmite para as abas abertas.

A fila de cada assinante tem teto: uma aba lenta descarta o evento mais antigo em vez de
segurar o publicador — perder um aviso não corrompe nada, porque a tela recarrega do
servidor quando o recebe.

O stream fica aberto de propósito, então `uvicorn.run` usa
`timeout_graceful_shutdown=5`: sem teto, cada reload esperaria por ele para sempre.

## Escrita em disco

Só o **PROGRESS canônico**, em `<repo>\.claude-outputs\progress\`, com escrita atômica e
hash otimista ([contrato](harness/progress-format.md)). Raízes permitidas: `C:\projects\` e
`C:\Users\<dev>\.claude\`. Todo o resto do harness é somente leitura.
