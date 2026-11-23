// Messaggi predefiniti (canned) delle radio con tastiera/rotella: regole e chiamate HTTP.
// Stesse regole di config_model.join_canned (il server rivalida prima di toccare la radio).
import { getJSON, send } from './api'
import type { MsgKey } from './i18n/index.svelte'
import type { CannedMessages } from './types'

export const CANNED_MAX_BYTES = 200
export const CANNED_SEP = '|'

const enc = new TextEncoder()

/** Byte UTF-8 dei messaggi uniti con "|" (come li riceve la radio). */
export function cannedBytes(list: string[]): number {
  return enc.encode(list.map((m) => m.trim()).join(CANNED_SEP)).length
}

/** Chiave dell'errore (area canned) o null se l'elenco si puo' scrivere. */
export function cannedError(list: string[]): MsgKey | null {
  if (list.length === 0) return 'canned.err.empty' as MsgKey
  const items = list.map((m) => m.trim())
  if (items.some((m) => m === '')) return 'canned.err.blank' as MsgKey
  if (items.some((m) => m.includes(CANNED_SEP))) return 'canned.err.pipe' as MsgKey
  // eslint-disable-next-line no-control-regex
  if (items.some((m) => /[\u0000-\u001f]/.test(m))) return 'canned.err.control' as MsgKey
  if (cannedBytes(items) > CANNED_MAX_BYTES) return 'canned.err.tooLong' as MsgKey
  return null
}

const cannedPath = (nodeId: string) => `/config/${encodeURIComponent(nodeId)}/canned`

export const getCanned = (nodeId: string, radioId?: string) =>
  getJSON<CannedMessages>(cannedPath(nodeId) + (radioId ? `?radio_id=${encodeURIComponent(radioId)}` : ''))

export const putCanned = (nodeId: string, messages: string[], radioId?: string) =>
  send<CannedMessages>('PUT', cannedPath(nodeId), { messages, radio_id: radioId ?? null })
