# Contrato do `PROGRESS.md`

> **Estado:** contrato definido no P0 (M5); a leitura e a escrita chegam na **B14** (M6).
> Este arquivo é a especificação que a B14 implementa, e já vale como formato para os
> PROGRESS escritos à mão enquanto isso.

O `PROGRESS.md` é o **único** arquivo que o SprintAI escreve. Todo o resto do harness
(`CLAUDE.md`, `DOCS.md`, skills, agents, specs, handoffs, memory) é somente leitura.

## Onde mora

```
<repo>\.claude-outputs\progress\PROGRESS-WAI-XXXX.md
```

Mesmo padrão da skill `preview`, que já escreve em `.claude-outputs/`. O SprintAI **nunca**
escreve fora de `.claude-outputs\progress\` e **nunca** edita o `.gitignore`: num repo que
não ignora `.claude-outputs` (hoje `api-audio-transcribe` e `api-credits`), ele avisa e
exige confirmação por repo antes da primeira escrita.

Card "Analisar e fatiar" não tem repo próprio: o dev escolhe. O padrão sugerido é o repo
das fatias já criadas; sem elas, o repo principal do Enhancement.

## Formato

````markdown
---
issue: WAI-8360
kind: task            # task | slicing
sprint: Sprint 74 - Growth
repos: [weaction-api, supervisor-web]
parent: WAI-7326      # Épico ou Enhancements
updated: 2026-09-14T21:30:00-03:00
updated_by: sprintai  # sprintai | dev | agent
---

# WAI-8360 — Remover DESATIVAR GRUPO do catálogo de ações

## Checklist

- [x] **P-1**: Tirar as ações do enum do catálogo (WAI-8361)
  Done when: o filtro de Ação não lista mais as duas e o teste cobre o legado
- [ ] **P-2**: Migration para reclassificar o histórico já gravado
- [ ] **P-3**: Ajustar a coluna Grupo no supervisor-web (WAI-8362)

## Notas

Texto livre. O SprintAI lê e mostra, mas nunca reescreve.

## Log

- 2026-09-14 21:30 — P-1 concluído (sprintai)
- 2026-09-13 10:12 — criado a partir do template (sprintai)
````

### Frontmatter

| Campo | Obrigatório | Observação |
|---|---|---|
| `issue` | sim | chave `WAI-XXXX` do card que este arquivo acompanha |
| `kind` | sim | `task` (desenvolvimento) ou `slicing` (card "Analisar e fatiar") |
| `sprint` | não | nome da sprint, como vem do Jira |
| `repos` | não | slugs dos repositórios afetados |
| `parent` | não | Épico ou Enhancements |
| `updated` | sim | ISO com fuso, reescrito a cada gravação |
| `updated_by` | sim | quem gravou por último |

### `## Checklist`

- Um item por linha, `- [ ]` ou `- [x]`.
- **Código do item** em negrito: `**P-1**`, `**P-2**`… Ele é a identidade do item e **não
  muda** — é por ele que o `PATCH` marca e desmarca. Compatível com o `T-n` dos
  `specs/*/tasks.md` do `weaction-api`, que o mesmo parser lê.
- Texto livre depois do `:`. Uma chave `(WAI-YYYY)` no fim liga o item a uma tarefa do Jira
  — é assim que um card de fatiar aponta para as fatias já criadas.
- `Done when:` na linha seguinte, indentado, é o critério de pronto (opcional).

### `## Notas` e `## Log`

`Notas` é texto livre. `Log` é **só acréscimo**: linhas datadas, sempre no topo, nunca
reescritas.

Qualquer outra seção que o dev criar é **preservada intacta**.

## API (B14)

| Rota | O que faz |
|---|---|
| `POST /api/progress` | cria a partir do template, no repo escolhido |
| `PATCH /api/progress/{doc}/items/{code}` | marca/desmarca um item |

O `PATCH` leva `expected_hash`. Se o arquivo mudou no disco desde a última leitura, a API
responde **409** em vez de sobrescrever — o dev edita `.md` à mão o tempo todo, e um editor
aberto não pode perder trabalho para a Home.

## Regras de escrita

- **Atômica**: arquivo temporário + `replace`.
- **Preserva o desconhecido**: seções, comentários e formatação fora do checklist voltam
  como estavam.
- **Preserva os fins de linha** do arquivo (LF continua LF).
- **Caminho validado**: resolve symlinks, recusa `..` e qualquer coisa fora de
  `<repo mapeado>\.claude-outputs\progress\`.
- Marcar um item acrescenta uma linha no `## Log` e atualiza `updated`/`updated_by`.

## Como ele vira progresso

Com checklist presente, a fonte `checklist` (F13) tem prioridade sobre a fonte `status`:
`value = feitos / total`. A tarefa mostra na Home e na timeline qual fonte respondeu, para
o número nunca ser uma caixa-preta.

Para um card `kind: slicing`, o progresso é composto: o checklist próprio **mais** o
progresso de cada fatia já criada (Tarefas ligadas por `Relates` ao Enhancement, na mesma
sprint). Fatia ainda não criada existe só como item do checklist.
