import { emitAuthRequired } from './api'
import type { Message, Node, Status } from './types'

export interface WSHandlers {
  nodes(n: Node[]): void
  message(m: Message): void
  status(s: Status): void
}

const RECONNECT_MS = 3000

/** Apre /ws e si riconnette ogni 3 s. Restituisce una funzione per chiudere. */
export function connectWS(handlers: WSHandlers): () => void {
  let ws: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false

  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}/ws`)
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'nodes') handlers.nodes(msg.nodes)
        else if (msg.type === 'message') handlers.message(msg.message)
        else if (msg.type === 'status') handlers.status({ mqtt: msg.mqtt })
      } catch {
        /* messaggio malformato: ignorato */
      }
    }
    ws.onclose = (ev) => {
      ws = null
      if (stopped) return
      if (ev.code === 4401) {
        emitAuthRequired()
        return // niente riconnessione: serve prima l'accesso
      }
      timer = setTimeout(open, RECONNECT_MS)
    }
  }
  open()

  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
    ws?.close()
  }
}
