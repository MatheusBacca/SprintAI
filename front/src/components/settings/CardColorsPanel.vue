<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Palette, Plus, RotateCcw, X } from 'lucide-vue-next'
import ChipsInput from '@/components/notes/ChipsInput.vue'
import { useCardColorsStore } from '@/stores/cardColors'

/**
 * Configurações › Cores dos cards: o fundo esfumaçado dos cards do canvas da sprint. Os
 * pais pelo tipo; as tarefas pelo repositório entre colchetes no começo do título. Quem
 * aplica a regra é o back — a prévia de cada linha só mostra como o card fica com a cor
 * escolhida e ainda não salva.
 */
const store = useCardColorsStore()

const draft = ref(null)

function reset() {
  if (!store.loaded) return
  draft.value = {
    types: Object.fromEntries(store.types.map((t) => [t.id, t.color])),
    repos: Object.fromEntries(store.repos.map((r) => [r.slug, r.color])),
    aliases: Object.fromEntries(store.repos.map((r) => [r.slug, [...r.aliases]])),
  }
}

onMounted(async () => {
  await store.load()
  reset()
})
watch(() => [store.types, store.repos], reset)

const dirty = computed(() => {
  if (!draft.value) return false
  return (
    store.types.some((t) => draft.value.types[t.id] !== t.color) ||
    store.repos.some((r) => draft.value.repos[r.slug] !== r.color) ||
    store.repos.some((r) => draft.value.aliases[r.slug].join('\n') !== r.aliases.join('\n'))
  )
})

const MAX_ALIAS_LENGTH = 60

function normalizeAlias(text) {
  const alias = text.trim()
  return alias && alias.length <= MAX_ALIAS_LENGTH ? alias : null
}

// A mesma comparação do `repo_key` do back: sem caixa, acento, hífen ou espaço.
function nameKey(name) {
  return name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

/**
 * Apelido que já é o slug de outro repositório, ou apelido de outro também. O back recusa
 * sem dizer qual (não repete o que foi digitado); aqui a linha diz qual é e de quem.
 */
const conflicts = computed(() => {
  if (!draft.value) return {}
  const slugs = new Map(store.repos.map((r) => [nameKey(r.slug), r.slug]))
  const users = new Map()
  for (const [slug, names] of Object.entries(draft.value.aliases)) {
    for (const name of names) {
      const key = nameKey(name)
      users.set(key, [...(users.get(key) ?? []), slug])
    }
  }
  // As duas linhas avisam: quem tinha o apelido e quem acabou de pôr.
  const found = {}
  for (const [slug, names] of Object.entries(draft.value.aliases)) {
    for (const name of names) {
      const key = nameKey(name)
      const owner = slugs.get(key)
      const others = (users.get(key) ?? []).filter((s) => s !== slug)
      let text = null
      if (owner && owner !== slug) text = `"${name}" já é o ${owner}`
      else if (others.length) text = `"${name}" também é apelido do ${others.join(', ')}`
      if (text) (found[slug] ??= []).push({ name, text })
    }
  }
  return found
})

const blocked = computed(() => Object.keys(conflicts.value).length > 0)

// Primeira sugestão que nenhum repositório está usando: três cliques em "Definir cor"
// dão três cores diferentes. Esgotadas, volta a repetir da primeira.
function suggestion() {
  const used = new Set(Object.values(draft.value.repos).filter(Boolean))
  return store.suggestions.find((c) => !used.has(c)) ?? store.suggestions[0]
}

function setType(id, color) {
  draft.value.types[id] = color
}

function setRepo(slug, color) {
  draft.value.repos[slug] = color
}

function setAliases(slug, names) {
  draft.value.aliases[slug] = names
}

async function save() {
  await store.save(draft.value)
}
</script>

<template>
  <section class="colors card">
    <header class="colors__header">
      <Palette :size="18" />
      <div>
        <h2 class="colors__title">Cor do fundo dos cards</h2>
        <p class="colors__desc">
          O canvas da sprint pinta o fundo do card com um esfumaçado leve, a partir do canto de cima. Os pais
          ganham a cor do tipo; as tarefas, a do repositório entre colchetes no começo do título —
          <code>[monitoria] Enviar a coleta…</code>, com o nome de dentro do colchete na cor do
          repositório. A grafia não importa (<code>[MonitorIA]</code> vale para <code>monitoria</code>), o
          começo do nome até um hífen também vale quando só um repositório começa assim
          (<code>[weaction]</code> para <code>weaction-api</code>), e outros apelidos vão no campo de cada
          repositório. Com mais de um no colchete (<code>[supervisor/qualificai]</code>), cada cor
          entra no fundo na ordem do título, da esquerda para a direita. Card sem tipo nem repositório
          com cor fica como sempre foi, e a cor da etapa continua na borda e no selo de status.
        </p>
      </div>
    </header>

    <p v-if="store.error" class="colors__error" role="alert">{{ store.error }}</p>
    <p v-else-if="!draft" class="colors__muted">Carregando…</p>

    <template v-else>
      <div class="colors__section">
        <h3 class="colors__sub">Por tipo</h3>
        <ul class="colors__list">
          <li v-for="type in store.types" :key="type.id" class="row" :data-type="type.id">
            <div class="row__name">
              <strong>{{ type.label }}</strong>
            </div>
            <div
              class="preview"
              :class="{ 'preview--tinted': draft.types[type.id] }"
              :style="{ '--tint': draft.types[type.id] }"
              aria-hidden="true"
            >
              <span class="preview__type">{{ type.label.toUpperCase() }}</span>
              <span class="preview__title">Título do card</span>
            </div>
            <div class="row__actions">
              <template v-if="draft.types[type.id]">
                <input
                  :value="draft.types[type.id]"
                  type="color"
                  class="row__color"
                  :aria-label="`Cor do ${type.label}`"
                  @input="setType(type.id, $event.target.value)"
                >
                <button
                  v-if="draft.types[type.id] !== type.default_color"
                  type="button"
                  class="btn btn--secondary row__btn"
                  title="Voltar à cor padrão"
                  @click="setType(type.id, type.default_color)"
                >
                  <RotateCcw :size="13" /> Padrão
                </button>
                <button
                  type="button"
                  class="btn btn--secondary row__btn row__clear"
                  :title="`Deixar o ${type.label} sem cor`"
                  :aria-label="`Deixar o ${type.label} sem cor`"
                  @click="setType(type.id, null)"
                >
                  <X :size="13" />
                </button>
              </template>
              <button
                v-else
                type="button"
                class="btn btn--secondary row__btn row__define"
                @click="setType(type.id, type.default_color)"
              >
                <Plus :size="13" /> Definir cor
              </button>
            </div>
          </li>
        </ul>
      </div>

      <div class="colors__section">
        <h3 class="colors__sub">Por repositório</h3>
        <p v-if="!store.repos.length" class="colors__muted">
          Nenhum repositório escolhido.
          <RouterLink :to="{ query: { aba: 'sincronizacao' } }">Escolha em Sincronização</RouterLink>
          os repositórios do Bitbucket, e eles aparecem aqui.
        </p>
        <ul v-else class="colors__list">
          <li v-for="repo in store.repos" :key="repo.slug" class="row" :data-repo="repo.slug">
            <div class="row__name">
              <strong>{{ repo.slug }}</strong>
              <small
                v-if="!repo.synced"
                class="row__warning"
                title="Saiu de Configurações › Sincronização, mas ainda tem cor ou apelido"
              >
                fora da sincronização
              </small>
              <label class="row__sr" :for="`apelidos-${repo.slug}`">Apelidos do {{ repo.slug }}</label>
              <ChipsInput
                class="row__aliases"
                :model-value="draft.aliases[repo.slug]"
                :normalize="normalizeAlias"
                :input-id="`apelidos-${repo.slug}`"
                invalid-message="Apelido com mais de 60 caracteres"
                placeholder="apelidos (Enter ou vírgula)"
                @update:model-value="setAliases(repo.slug, $event)"
              />
              <small v-if="repo.automatic_aliases.length" class="row__hint">
                Também vale: {{ repo.automatic_aliases.map((name) => `[${name}]`).join(', ') }}
              </small>
              <small v-for="conflict in conflicts[repo.slug] ?? []" :key="conflict.name" class="row__conflict" role="alert">
                {{ conflict.text }}
              </small>
            </div>
            <div
              class="preview"
              :class="{ 'preview--tinted': draft.repos[repo.slug] }"
              :style="{ '--tint': draft.repos[repo.slug] }"
              aria-hidden="true"
            >
              <span class="preview__type">TAREFA</span>
              <span class="preview__title">[<span class="preview__repo">{{ repo.slug }}</span>] Título da tarefa</span>
            </div>
            <div class="row__actions">
              <template v-if="draft.repos[repo.slug]">
                <input
                  :value="draft.repos[repo.slug]"
                  type="color"
                  class="row__color"
                  :aria-label="`Cor do ${repo.slug}`"
                  @input="setRepo(repo.slug, $event.target.value)"
                >
                <button
                  type="button"
                  class="btn btn--secondary row__btn row__clear"
                  :title="`Deixar o ${repo.slug} sem cor`"
                  :aria-label="`Deixar o ${repo.slug} sem cor`"
                  @click="setRepo(repo.slug, null)"
                >
                  <X :size="13" />
                </button>
              </template>
              <button
                v-else
                type="button"
                class="btn btn--secondary row__btn row__define"
                @click="setRepo(repo.slug, suggestion())"
              >
                <Plus :size="13" /> Definir cor
              </button>
            </div>
          </li>
        </ul>
      </div>

      <footer class="colors__footer">
        <p v-if="store.feedback" class="colors__feedback" :data-type="store.feedback.type" role="status">
          {{ store.feedback.text }}
        </p>
        <button type="button" class="btn btn--secondary" :disabled="!dirty || store.saving" @click="reset">
          Descartar
        </button>
        <p v-if="blocked" class="colors__feedback" data-type="error" role="status">
          Tem apelido valendo para dois repositórios — ajuste antes de salvar.
        </p>
        <button type="button" class="btn btn--primary" :disabled="!dirty || blocked || store.saving" @click="save">
          {{ store.saving ? 'Salvando…' : 'Salvar cores' }}
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.colors {
  max-width: 820px;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.colors__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.colors__header > svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-primary);
}

.colors__title {
  margin: 0 0 4px;
  font-size: var(--text-md);
  font-weight: 600;
}

.colors__desc,
.colors__muted {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.colors__desc code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.colors__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.colors__sub {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.colors__list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.row {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 236px minmax(150px, auto);
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
}

.row:last-child {
  border-bottom: 0;
}

.row__name {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: var(--text-sm);
}

.row__name strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.row__name small {
  font-size: 11px;
}

.row__warning {
  color: var(--color-warning);
}

.row__hint {
  margin-top: 3px;
  color: var(--color-text-muted);
}

.row__conflict {
  margin-top: 3px;
  color: var(--color-error);
}

.row__aliases {
  margin-top: 6px;
}

/* O campo de apelidos é baixo aqui: a linha é de uma cor, não um formulário. */
.row__aliases :deep(.chips-input) {
  min-height: 30px;
  padding: 2px 6px;
}

.row__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.row__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.row__color {
  width: 36px;
  height: 28px;
  padding: 2px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  cursor: pointer;
}

.row__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  font-size: var(--text-xs);
}

.row__clear {
  padding: 0 7px;
}

/* A largura e a borda do card do canvas, bem mais baixo: o que importa aqui é o fundo. */
.preview {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  height: 52px;
  padding: 0 12px;
  overflow: hidden;
  border: 1.5px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

/* O mesmo esfumaçado do `.node--tinted` do IssueNode. */
.preview--tinted {
  background:
    radial-gradient(
      130% 150% at 0% 0%,
      color-mix(in srgb, var(--tint) var(--card-tint-mix), transparent),
      transparent 65%
    ),
    var(--color-surface);
}

.preview__type {
  font-size: 10px;
  font-weight: 600;
  line-height: 14px;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
}

/* E o tipo e o nome do colchete na cor do card, como no IssueNode. */
.preview--tinted .preview__type,
.preview--tinted .preview__repo {
  color: color-mix(in srgb, var(--tint) var(--card-tint-ink), var(--color-text));
}

.preview__title {
  flex-shrink: 0;
  line-height: 17px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text);
}

.colors__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.colors__feedback {
  margin: 0 auto 0 0;
  font-size: var(--text-sm);
}

.colors__feedback[data-type='success'] {
  color: var(--color-success);
}

.colors__feedback[data-type='error'] {
  color: var(--color-error);
}

@media (max-width: 640px) {
  .row {
    grid-template-columns: 1fr auto;
  }

  .preview {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}
</style>
