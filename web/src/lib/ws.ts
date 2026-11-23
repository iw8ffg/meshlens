import { emitAuthRequired } from './api'
import type { PredictionJob } from './prediction'
import type { SfJob, SfRouter } from './storeforward'
import type { ConfigJob, MapJob, UpdateJob, Alert, CoveragePoint, CoverageSession, CoverageTrackPoint, Message, MessageStatus, Node, Radio, Status, Traceroute, Waypoint } from './types'

export interface WSHandlers {
  nodes(n: Node[]): void
  message(m: Message): void
  status(s: Status): void
  radios(r: Radio[]): void
  alerts(a: Alert[]): void
  traceroute(t: Traceroute): void
  coverage(session: CoverageSession, point: CoveragePoint | null, trackPoint?: CoverageTrackPoint | null): void
  messageStatus(key: string, status: MessageStatus, error?: string | null, heardBy?: string[] | null): void
  waypoint?(w: Waypoint): void
  waypointDeleted?(id: number): void
  /** Conversazione letta da un altro dispositivo. */
  convRead?(key: string, time: number): void
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
/** Il server manda `status` ogni 5 s: dopo questo silenzio il socket e' considerato mezzo aperto. */
const STALE_MS = 20_000
const WATCHDOG_MS = 5000

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
  else if (m.type === 'message_status') {
    if (m.heard_by) h.messageStatus(m.key, m.status, m.error ?? null, m.heard_by)
    else h.messageStatus(m.key, m.status, m.error ?? null)
  }
  else if (m.type === 'waypoint') h.waypoint?.(m.waypoint)
  else if (m.type === 'waypoint_deleted') h.waypointDeleted?.(m.id)
  else if (m.type === 'conv_read') h.convRead?.(m.key, m.time)
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
  let lastRx = Date.now()

  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}/ws`)
    lastRx = Date.now()
    ws.onopen = () => {
      lastRx = Date.now()
      handlers.connection?.(true)
      if (opened) handlers.reconnected?.()
      opened = true
    }
    ws.onmessage = (ev) => {
      lastRx = Date.now()
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
      scheduleRetry()
    }
  }

  const scheduleRetry = () => {
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

  /** Socket mezzo aperto (nessun evento da troppo tempo): lo si abbandona e se ne apre uno nuovo. */
  const dropIfStale = () => {
    if (stopped || !ws || Date.now() - lastRx <= STALE_MS) return
    const old = ws
    ws = null
    old.onopen = old.onmessage = old.onclose = null
    try {
      old.close()
    } catch {
      /* gia' chiuso */
    }
    handlers.connection?.(false)
    open()
  }
  const onOnline = () => {
    if (timer) retryNow?.()
    else dropIfStale()
  }
  const onVisible = () => {
    if (document.visibilityState !== 'visible') return
    if (timer) retryNow?.()
    else dropIfStale()
  }
  if (typeof window.addEventListener === 'function') window.addEventListener('online', onOnline)
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') document.addEventListener('visibilitychange', onVisible)
  const watchdog = setInterval(dropIfStale, WATCHDOG_MS)
  open()

  return () => {
    stopped = true
    retryNow = null
    clearInterval(watchdog)
    if (typeof window.removeEventListener === 'function') window.removeEventListener('online', onOnline)
    if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function') document.removeEventListener('visibilitychange', onVisible)
    if (timer) clearTimeout(timer)
    ws?.close()
  }
}
