// Stato live delle automazioni (WP5): bersagli dei traceroute periodici e stato del bot,
// aggiornati dagli eventi WebSocket `trace_targets` e `bot` (wsext) e ricaricati dopo un resync.
import { getJSON } from './api'
import type { BotInfo, BotState } from './bot'
import type { TraceTargetsResponse } from './tracesched'
import type { TraceTarget } from './types'
import { onWsEvent, onWsResync } from './wsext'

export const automation = $state({
  targets: [] as TraceTarget[],
  autoEnabled: false,
  maxPerHour: 6,
  bot: null as BotState | null,
  loaded: false,
})

export async function loadAutomation(): Promise<void> {
  const [tr, bot] = await Promise.allSettled([
    getJSON<TraceTargetsResponse>('/trace-targets'),
    getJSON<BotInfo>('/bot'),
  ])
  if (tr.status === 'fulfilled') {
    automation.targets = tr.value.targets
    automation.autoEnabled = tr.value.enabled
    automation.maxPerHour = tr.value.max_per_hour
  }
  if (bot.status === 'fulfilled') automation.bot = bot.value.status
  automation.loaded = true
}

/** Applica un elenco di bersagli arrivato da una risposta o da un evento. */
export function setTargets(targets: TraceTarget[]): void {
  automation.targets = targets
}

/** Registra i gestori live e carica lo stato; restituisce la funzione di pulizia. */
export function startAutomation(): () => void {
  const offs = [
    onWsEvent('trace_targets', (m) => {
      if (Array.isArray(m.targets)) automation.targets = m.targets as TraceTarget[]
    }),
    onWsEvent('bot', (m) => {
      if (m.status && typeof m.status === 'object') automation.bot = m.status as BotState
    }),
    onWsResync(() => void loadAutomation()),
  ]
  void loadAutomation()
  return () => offs.forEach((off) => off())
}
