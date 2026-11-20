import { SvelteMap } from 'svelte/reactivity'
import { loadFilter, saveFilter } from './filters'
import type { NodeFilter } from './filters'
import { MAX_REPLACED, insertMessage, mergeRadioMessages, pruneSet } from './chat'
import type { Message, MessageStatus, Node, Radio, Status } from './types'

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
})

export function upsertNodes(list: Node[]): void {
  for (const n of list) app.nodes.set(n.id, n)
}

const replaced = new Set<string>()

export function addMessage(m: Message): void {
  if (m.radio_id) {
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

export function setStatus(s: Status): void {
  app.status = s
}

export function persistFilter(): void {
  const { countries, maxAgeH, sources, text } = app.filter
  saveFilter(localStorage, { countries: [...countries], maxAgeH, sources: [...sources], text })
}
