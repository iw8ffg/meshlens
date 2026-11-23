// Stato reattivo dei contatti ATAK: caricamento e aggiornamento in tempo reale (evento `tak_contact`).
import { onWsEvent, onWsResync } from '../wsext'
import type { TakContact, TakSummary } from '../types'
import { mergeContact, takContacts, takSummary } from './takData'

export const tak = $state({
  contacts: new Map<string, TakContact>(),
  summary: null as TakSummary | null,
  loaded: false,
  error: false,
})

export async function loadTak(hours = 24): Promise<void> {
  try {
    const [list, summary] = await Promise.all([takContacts(hours), takSummary(hours)])
    tak.contacts = new Map(list.map((c) => [c.node_id, c]))
    tak.summary = summary
    tak.loaded = true
    tak.error = false
  } catch {
    tak.error = true
  }
}

let refs = 0
let off: (() => void)[] = []

/** Sottoscrive gli aggiornamenti; piu' chiamate condividono le stesse sottoscrizioni (contatore). */
export function startTakLive(): () => void {
  if (refs++ === 0) {
    off = [
      onWsEvent('tak_contact', (m) => {
        tak.contacts = mergeContact(tak.contacts, m.contact as TakContact)
      }),
      onWsResync(() => void loadTak()),
    ]
  }
  let done = false
  return () => {
    if (done) return
    done = true
    if (--refs === 0) {
      for (const f of off) f()
      off = []
    }
  }
}
