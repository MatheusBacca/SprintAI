const pad = (n) => String(n).padStart(2, '0')

/** ISO (com fuso) → valor de `<input type="datetime-local">` no fuso do navegador. */
export function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Valor do `datetime-local` (hora local, sem fuso) → ISO com fuso, como a API exige. */
export function fromLocalInput(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Atalhos de horário para lembrete. */
export function reminderPresets(now = new Date()) {
  const inOneHour = new Date(now.getTime() + 60 * 60 * 1000)
  inOneHour.setSeconds(0, 0)

  const tomorrow9 = new Date(now)
  tomorrow9.setDate(now.getDate() + 1)
  tomorrow9.setHours(9, 0, 0, 0)

  const nextMonday9 = new Date(now)
  const daysToMonday = ((8 - now.getDay()) % 7) || 7
  nextMonday9.setDate(now.getDate() + daysToMonday)
  nextMonday9.setHours(9, 0, 0, 0)

  return [
    { id: '1h', label: 'Em 1 hora', at: inOneHour },
    { id: 'tomorrow', label: 'Amanhã 9h', at: tomorrow9 },
    { id: 'monday', label: 'Segunda 9h', at: nextMonday9 },
  ]
}

const dateTimeFormat = new Intl.DateTimeFormat('pt-BR', {
  weekday: 'short',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDateTime(iso) {
  return iso ? dateTimeFormat.format(new Date(iso)) : ''
}
