import { emitAuthRequired } from './api'
import type { PredictionJob } from './prediction'
import type { SfJob, SfRouter } from './storeforward'
import type { ConfigJob, MapJob, UpdateJob, Alert, CoveragePoint, CoverageSession, CoverageTrackPoint, Message, MessageStatus, Node, Radio, Status, Traceroute } from './types'

export interface WSHandlers {
  nodes(n: Node[]): void
  message(m: Message): void
  status(s: Status): void
  radios(r: Radio[]): void
  alerts(a: Alert[]): void
  traceroute(t: Traceroute): void
  coverage(session: CoverageSession, point: CoveragePoint | null, trackPoint?: CoverageTrackPoint | null): void
  messageStatus(key: string, status: MessageStatus): void
  configJob?(job: ConfigJob): void
  mapJob?(job: MapJob): void
  updateJob?(job: UpdateJob): void
  prediction_job?(job: PredictionJob): void
  sf_job?(job: SfJob): void
  sf_routers?(routers: SfRouter[]): void
  /** Chiamato a ogni riapertura dopo la prima: lo stato puo' essere vecchio (telefono in standby). */
  reconnected?(): void
  /** Il server ha scartato eventi (coda piena): ricaricare i dati. */
  resync?(): void
  /** true a ogni apertura, false a ogni chiusura imprevista (non 4401, non voluta). */
  connection?(online: boolean): void
  /** Chiusura 4401: serve un nuovo accesso; lo stato di connessione va azzerato. */
  authLost?(): void
}

const RECONNECT_MS = 3000

let retryNow: (() => void) | null = null

/** Se un tentativo e' in attesa, lo anticipa; altrimenti non fa nulla. */
export function reconnectNow(): void {
  retryNow?.()
}

/** Smista un messaggio del WebSocket verso l'handler giusto; tipi ignoti o non-oggetti: nessun effetto. */
export function dispatch(msg: unknown, h: WSHandlers): void {
  if (msg === null || typeof msg !== 'object') return
  const m = msg as Record<string, any>
  if (m.type === 'nodes') h.nodes(m.nodes)
  else if (m.type === 'message') h.message(m.message)
  else if (m.type === 'radios') h.radios(m.radios)
  else if (m.type === 'alerts') h.alerts(m.alerts)
  else if (m.type === 'traceroute') h.traceroute(m.result)
  else if (m.type === 'coverage') h.coverage(m.session, m.point ?? null, m.track_point ?? null)
  else if (m.type === 'message_status') h.messageStatus(m.key, m.status)
  else if (m.type === 'config_job') h.configJob?.(m.job)
  else if (m.type === 'map_job') h.mapJob?.(m.job)
  else if (m.type === 'update_job') h.updateJob?.(m.job)
  else if (m.type === 'prediction_job') h.prediction_job?.(m.job)
  else if (m.type === 'sf_job') h.sf_job?.(m.job)
  else if (m.type === 'sf_routers') h.sf_routers?.(m.routers)
  else if (m.type === 'status') h.status({ mqtt: m.mqtt })
  else if (m.type === 'resync') h.resync?.()
}

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
      handlers.connection?.(true)
      if (opened) handlers.reconnected?.()
      opened = true
    }
    ws.onmessage = (ev) => {
      try {
        dispatch(JSON.parse(ev.data as string), handlers)
      } catch {
        /* messaggio malformato: ignorato */
      }
    }
    ws.onclose = (ev) => {
      ws = null
      if (stopped) return
      if (ev.code === 4401) {
        handlers.authLost?.()
        emitAuthRequired()
        return // niente riconnessione: serve prima l'accesso
      }
      handlers.connection?.(false)
      timer = setTimeout(() => {
        timer = null
        retryNow = null
        open()
      }, RECONNECT_MS)
      retryNow = () => {
        if (!timer) return
        clearTimeout(timer)
        timer = null
        retryNow = null
        open()
      }
    }
  }
  open()

  return () => {
    stopped = true
    retryNow = null
    if (timer) clearTimeout(timer)
    ws?.close()
  }
}
