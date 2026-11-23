/**
 * Eventi WebSocket della 1.6 (contratto §7): i pacchetti di lavoro registrano qui i gestori dei
 * propri tipi (`sensor_event`, `tak_contact`, ...) senza toccare `ws.ts` né `App.svelte`.
 */

export type WsExtHandler = (msg: Record<string, unknown>) => void

/** Tipi gestiti dal nucleo (`dispatch` di ws.ts): non si registrano qui. */
export const CORE_WS_TYPES: readonly string[] = [
  'nodes', 'message', 'radios', 'alerts', 'traceroute', 'coverage', 'message_status',
  'waypoint', 'waypoint_deleted', 'conv_read', 'config_job', 'map_job', 'update_job',
  'prediction_job', 'sf_job', 'sf_routers', 'status', 'resync',
]

const handlers = new Map<string, Set<WsExtHandler>>()
const resyncHandlers = new Set<() => void>()

/** Registra un gestore per un tipo nuovo; restituisce la funzione che lo rimuove. */
export function onWsEvent(type: string, fn: WsExtHandler): () => void {
  if (CORE_WS_TYPES.includes(type)) throw new Error(`Tipo WebSocket del nucleo: ${type}`)
  let set = handlers.get(type)
  if (!set) handlers.set(type, (set = new Set()))
  set.add(fn)
  return () => {
    set.delete(fn)
    if (set.size === 0 && handlers.get(type) === set) handlers.delete(type)
  }
}

/** Passa un messaggio ai gestori del suo tipo; true se almeno uno l'ha ricevuto. */
export function dispatchExt(msg: Record<string, unknown>): boolean {
  const set = typeof msg.type === 'string' ? handlers.get(msg.type) : undefined
  if (!set || set.size === 0) return false
  for (const fn of [...set]) {
    try {
      fn(msg)
    } catch (e) {
      console.error('Gestore WebSocket fallito', e)
    }
  }
  return true
}

/** Chiamata dopo un resync o una riconnessione (i dati vanno ricaricati). */
export function onWsResync(fn: () => void): () => void {
  resyncHandlers.add(fn)
  return () => {
    resyncHandlers.delete(fn)
  }
}

/** Avvisa i gestori di resync (la chiama App.svelte). */
export function notifyWsResync(): void {
  for (const fn of [...resyncHandlers]) {
    try {
      fn()
    } catch (e) {
      console.error('Gestore di resync fallito', e)
    }
  }
}
