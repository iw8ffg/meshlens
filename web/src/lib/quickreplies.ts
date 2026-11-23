import { byteLength } from './chat'
import type { Node, Radio } from './types'

/** Limiti del server (contratto §2): massimo di messaggi rapidi e byte per messaggio. */
export const MAX_QUICK_REPLIES = 20
export const QUICK_REPLY_MAX_BYTES = 200
/** Variabili note dei messaggi rapidi (tra graffe nel testo). */
export const VARIABLES = ['batteria', 'posizione', 'ora'] as const
export type QuickVariable = (typeof VARIABLES)[number]

export type QuickReplyError = 'empty' | 'edges' | 'tooLong' | 'control' | 'duplicate'

/** Stesse regole del server: niente spazi agli estremi, 1..200 byte UTF-8, niente caratteri di controllo, niente doppioni. */
export function validateQuickReply(text: string, existing: string[]): QuickReplyError | null {
  if (text.length === 0) return 'empty'
  if (text !== text.trim()) return 'edges'
  if (byteLength(text) > QUICK_REPLY_MAX_BYTES) return 'tooLong'
  for (const ch of text) if (ch.charCodeAt(0) < 32) return 'control'
  if (existing.includes(text)) return 'duplicate'
  return null
}

const placeholder = (name: string) => `{${name}}`

/** Variabili note presenti nel testo (ognuna una volta, nell'ordine di `VARIABLES`). */
export function variablesIn(text: string): string[] {
  return VARIABLES.filter((v) => text.includes(placeholder(v)))
}

/** Vero se nel testo resta una variabile nota non sostituita. */
export function hasUnresolvedVariables(text: string): boolean {
  return variablesIn(text).length > 0
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/**
 * Sostituisce le variabili note. Una variabile che non si puo' risolvere (batteria sconosciuta,
 * posizione mancante, nodo ignoto) resta nel testo cosi' com'e' e finisce in `missing`: non viene
 * mai inviata un'invenzione. Sostituzione di tutte le occorrenze, non ricorsiva.
 */
export function expandVariables(
  text: string,
  ctx: { node: Pick<Node, 'battery' | 'lat' | 'lon'> | null; now: Date },
): { text: string; missing: string[] } {
  const values: Record<QuickVariable, string | null> = {
    batteria: ctx.node && ctx.node.battery !== null && ctx.node.battery !== undefined && Number.isFinite(ctx.node.battery) && ctx.node.battery >= 0 && ctx.node.battery <= 100 ? `${Math.round(ctx.node.battery)}%` : null,
    posizione:
      ctx.node && ctx.node.lat !== null && ctx.node.lat !== undefined && ctx.node.lon !== null && ctx.node.lon !== undefined && Number.isFinite(ctx.node.lat) && Number.isFinite(ctx.node.lon)
        ? `${ctx.node.lat.toFixed(5)}, ${ctx.node.lon.toFixed(5)}`
        : null,
    ora: `${pad2(ctx.now.getHours())}:${pad2(ctx.now.getMinutes())}`,
  }
  const missing: string[] = []
  // un solo passaggio sul testo originale: un valore sostituito non viene riesaminato
  const out = text.replace(/\{(batteria|posizione|ora)\}/g, (whole, name: QuickVariable) => {
    const v = values[name]
    if (v === null) {
      if (!missing.includes(name)) missing.push(name)
      return whole
    }
    return v
  })
  return { text: out, missing }
}

/** Id del nodo mittente: la radio scelta, oppure il nodo MQTT (o, in mancanza, la prima radio collegata). */
export function ownNodeId(via: string, radios: Radio[], mqttNodeId: string): string | null {
  if (via.startsWith('radio:')) {
    const id = via.slice('radio:'.length)
    return radios.find((r) => r.id === id)?.my_node_id ?? null
  }
  if (via === 'mqtt') {
    if (/^![0-9a-fA-F]{8}$/.test(mqttNodeId)) return mqttNodeId
    return radios.find((r) => r.state === 'connected' && r.my_node_id)?.my_node_id ?? null
  }
  return null
}

/** Testo del campo dopo aver inserito un messaggio rapido: campo vuoto → lo sostituisce, altrimenti lo accoda dopo uno spazio. */
export function insertReply(current: string, reply: string): string {
  if (current.trim() === '') return reply
  return /\s$/.test(current) ? current + reply : `${current} ${reply}`
}
