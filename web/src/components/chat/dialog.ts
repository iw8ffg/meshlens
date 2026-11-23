// Azione Svelte per le finestre della chat (ricerca, esportazione): focus dentro la finestra,
// trappola di Tab, Esc chiude, il focus torna a chi lo aveva alla chiusura.
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function dialogTrap(node: HTMLElement, onclose: () => void): { update: (fn: () => void) => void; destroy: () => void } {
  let close = onclose
  const prev = document.activeElement as HTMLElement | null
  ;(node.querySelector<HTMLElement>('[data-autofocus]') ?? node).focus()
  const onkey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      close()
      return
    }
    if (e.key !== 'Tab') return
    const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)]
    if (!items.length) {
      e.preventDefault()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const cur = document.activeElement
    if (e.shiftKey && (cur === first || cur === node)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && cur === last) {
      e.preventDefault()
      first.focus()
    }
  }
  node.addEventListener('keydown', onkey)
  return {
    update(fn) {
      close = fn
    },
    destroy() {
      node.removeEventListener('keydown', onkey)
      prev?.focus?.()
    },
  }
}
