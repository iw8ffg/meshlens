import type { Traceroute } from './types'

/** Un `pending` non declassa mai un esito finale gia' noto con lo stesso id. */
export function shouldStore(stored: Traceroute | undefined, incoming: Traceroute): boolean {
  return !(stored && stored.id === incoming.id && stored.status !== 'pending' && incoming.status === 'pending')
}

/** Inserisce un esito nello storico: sostituisce la voce con lo stesso id, altrimenti la mette in cima. */
export function mergeHistory(history: Traceroute[], t: Traceroute): Traceroute[] {
  const i = history.findIndex((h) => h.id === t.id)
  if (i < 0) return [t, ...history]
  if (history[i] === t) return history
  return history.map((h, j) => (j === i ? t : h))
}
