/**
 * Cores de post-it — mesmas chaves do CHECK da tabela `note`.
 * Os valores são tokens porque o papel muda de tom entre o tema claro e o
 * escuro; o hex de cada um mora em `styles/tokens.css`.
 */
export const NOTE_COLORS = {
  yellow: {
    label: 'Amarelo',
    bg: 'var(--note-yellow-bg)',
    border: 'var(--note-yellow-border)',
    accent: 'var(--note-yellow-accent)',
  },
  pink: {
    label: 'Rosa',
    bg: 'var(--note-pink-bg)',
    border: 'var(--note-pink-border)',
    accent: 'var(--note-pink-accent)',
  },
  green: {
    label: 'Verde',
    bg: 'var(--note-green-bg)',
    border: 'var(--note-green-border)',
    accent: 'var(--note-green-accent)',
  },
  blue: {
    label: 'Azul',
    bg: 'var(--note-blue-bg)',
    border: 'var(--note-blue-border)',
    accent: 'var(--note-blue-accent)',
  },
  purple: {
    label: 'Roxo',
    bg: 'var(--note-purple-bg)',
    border: 'var(--note-purple-border)',
    accent: 'var(--note-purple-accent)',
  },
  gray: {
    label: 'Cinza',
    bg: 'var(--note-gray-bg)',
    border: 'var(--note-gray-border)',
    accent: 'var(--note-gray-accent)',
  },
}

export const NOTE_COLOR_KEYS = Object.keys(NOTE_COLORS)
