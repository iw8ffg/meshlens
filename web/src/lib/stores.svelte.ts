import { SvelteMap } from 'svelte/reactivity'
import { loadFilter, saveFilter } from './filters'
import type { NodeFilter } from './filters'
import { MAX_REPLACED, insertMessage, removeByKey, mergeRadioMessages, pruneSet } from './chat'
import { shouldStore } from './traceroute'
import type { Alert, CoverageDetail, CoveragePoint, CoverageSession, Message, MessageStatus, Node, Radio, Status, Traceroute } from './types'

const MAX_MESSAGES = 500

export const app = $state({
  nodes: new SvelteMap<string, Node>(),
  messages: [] as Message[],
  radioMessages: [] as Message[],
  status: null as Status | null,
  radios: [] as Radio[],
  filter: loadFilter(localStorage) as NodeFilter,
  selectedId: null as string | null,
  chatConv: null as string | null,
  alerts: [] as Alert[],
  traceroutes: new SvelteMap<string, Traceroute>(),
  reconnects: 0, // contatore: cresce a ogni riconnessione del WebSocket
})

export const coverage = $state({
  sessions: [] as CoverageSession[],
  openId: null as number | null,
  detail: null as CoverageDetail | null,
})

export function setCoverageSessions(list: CoverageSession[]): void {
  coverage.sessions = list
}

/** Aggiornamento dal WebSocket: sostituisce il riepilogo e aggiunge il punto al dettaglio aperto. */
export function applyCoverage(session: CoverageSession, point: CoveragePoint | null): void {
  const i = coverage.sessions.findIndex((s) => s.id === session.id)
  if (i >= 0) coverage.sessions[i] = session
  else coverage.sessions.unshift(session)
  if (session.id === coverage.openId && coverage.detail?.id === session.id) {
    const d = coverage.detail
    coverage.detail = { ...d, ...session, points: point ? [...d.points, point] : d.points }
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
  const { countries, maxAgeH, sources, text, links } = app.filter
  saveFilter(localStorage, { countries: [...countries], maxAgeH, sources: [...sources], text, links })
}
