import { emitAuthRequired } from './api'
import type { Alert, CoveragePoint, CoverageSession, Message, MessageStatus, Node, Radio, Status, Traceroute } from './types'

export interface WSHandlers {
  nodes(n: Node[]): void
  message(m: Message): void
  status(s: Status): void
  radios(r: Radio[]): void
  alerts(a: Alert[]): void
  traceroute(t: Traceroute): void
  coverage(session: CoverageSession, point: CoveragePoint | null): void
  messageStatus(key: string, status: MessageStatus): void
  /** Chiamato a ogni riapertura dopo la prima: lo stato puo' essere vecchio (telefono in standby). */
  reconnected?(): void
}

const RECONNECT_MS = 3000

/** Apre /ws e si riconnette ogni 3 s. Restituisce una funzione per chiudere. */
export function connectWS(handlers: WSHandlers): () => void {
  let ws: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false
  let opened = false

  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}/ws`)
    ws.onopen = () => {
      if (opened) handlers.reconnected?.()
      opened = true
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'nodes') handlers.nodes(msg.nodes)
        else if (msg.type === 'message') handlers.message(msg.message)
        else if (msg.type === 'radios') handlers.radios(msg.radios)
        else if (msg.type === 'alerts') handlers.alerts(msg.alerts)
        else if (msg.type === 'traceroute') handlers.traceroute(msg.result)
        else if (msg.type === 'coverage') handlers.coverage(msg.session, msg.point ?? null)
        else if (msg.type === 'message_status') handlers.messageStatus(msg.key, msg.status)
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
