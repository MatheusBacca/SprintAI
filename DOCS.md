# Documentação do SprintAI

| Documento | O que responde |
|---|---|
| [README.md](README.md) | O que a ferramenta faz, setup, cada tela e a lista de endpoints |
| [CLAUDE.md](CLAUDE.md) | Como mexer no código: stack, comandos, convenções, regras de segurança e as armadilhas do domínio |
| [docs/architecture.md](docs/architecture.md) | Camadas, fluxo de uma sincronização, como o tempo real funciona e o que a guarda local protege |
| [docs/harness/progress-format.md](docs/harness/progress-format.md) | Contrato do `PROGRESS.md` — o único arquivo que o SprintAI escreve |
| [docs/harness/discovery.md](docs/harness/discovery.md) | O que é indexado do disco, de onde, por quê e o que nunca é lido |
| [docs/agent/context-contract.md](docs/agent/context-contract.md) | O que vai (e o que nunca vai) no contexto do agente Claude |

## Onde as decisões moram

- **Plano de entregas:** `C:\Users\Matheus Bacca\.claude\plans\gostaria-de-planejar-um-snuggly-bubble.md`
- **Progresso deste plano:** `.claude-outputs/progress/` (gitignored — é dogfooding do
  formato descrito em [progress-format.md](docs/harness/progress-format.md))
- **Design:** tokens em `front/src/styles/tokens.css`, com base no `DESIGN.md` do
  `organia-configs`. O tema escuro é o mesmo arquivo sob `[data-theme='dark']`;
  quem escolhe é o botão no rodapé da sidebar (store `ui`), e sem escolha salva
  o app segue o `prefers-color-scheme` do Windows

## Estado das entregas

| Marco | Situação |
|---|---|
| M1 — Vejo minha sprint | concluído |
| M2 — Guardo o que aprendi | concluído |
| **M5 — Abro a Home e sei onde estou** | **concluído** (P0, B8, B9, B10, B11, F11) |
| M6 — O harness dos meus repos vira dado | a fazer (B12, B13, B14, F12, F13) |
| M7 — Encontro qualquer coisa | F6 concluída; B6 e F7 a fazer |
| M8 — Agente Claude | bases (A1–A3) a fazer; feature quando o dev pedir |
