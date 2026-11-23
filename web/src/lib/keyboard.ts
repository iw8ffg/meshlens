// Tiene un elemento (il compositore della chat) sopra la tastiera su telefono, con visualViewport.

/** Ctrl+K (Cmd+K su Mac), senza Alt né Maiusc: apre la ricerca globale, anche con il focus in un campo. */
export function isSearchShortcut(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>): boolean {
  return (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k'
}

/**
 * Di quanti pixel sollevare l'elemento: il suo bordo inferiore "naturale" (senza sollevamento)
 * meno il bordo inferiore del viewport visibile; mai negativo.
 */
export function keyboardLift(rectBottom: number, currentLift: number, vvHeight: number, vvOffsetTop: number): number {
  const natural = rectBottom + currentLift
  return Math.max(0, Math.round(natural - (vvOffsetTop + vvHeight)))
}

/** Azione Svelte: ascolta resize e scroll di visualViewport e solleva l'elemento; ripulisce alla chiusura. */
export function keepAboveKeyboard(node: HTMLElement): { destroy: () => void } {
  const vv = typeof window === 'undefined' ? null : window.visualViewport
  if (!vv) return { destroy() {} }
  let lift = 0
  const update = () => {
    const next = keyboardLift(node.getBoundingClientRect().bottom, lift, vv.height, vv.offsetTop)
    if (next === lift) return
    lift = next
    node.style.transform = next ? `translateY(${-next}px)` : ''
  }
  vv.addEventListener('resize', update)
  vv.addEventListener('scroll', update)
  node.addEventListener('focusin', update)
  update()
  return {
    destroy() {
      vv.removeEventListener('resize', update)
      vv.removeEventListener('scroll', update)
      node.removeEventListener('focusin', update)
      node.style.transform = ''
    },
  }
}
