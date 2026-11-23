// Sensori (E9): eventi del Detection Sensor di un nodo e serie del Paxcounter. Solo presentazione.
import { getJSON } from './api'
import type { Pt } from './chart'
import { t } from './i18n/index.svelte'
import type { MetricsResponse, SensorEvent } from './types'

export const sensorEvents = (id: string, hours = 168, limit = 200) =>
  getJSON<SensorEvent[]>(`/nodes/${encodeURIComponent(id)}/sensor-events?hours=${hours}&limit=${limit}`)

const toPts = (s: [number, number][] | undefined): Pt[] => (s ?? []).map(([time, v]) => ({ t: time, v }))

/** Serie Wi-Fi e Bluetooth del Paxcounter (vuote se il nodo non le ha). */
export function paxSeries(series: MetricsResponse['series']): { wifi: Pt[]; ble: Pt[] } {
  return { wifi: toPts(series['paxcounter.wifi']), ble: toPts(series['paxcounter.ble']) }
}

export function hasPax(series: MetricsResponse['series']): boolean {
  const p = paxSeries(series)
  return p.wifi.length > 0 || p.ble.length > 0
}

/** Testo dell'evento: quello del sensore, oppure «Rilevato»/«Cessato» se vuoto. */
export function eventLabel(e: SensorEvent): string {
  if (e.text) return e.text
  return e.value === 0 ? t('sensors.cleared') : t('sensors.detected')
}

const dayStart = (ms: number): number => {
  const d = new Date(ms)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000
}

/** Eventi raggruppati per giorno locale, dal più recente; dentro il giorno dal più recente. */
export function groupByDay(events: SensorEvent[], _now: number): { dayStart: number; events: SensorEvent[] }[] {
  const groups = new Map<number, SensorEvent[]>()
  for (const e of [...events].sort((a, b) => b.time - a.time)) {
    const k = dayStart(e.time * 1000)
    const g = groups.get(k)
    if (g) g.push(e)
    else groups.set(k, [e])
  }
  return [...groups.entries()].sort((a, b) => b[0] - a[0]).map(([k, list]) => ({ dayStart: k, events: list }))
}

/** Aggiunge in testa un evento nuovo (non duplica lo stesso id) e taglia a `max`. */
export function mergeLive(list: SensorEvent[], e: SensorEvent, max = 200): SensorEvent[] {
  if (list.some((x) => x.id === e.id)) return list
  return [e, ...list].slice(0, max)
}
