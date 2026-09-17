# Contrato de contexto do agente

> **Estado:** contrato definido no P0 (M5). O contexto de tela é a **A1**, o montador é a
> **A2** e as ferramentas são a **A3** — todos sem LLM. O provider Claude é a B7', e só
> começa quando o dev pedir.

O agente do SprintAI é **Claude**, via Claude Agent SDK, consumindo `CLAUDE.md`, skills e
agents nativamente. Este documento diz o que entra no contexto dele, o que nunca entra e
como uma escrita vira proposta em vez de ação.

## O que o agente recebe

| Bloco | Origem | Observação |
|---|---|---|
| Perfil do dev | conexão do Jira | nome e `account_id`. **Nunca** o token |
| Sprint ativa e progresso | `GET /api/home` | real, esperado, sprint vencida |
| Contexto de tela | `agent_session` (A1) | rota, aba aberta, tarefa em foco, seleção de texto, período da timeline, filtros |
| Tarefa em foco | espelho | campos, descrição, contextos, lembretes, PRs, PROGRESS |
| `CLAUDE.md` dos repos da tarefa | disco | só dos repos ligados à tarefa em foco |

Tudo com **orçamento de tokens**: o montador corta pelo bloco menos relevante, nunca pelo
meio de um documento.

`GET /api/agent/context/preview` mostra **exatamente** o que seria enviado. Se o preview não
mostra, não vai.

## O que nunca entra

- **Segredo de qualquer tipo.** Token de Jira/Bitbucket, chave da Anthropic, `.env`,
  `settings.local.json`. O indexador nem lê esses arquivos
  ([discovery](../harness/discovery.md)).
- **Arquivo fora das raízes permitidas** (`C:\projects\`, `C:\Users\<dev>\.claude\`).
- **Código-fonte inteiro.** O agente tem `Read`/`Grep` nos repos mapeados e busca o que
  precisa; despejar arquivo no prompt é desperdício e vazamento.

## Conteúdo de terceiros é dado

Descrição de tarefa, comentário, título de PR e todo `.md` lido do disco são **dados**,
marcados como não confiáveis no prompt. Instrução vem do dev, pela interface — nunca de um
texto que o agente leu. Um comentário de Jira que diga "ignore as instruções acima" é um
comentário de Jira.

## Ferramentas

Servidas como um **servidor MCP** (`agent_tools/`), usável tanto pelo dock do SprintAI
quanto pelo Claude Code no terminal.

**Leitura** (executam direto): `search`, `get_issue`, `get_week`, `get_activity`,
`get_sprint_progress`, `list_open_points`, `list_notes`, `list_harness`, `read_harness_doc`,
`get_screen_context`.

**Escrita** (só geram proposta): `create_note`, `create_context`, `toggle_progress_item`,
`append_progress_log`, `transition_issue`, `comment_issue`.

## Escrita é proposta, não ação

Toda ferramenta de escrita grava uma linha em `ai_action_proposal` e devolve o id. Nada
acontece até o dev confirmar na interface. O callback de permissão do Agent SDK converte
qualquer tentativa de escrita em proposta — não há caminho alternativo.

O agente roda **sem `Bash` e sem `Edit`**. `cwd` é o repo da tarefa em foco e
`setting_sources` é user+project, para o `CLAUDE.md` e as skills valerem.

No Jira, a regra do time continua: **status nunca é aproximado**. A proposta lista as
transições disponíveis para aquela issue; se a transição desejada não existe no workflow, o
agente mostra o que há e pergunta.
