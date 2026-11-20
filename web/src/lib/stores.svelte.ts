import { SvelteMap } from 'svelte/reactivity'
import { loadFilter, saveFilter } from './filters'
import type { NodeFilter } from './filters'
import type { Message, Node, Radio, Status } from './types'

const MAX_MESSAGES = 500

export const app = $state({
  nodes: new SvelteMap<string, Node>(),
  messages: [] as Message[],
  status: null as Status | null,
  radios: [] as Radio[],
  filter: loadFilter(localStorage) as NodeFilter,
  selectedId: null as string | null,
})

export function upsertNodes(list: Node[]): void {
  for (const n of list) app.nodes.set(n.id, n)
}

export function addMessage(m: Message): void {
  if (app.messages.some((x) => x.key === m.key)) return
  app.messages.push(m)
  if (app.messages.length > MAX_MESSAGES) app.messages.splice(0, app.messages.length - MAX_MESSAGES)
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
