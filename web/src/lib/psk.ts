// Chiavi dei canali: generazione e classificazione (stessa regola di config_model.psk_kind).

export type KeyKind = 'none' | 'default' | 'custom' | 'invalid'

const DEFAULT_KEY = '1PG7OiApB1nwvP+rz05pAQ==' // chiave pubblica nota di Meshtastic

/** Nuova chiave casuale in base64 (16 = AES-128, 32 = AES-256). */
export function generatePsk(bytes: 16 | 32 = 32): string {
  const b = new Uint8Array(bytes)
  crypto.getRandomValues(b)
  let s = ''
  for (const x of b) s += String.fromCharCode(x)
  return btoa(s)
}

function decode(b64: string): string | null {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(b64) || b64.length % 4 !== 0) return null
  try {
    return atob(b64)
  } catch {
    return null
  }
}

/** "none" (nessuna cifratura), "default" (chiave pubblica e varianti), "custom", "invalid". */
export function keyKind(b64: string): KeyKind {
  const text = (b64 ?? '').trim()
  if (text === '') return 'none'
  const raw = decode(text)
  if (raw === null) return 'invalid'
  if (raw.length === 0) return 'none'
  if (raw.length === 1) return raw.charCodeAt(0) === 0 ? 'none' : 'default'
  if (raw.length === 16 && text === DEFAULT_KEY) return 'default'
  if (raw.length === 16 || raw.length === 32) return 'custom'
  return 'invalid'
}

/** Chiave che chiunque con l'app puo' usare (o assente). */
export function isWeak(kind: KeyKind | undefined): boolean {
  return kind === 'none' || kind === 'default'
}
