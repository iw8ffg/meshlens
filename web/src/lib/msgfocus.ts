// Salto al messaggio trovato: la ricerca chiede di mettere a fuoco un messaggio, la conversazione
// aperta lo consuma. Variabile di modulo semplice, non reattiva (come `chatBridge`).
let pending: string | null = null

/** Chiede di mettere a fuoco il messaggio con questa chiave (sostituisce una richiesta precedente). */
export function requestFocus(key: string): void {
  pending = key
}

/** Chiave in attesa, senza consumarla. */
export function peekFocus(): string | null {
  return pending
}

/** Chiave in attesa; la richiesta viene consumata (una sola lettura). */
export function takeFocus(): string | null {
  const k = pending
  pending = null
  return k
}
