// Stato degli strati della mappa (E5): chiave propria `meshlens.layers`, versione 1. Non sta in
// `viewstate.ts` (il suo test confronta l'intero ViewState predefinito). Ogni campo non valido
// torna al predefinito (spento), come fa loadView.

export const LAYERS_KEY = 'meshlens.layers'
export type LayerKey = 'precision' | 'heat' | 'infra' | 'linkLabels' | 'tak'
export type LayerState = Record<LayerKey, boolean>
/** Ordine di visualizzazione nel pannello. */
export const LAYER_KEYS: readonly LayerKey[] = ['precision', 'heat', 'infra', 'linkLabels', 'tak']

export function defaultLayers(): LayerState {
  return { precision: false, heat: false, infra: false, linkLabels: false, tak: false }
}

type ReadStorage = Pick<Storage, 'getItem'>
type WriteStorage = Pick<Storage, 'getItem' | 'setItem'>

export function loadLayers(storage: ReadStorage | null): LayerState {
  const out = defaultLayers()
  if (!storage) return out
  try {
    const raw = storage.getItem(LAYERS_KEY)
    if (!raw) return out
    const o = JSON.parse(raw) as Record<string, unknown> | null
    if (!o || typeof o !== 'object' || o.v !== 1) return out
    for (const k of LAYER_KEYS) if (o[k] === true) out[k] = true
  } catch {
    // contenuto rotto: predefiniti
  }
  return out
}

/** Unisce `patch` allo stato salvato; gli errori di scrittura si ignorano. */
export function saveLayers(storage: WriteStorage | null, patch: Partial<LayerState>): void {
  if (!storage) return
  try {
    const merged = { ...loadLayers(storage), ...patch }
    storage.setItem(LAYERS_KEY, JSON.stringify({ v: 1, ...merged }))
  } catch {
    // quota piena o accesso negato: lo stato resta valido in memoria
  }
}
