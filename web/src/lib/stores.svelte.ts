import { SvelteMap } from 'svelte/reactivity'
import { loadFilter, saveFilter, loadFeedFilter, saveFeedFilter } from './filters'
import type { NodeFilter, FeedFilter } from './filters'
import { MAX_REPLACED, insertMessage, removeByKey, mergeRadioMessages, pruneSet } from './chat'
import { shouldStore } from './traceroute'
import { appendTrackPoint, upsertPoint } from './coverage'
import { updateStatus } from './api'
import { shouldReloadStatus } from './update'
import { saveView } from './viewstate'
import type { Bbox, ConfigJob, MapJob, UpdateJob, UpdateStatus, Alert, CoverageDetail, CoveragePoint, CoverageSession, CoverageTrackPoint, Message, MessageStatus, Node, Radio, Status, Traceroute } from './types'

const MAX_MESSAGES = 500

export const app = $state({
  nodes: new SvelteMap<string, Node>(),
  messages: [] as Message[],
  radioMessages: [] as Message[],
  status: null as Status | null,
  radios: [] as Radio[],
  filter: loadFilter(localStorage) as NodeFilter,
  feedFilter: loadFeedFilter(localStorage) as FeedFilter,
  selectedId: null as string | null,
  alerts: [] as Alert[],
  traceroutes: new SvelteMap<string, Traceroute>(),
  reconnects: 0, // contatore: cresce a ogni riconnessione del WebSocket
})

// Apertura di una conversazione dall'esterno (es. «Messaggio diretto»): callback, nessuno stato reattivo.
// Se la chat non e' ancora montata la richiesta resta in attesa e la ritira alla creazione.
const chatBridge = { open: null as ((key: string) => void) | null, pending: null as string | null }

export function openChat(key: string): void {
  if (chatBridge.open) chatBridge.open(key)
  else chatBridge.pending = key
}

/** La chat si registra alla creazione; restituisce la richiesta in attesa e la funzione di annullamento. */
export function attachChat(open: (key: string) => void): { pending: string | null; detach: () => void } {
  const pending = chatBridge.pending
  chatBridge.pending = null
  chatBridge.open = open
  return {
    pending,
    detach: () => {
      if (chatBridge.open === open) chatBridge.open = null
    },
  }
}

export const coverage = $state({
  sessions: [] as CoverageSession[],
  openId: null as number | null,
  detail: null as CoverageDetail | null,
  /** Ultimo punto della sessione attiva (indipendente dalla sessione aperta). */
  last: null as { id: number; snr: number | null; time: number } | null,
})

export function setCoverageSessions(list: CoverageSession[]): void {
  coverage.sessions = list
}

/** Aggiornamento dal WebSocket: sostituisce il riepilogo e aggiunge il punto al dettaglio aperto. */
export function applyCoverage(
  session: CoverageSession,
  point: CoveragePoint | null,
  trackPoint: CoverageTrackPoint | null = null,
): void {
  const i = coverage.sessions.findIndex((s) => s.id === session.id)
  if (i >= 0) coverage.sessions[i] = session
  else coverage.sessions.unshift(session)
  if (point && session.ended === null) coverage.last = { id: session.id, snr: point.snr, time: point.time }
  if (session.id === coverage.openId && coverage.detail?.id === session.id) {
    const d = coverage.detail
    coverage.detail = {
      ...d,
      ...session,
      points: point ? upsertPoint(d.points, point) : d.points,
      track: trackPoint ? appendTrackPoint(d.track, trackPoint) : d.track,
    }
  }
}

export function upsertNodes(list: Node[]): void {
  for (const n of list) app.nodes.set(n.id, n)
}

const replaced = new Set<string>()

export function addMessage(m: Message): void {
  if (m.radio_id) {
    removeByKey(app.messages, m.key)
    mergeRadioMessages(app.radioMessages, [m], replaced)
    return
  }
  insertMessage(app.messages, m, replaced)
  pruneSet(replaced, MAX_REPLACED)
  if (app.messages.length > MAX_MESSAGES) app.messages.splice(0, app.messages.length - MAX_MESSAGES)
}

/** Storico radio (piu' recenti per primi o in qualunque ordine): unito alla lista senza duplicati. */
export function addRadioHistory(list: Message[]): void {
  mergeRadioMessages(app.radioMessages, list, replaced)
}

export function setMessageStatus(key: string, status: MessageStatus): void {
  const m = app.radioMessages.find((x) => x.key === key) ?? app.messages.find((x) => x.key === key)
  if (m) m.status = status
}

export function setRadios(list: Radio[]): void {
  app.radios = list
}

export function setAlerts(list: Alert[]): void {
  app.alerts = list
}

/** Ultimo traceroute per nodo di destinazione. */
export function setTraceroute(t: Traceroute): void {
  if (shouldStore(app.traceroutes.get(t.target_id), t)) app.traceroutes.set(t.target_id, t)
}

export function setStatus(s: Status): void {
  app.status = s
}

export function persistFilter(): void {
  const { countries, maxAgeH, sources, text, links, favorites } = app.filter
  saveFilter(localStorage, { countries: [...countries], maxAgeH, sources: [...sources], text, links, favorites })
}

export function persistFeedFilter(): void {
  const { countries, includeUnknown } = app.feedFilter
  saveFeedFilter(localStorage, { countries: [...countries], includeUnknown })
}

/** Lavori di configurazione, aggiornati dal WebSocket. */
export const configJobs = new SvelteMap<number, ConfigJob>()

export function setConfigJob(j: ConfigJob): void {
  configJobs.set(j.id, j)
}

/** Pannello "Configura" aperto: nodo e radio preferita (null = scelta automatica). */
export const configUi = $state({ target: null as { nodeId: string; radioId: string | null; tab: string | null } | null })

export function openConfig(nodeId: string, radioId: string | null = null, tab: string | null = null): void {
  configUi.target = { nodeId, radioId, tab }
}

/** Mappe offline: lavoro in corso (WebSocket), contatore di ricarica e area visibile. */
export const maps = $state({
  job: null as MapJob | null,
  /** Cresce quando cambia modalita', elenco mappe o fine download: MapView e pannello ricaricano. */
  version: 0,
  /** Area inquadrata dalla mappa, aggiornata a fine movimento. */
  bounds: null as Bbox | null,
})

export function bumpMaps(): void {
  maps.version++
}

/** Aggiornamento dal WebSocket; a download riuscito la mappa ricarica stile e elenco. */
export function setMapJob(j: MapJob): void {
  const prev = maps.job
  maps.job = j
  const finished = j.status === 'done' && !(prev && prev.id === j.id && prev.status === 'done')
  if (finished) maps.version++
}

/** Aggiornamenti: ultimo stato noto (banner e impostazioni) e lavoro di download (WebSocket). */
export const updates = $state({
  status: null as UpdateStatus | null,
  job: null as UpdateJob | null,
})

export function setUpdateStatus(s: UpdateStatus): void {
  updates.status = s
  updates.job = s.job
}

export function setUpdateJob(j: UpdateJob): void {
  const reload = shouldReloadStatus(updates.job, j)
  updates.job = j
  // a download completato il server calcola can_install: rileggi lo stato (WebSocket o polling)
  if (reload) {
    updateStatus()
      .then(setUpdateStatus)
      .catch(() => {})
  }
}

/** Ultima conversazione aperta in Messaggi: si riapre al prossimo avvio. */
export function rememberConv(key: string): void {
  saveView(localStorage, { conv: key })
}
