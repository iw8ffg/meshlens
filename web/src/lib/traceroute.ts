import type { Traceroute } from './types'

/** Un `pending` non declassa mai un esito finale gia' noto con lo stesso id. */
export function shouldStore(stored: Traceroute | undefined, incoming: Traceroute): boolean {
  return !(stored && stored.id === incoming.id && stored.status !== 'pending' && incoming.status === 'pending')
}

/** Per uno storico in ordine di tempo decrescente senza `route_changed` (calcolo locale su
 * `route`): vero se il percorso di una riga `ok` differisce dall'`ok` precedente (piu' vecchio).
 * Le righe non `ok` e il primo `ok` non sono mai "cambiati". */
export function markChangedRoutes(items: Traceroute[]): boolean[] {
  const out = items.map(() => false)
  let newer = -1 // indice dell'ultimo ok piu' recente visto, in attesa del predecessore
  for (let i = 0; i < items.length; i++) {
    const it = items[i]
    if (it.status !== 'ok' || it.route == null) continue
    if (newer >= 0) out[newer] = items[newer].route !== it.route
    newer = i
  }
  return out
}

/** Inserisce un esito nello storico: sostituisce la voce con lo stesso id, altrimenti la mette in cima. */
export function mergeHistory(history: Traceroute[], t: Traceroute): Traceroute[] {
  const i = history.findIndex((h) => h.id === t.id)
  if (i < 0) return [t, ...history]
  // confronto per valore: lo storico e' un proxy $state, l'identita' non coincide mai
  const h = history[i]
  if (h.status === t.status && h.error === t.error && h.forward.length === t.forward.length
      && h.back.length === t.back.length) return history
  return history.map((h, j) => (j === i ? t : h))
}
