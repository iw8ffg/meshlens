import type { NodeFilter } from './filters'
import type { Message, Node, Status } from './types'

const MAX_MESSAGES = 500

export const app = $state({
  nodes: new Map<string, Node>(),
  messages: [] as Message[],
  status: null as Status | null,
  filter: { countries: [], maxAgeH: null, sources: [], text: '' } as NodeFilter,
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

export function setStatus(s: Status): void {
  app.status = s
}
