/**
 * Copia os dois formatos: o HTML já renderizado (colar no Jira ou no Slack sai
 * formatado) e o texto original como texto puro (colar num editor sai igual à fonte).
 * Onde o navegador não deixa escrever os dois, vai só o texto. `true` se copiou.
 *
 * `html` sai do DOM que o app já renderizou (AdfRenderer, MarkdownRenderer), nunca de
 * string vinda de fora — é o mesmo conteúdo que está na tela.
 */
export async function copyRichText({ html = null, text = '' }) {
  return (await copyByClipboardApi(html, text)) || copyBySelection(text)
}

async function copyByClipboardApi(html, text) {
  try {
    if (html && typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }),
        }),
      ])
      return true
    }
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/**
 * Último recurso, só o texto: a Clipboard API é negada em contexto embutido e por
 * política de navegador, e aí a seleção temporária ainda copia. Vale mais que um
 * botão que não faz nada.
 */
function copyBySelection(text) {
  if (typeof document.execCommand !== 'function') return false
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0'
  document.body.appendChild(area)
  area.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    area.remove()
  }
}
