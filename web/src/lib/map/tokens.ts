// Colori della mappa letti dai token CSS (nessun colore scritto a mano nei layer).
// Letti a ogni (ri)creazione dello stile, cosi' seguono il tema attivo.

export interface MapTokens {
  land: string
  water: string
  road: string
  label: string
  contactFresh: string
  contactRecent: string
  contactOld: string
  snrGood: string
  snrMid: string
  snrBad: string
  snrNone: string
  srcRadio: string
  srcMqtt: string
  srcBoth: string
  amber: string
  outline: string
  surfaceRaised: string
  accent: string
  ink: string
  inkMuted: string
}

/** Nome della variabile CSS per ogni chiave. */
export const TOKEN_VARS: Record<keyof MapTokens, string> = {
  land: '--map-land',
  water: '--map-water',
  road: '--map-road',
  label: '--map-label',
  contactFresh: '--contact-fresh',
  contactRecent: '--contact-recent',
  contactOld: '--contact-old',
  snrGood: '--snr-good',
  snrMid: '--snr-mid',
  snrBad: '--snr-bad',
  snrNone: '--snr-none',
  srcRadio: '--src-radio',
  srcMqtt: '--src-mqtt',
  srcBoth: '--src-both',
  amber: '--brand-amber',
  outline: '--marker-outline',
  surfaceRaised: '--surface-raised',
  accent: '--accent',
  ink: '--ink',
  inkMuted: '--ink-muted',
}

/** Valori dei token del tema scuro (uso: ambienti senza CSS, es. test, e valore di riserva). */
export const FALLBACK_TOKENS: MapTokens = {
  land: '#16253a',
  water: '#0f2c44',
  road: '#2c4262',
  label: '#9fb2cb',
  contactFresh: '#2fd4c0',
  contactRecent: '#f2d33f',
  contactOld: '#8497b0',
  snrGood: '#2fd4c0',
  snrMid: '#f2d33f',
  snrBad: '#ff7a59',
  snrNone: '#8497b0',
  srcRadio: '#4db8f2',
  srcMqtt: '#e08ec4',
  srcBoth: '#e8eef7',
  amber: '#f59e0b',
  outline: '#0b1220',
  surfaceRaised: '#182540',
  accent: '#4db8f2',
  ink: '#e8eef7',
  inkMuted: '#a3b3cb',
}

/** Legge i token con `getVar(nome)`; un valore vuoto cade sul valore di riserva. */
export function readTokens(getVar: (name: string) => string): MapTokens {
  const out = { ...FALLBACK_TOKENS }
  for (const k of Object.keys(TOKEN_VARS) as (keyof MapTokens)[]) {
    const v = getVar(TOKEN_VARS[k]).trim()
    if (v) out[k] = v
  }
  return out
}

/** Token del documento corrente. */
export function readDocumentTokens(): MapTokens {
  const cs = getComputedStyle(document.documentElement)
  return readTokens((n) => cs.getPropertyValue(n))
}

function parseHex(c: string): [number, number, number] | null {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(c.trim())
  if (!m) return null
  let h = m[1]
  if (h.length === 3) h = [...h].map((x) => x + x).join('')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

/** Miscela due colori esadecimali (t=0 -> a, t=1 -> b); se uno non e' esadecimale restituisce `a`. */
export function mix(a: string, b: string, t: number): string {
  const pa = parseHex(a)
  const pb = parseHex(b)
  if (!pa || !pb) return a
  const ch = pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0'))
  return `#${ch.join('')}`
}
