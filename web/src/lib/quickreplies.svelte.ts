// Stato dei messaggi rapidi (WP1, E10): elenco condiviso fra la scheda delle impostazioni e il compositore.
import { getJSON, send } from './api'
import type { AppSettings } from './settings'

export const quick = $state({ list: [] as string[], loaded: false, error: false })

let inflight: Promise<void> | null = null

/** Legge l'elenco dal server (una volta; `force` lo rilegge). Un errore non lascia l'elenco a meta': `quick.error` e riprova possibile. */
export function loadQuickReplies(force = false): Promise<void> {
  if (quick.loaded && !force) return Promise.resolve()
  if (inflight) return inflight
  inflight = getJSON<AppSettings>('/settings')
    .then((s) => {
      quick.list = Array.isArray(s.quick_replies) ? [...s.quick_replies] : []
      quick.loaded = true
      quick.error = false
    })
    .catch(() => {
      quick.error = true
    })
    .finally(() => {
      inflight = null
    })
  return inflight
}

/** Salva l'elenco; l'elenco locale diventa quello restituito dal server. Un errore (anche di validazione) si propaga gia' tradotto. */
export async function saveQuickReplies(list: string[]): Promise<void> {
  const s = await send<AppSettings>('PUT', '/settings', { quick_replies: list })
  quick.list = Array.isArray(s?.quick_replies) ? [...s.quick_replies] : [...list]
  quick.loaded = true
  quick.error = false
}
