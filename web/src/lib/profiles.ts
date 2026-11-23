// Profili di configurazione (WP4): chiamate HTTP e funzioni pure per l'interfaccia.
// I profili non contengono mai segreti ne' parametri legati all'hardware (li toglie il server).
import { getJSON, send } from './api'
import { t, type MsgKey } from './i18n/index.svelte'
import type { ConfigProfile, ConfigProfileDetail, ProfileCompare, ProfilePreview } from './types'

export const PROFILE_FORMAT = 'meshlens-profile'

/** Sezioni copiabili, come profiles.allowed_sections del server (mai config.security). */
export const PROFILE_SECTIONS: readonly string[] = [
  ...['device', 'position', 'power', 'network', 'display', 'lora', 'bluetooth'].map((s) => `config.${s}`),
  ...['mqtt', 'serial', 'external_notification', 'store_forward', 'range_test', 'telemetry', 'canned_message', 'audio',
    'remote_hardware', 'neighbor_info', 'detection_sensor', 'ambient_lighting', 'paxcounter', 'traffic_management'].map(
    (s) => `module_config.${s}`,
  ),
]

/** Sezioni di una lettura salvata ("lora", "mqtt") presenti tra quelle copiabili. */
export function readSections(saved: string[]): string[] {
  const have = new Set(saved)
  return PROFILE_SECTIONS.filter((s) => have.has(s.split('.')[1]))
}

export const listProfiles = () => getJSON<ConfigProfile[]>('/profiles')
export const getProfile = (id: number) => getJSON<ConfigProfileDetail>(`/profiles/${id}`)
export const saveProfile = (body: { node_id: string; name: string; sections?: string[] | null; notes?: string | null }) =>
  send<ConfigProfileDetail>('POST', '/profiles', body)
export const renameProfile = (id: number, body: { name?: string; notes?: string | null }) =>
  send<ConfigProfile>('PUT', `/profiles/${id}`, body)
export const deleteProfile = (id: number) => send<{ ok: boolean }>('DELETE', `/profiles/${id}`, { confirm: true })
export const previewProfile = (id: number, nodeId: string, sections: string[] | null) =>
  send<ProfilePreview>('POST', `/profiles/${id}/preview`, { node_id: nodeId, sections })
export const importProfile = (doc: Record<string, unknown>, name?: string | null) =>
  send<ConfigProfileDetail>('POST', '/profiles/import', { profile: doc, name: name ?? null })
export const exportProfileUrl = (id: number) => `/api/profiles/${id}/export`

export function compareProfiles(q: { a?: string; profile?: number; b: string; sections?: string[] }): Promise<ProfileCompare> {
  const p = new URLSearchParams({ b: q.b })
  if (q.a !== undefined) p.set('a', q.a)
  if (q.profile !== undefined) p.set('profile', String(q.profile))
  if (q.sections?.length) p.set('sections', q.sections.join(','))
  return getJSON<ProfileCompare>(`/profiles/compare?${p.toString()}`)
}

/** Sezioni raggruppate: configurazione e moduli (il resto si scarta). */
export function sectionGroups(sections: string[]): { config: string[]; module_config: string[] } {
  return {
    config: sections.filter((s) => s.startsWith('config.')),
    module_config: sections.filter((s) => s.startsWith('module_config.')),
  }
}

/** "config.lora" -> "LoRa" (area profiles), altrimenti il nome della sezione. */
export function sectionLabel(s: string): string {
  const name = s.split('.').slice(1).join('.') || s
  const key = `profiles.section.${name}`
  const text = t(key as MsgKey)
  return text === key ? name : text
}

/** Legge un file di profilo; l'errore porta come messaggio una chiave i18n (area profiles). */
export function parseProfileFile(text: string): Record<string, unknown> {
  let doc: unknown
  try {
    doc = JSON.parse(text)
  } catch {
    throw new Error('profiles.err.badJson')
  }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc) || (doc as Record<string, unknown>).format !== PROFILE_FORMAT)
    throw new Error('profiles.err.badFormat')
  return doc as Record<string, unknown>
}
