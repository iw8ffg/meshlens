// Messaggi predefiniti (canned) delle radio con tastiera/rotella: regole e chiamate HTTP.
// Stesse regole di config_model.join_canned (il server rivalida prima di toccare la radio).
import { getJSON, send } from './api'
import { hasUnresolvedVariables } from './quickreplies'
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

/** Risposte rapide -> (le radio non espandono {batteria}, {posizione}, {ora}) -> messaggi predefiniti: salta quelle con "|" o variabili, si ferma al limite di byte. */
export function quickToCanned(quick: string[]): { out: string[]; skippedVars: number; skippedPipe: number; truncated: boolean } {
  const out: string[] = []
  let skippedVars = 0
  let skippedPipe = 0
  let truncated = false
  for (const q of quick) {
    if (q.includes(CANNED_SEP)) {
      skippedPipe++
      continue
    }
    if (hasUnresolvedVariables(q)) {
      skippedVars++
      continue
    }
    if (cannedBytes([...out, q]) > CANNED_MAX_BYTES) {
      truncated = true
      break
    }
    out.push(q)
  }
  return { out, skippedVars, skippedPipe, truncated }
}
