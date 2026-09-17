# Descoberta do harness

> **Estado:** desenho fechado no P0 (M5); o indexador é a **B13** e o vínculo repo ↔ pasta é
> a **B12**, ambos no M6.

O "harness" é a estrutura que os agentes Claude já entendem e que hoje só existe como
arquivo no disco: `CLAUDE.md`, `DOCS.md`, `PROGRESS.md`, skills, agents, plans, memory,
specs e handoffs. A ideia do M6 é fazer o SprintAI **ler** isso e virar dado: aparecer na
busca (`Ctrl+K`), na aba Harness do painel da tarefa e no progresso da semana.

## Raízes permitidas

| Raiz | O que é |
|---|---|
| `C:\projects\` | todos os repositórios de trabalho |
| `C:\Users\<dev>\.claude\` | harness pessoal (CLAUDE.md, skills, agents, plans, memory) |

Nada fora disso é lido. **`Z:\` nunca** — se um repo não está em `C:\projects\`, ele não
está clonado.

Toda leitura resolve symlinks e recusa `..`: um caminho que escape das raízes é erro, não
aviso.

## Vínculo repo ↔ pasta (B12)

Não existe hoje. A descoberta é **só leitura** e sem nenhum comando git:

1. lista as pastas de `C:\projects\`;
2. lê `.git/config` e casa o remote `git@bitbucket.org:weonrepo/<slug>.git` com o
   `bb_repository.slug` do espelho;
3. lê `.git/HEAD` para a branch atual.

O slug do Bitbucket é sempre igual ao nome da pasta. As exceções conhecidas viram "local sem
vínculo", e o dev confirma ou ajusta em Configurações › Workspace:

| Pasta | Por quê |
|---|---|
| `sprintai` | sem remote |
| `appingos` | GitHub pessoal |
| `mcp`, `daily-git-report`, `weon-proativo-mcp` | sem git |

## O que é lido (B13)

**Por repositório:**

- `*.md` da raiz e `docs/**` (profundidade limitada);
- `.claude/{skills,agents,commands}/**/*.md`;
- `.claude-outputs/**/*.md` — reviews, descrições de PR e planos escritos pela skill
  `preview`;
- `specs/*/{spec,plan,tasks}.md` — o formato de checklist mais maduro que existe hoje
  (`- [x] **T-1**: …` com `Done when:`), no `weaction-api`.

**No escopo pessoal:**

- `~/.claude/CLAUDE.md`;
- `~/.claude/skills/*/SKILL.md`;
- `~/.claude/agents/*.md`;
- `~/.claude/plans/*.md`;
- `~/.claude/projects/*/memory/*.md`.

## O que nunca é lido

- **Qualquer coisa que não seja `.md`.** Em particular `settings.json`, `settings.local.json`
  e `.env` — eles carregam segredo e caminho de máquina.
- `node_modules`, `.venv`, `dist`, `.git`.
- Arquivo maior que 1 MB.

## Como a chave da tarefa é extraída

Na ordem:

1. nome do arquivo — `<tipo>-WAI-XXXX[-tema]-AAAA-MM-DD.md`;
2. `specs/(\d+)-<slug>/` — o número da spec, quando ele mapeia para uma chave;
3. frontmatter `issue:`;
4. prefixo no primeiro `#` do arquivo.

## Quando a varredura roda

No mesmo laço do agendador de sync (`services/sync/engine.py`), comparando `mtime` + hash —
arquivo que não mudou não é reprocessado. Há também um botão "Reindexar". Ao terminar, emite
`harness.changed` no barramento, e as telas abertas recarregam sozinhas.

## O que já existe hoje (levantamento de 14/09/2026)

| Artefato | Onde |
|---|---|
| `CLAUDE.md` | `supervisor-web`, `weaction-api` (e agora `sprintai`) |
| `DESIGN.md` | `organia-configs` |
| `specs/<n>-<slug>/{spec,plan,tasks}.md` | `weaction-api` (6) |
| `docs/handoff/handoff-WAI-*.md` | `weaction-api` (21) |
| `.claude-outputs/{reviews,pr-descriptions,planos}` | 7 repos |
| `PROGRESS.md`, `AGENTS.md` | nenhum ainda |

`.claude-outputs/` está no `.gitignore` de `monitoria`, `organia-configs`, `qualificai`,
`supervisor-web` e `weaction-api`. **Não** está em `api-audio-transcribe` nem `api-credits` —
por isso a B14 exige confirmação antes de escrever nesses dois.

## Conteúdo é dado, nunca instrução

Todo `.md` indexado é tratado como **dado**. Isso vale para o indexador, para o visualizador
(markdown com `html: false` e links sanitizados) e principalmente para o montador de contexto
do agente ([contrato](../agent/context-contract.md)). Um arquivo no disco não manda no agente.
