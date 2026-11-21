// Bozze dei messaggi per conversazione (localStorage `meshlens.drafts`, per dispositivo).
export const DRAFTS_KEY = 'meshlens.drafts'
const MAX_DRAFTS = 50

type DraftStorage = Pick<Storage, 'getItem' | 'setItem'>

function read(storage: DraftStorage): Record<string, string> {
  try {
    const o = JSON.parse(storage.getItem(DRAFTS_KEY) ?? 'null')
    if (!o || o.v !== 1 || !o.drafts || typeof o.drafts !== 'object') return {}
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(o.drafts)) if (typeof v === 'string' && v !== '') out[k] = v
    return out
  } catch {
    return {}
  }
}

export function loadDraft(storage: DraftStorage, conv: string): string {
  return read(storage)[conv] ?? ''
}

/** Salva la bozza (il testo vuoto la rimuove); oltre 50 voci si tolgono le più vecchie. */
export function saveDraft(storage: DraftStorage, conv: string, text: string): void {
  const drafts = read(storage)
  // si rimuove e si reinserisce: la voce modificata diventa la più recente
  delete drafts[conv]
  if (text !== '') drafts[conv] = text
  const keys = Object.keys(drafts)
  for (const k of keys.slice(0, Math.max(0, keys.length - MAX_DRAFTS))) delete drafts[k]
  try {
    storage.setItem(DRAFTS_KEY, JSON.stringify({ v: 1, drafts }))
  } catch {
    /* spazio esaurito o storage non disponibile: la bozza resta solo in memoria */
  }
}
