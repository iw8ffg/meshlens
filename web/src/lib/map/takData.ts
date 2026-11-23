// Dati ATAK nel browser (E16): richieste HTTP e funzioni pure. Le posizioni e i nominativi sono
// dati sensibili: arrivano solo da /api/tak/*.
import { getJSON } from '../api'
import { tak as itTak } from '../i18n/it/tak'
import type { MsgKey } from '../i18n/index.svelte'
import type { TakContact, TakSummary } from '../types'

export const takContacts = (hours = 24) => getJSON<TakContact[]>(`/tak/contacts?hours=${hours}`)
export const takSummary = (hours = 24) => getJSON<TakSummary>(`/tak/summary?hours=${hours}`)

/** Nuova Map con `c`; un contatto piu' vecchio di quello presente si ignora. La Map in ingresso non cambia. */
export function mergeContact(list: Map<string, TakContact>, c: TakContact): Map<string, TakContact> {
  const next = new Map(list)
  const cur = next.get(c.node_id)
  if (cur && c.time < cur.time) return next
  next.set(c.node_id, c)
  return next
}

function nameKey(prefix: 'tak.role.' | 'tak.team.', name: string | null): MsgKey | null {
  if (!name) return null
  const key = `${prefix}${name}`
  return key in itTak ? (key as MsgKey) : null
}

/** Chiave del testo del ruolo ATAK, o null (si mostra il nome grezzo). */
export const takRoleKey = (role: string | null): MsgKey | null => nameKey('tak.role.', role)
export const takTeamKey = (team: string | null): MsgKey | null => nameKey('tak.team.', team)

export const contactName = (c: TakContact, nodeName: (id: string) => string): string => c.callsign ?? nodeName(c.node_id)
