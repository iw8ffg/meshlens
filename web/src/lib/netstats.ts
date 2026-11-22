// Statistiche della rete: etichette e calcoli per i grafici della pagina Rete.
import type { NetworkStats } from './types'

export const KIND_LABEL: Record<string, string> = {
  text: 'Messaggi',
  position: 'Posizioni',
  nodeinfo: 'Info nodo',
  telemetry: 'Telemetria',
  mapreport: 'Map report',
  neighbors: 'Vicini',
  traceroute: 'Traceroute',
  rangetest: 'Range test',
}

export const kindLabel = (k: string): string => KIND_LABEL[k] ?? k

/** Somma i pacchetti di tutti i tipi, ora per ora (ordinata per tempo). */
export function packetsPerHour(rows: NetworkStats['packets']): { time: number; packets: number }[] {
  const by = new Map<number, number>()
  for (const r of rows) by.set(r.time, (by.get(r.time) ?? 0) + r.packets)
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([time, packets]) => ({ time, packets }))
}

/** Totali per tipo, dal piu' frequente; `share` e' la quota sul totale (0..1). */
export function kindTotals(rows: NetworkStats['packets']): { kind: string; packets: number; share: number }[] {
  const by = new Map<string, number>()
  for (const r of rows) by.set(r.kind, (by.get(r.kind) ?? 0) + r.packets)
  const total = [...by.values()].reduce((a, b) => a + b, 0)
  return [...by.entries()]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .map(([kind, packets]) => ({ kind, packets, share: total > 0 ? packets / total : 0 }))
}

/** Rettangoli delle barre: altezza proporzionale al massimo, ancorate al fondo di `h`. */
export function barRects(values: number[], w: number, h: number, gap = 2): { x: number; y: number; w: number; h: number }[] {
  const n = values.length
  if (n === 0) return []
  const slot = w / n
  const bw = Math.max(0, slot - gap)
  const max = Math.max(0, ...values)
  return values.map((v, i) => {
    const bh = max > 0 ? (Math.max(0, v) / max) * h : 0
    return { x: i * slot + gap / 2, y: h - bh, w: bw, h: bh }
  })
}

const SNR_STEP = 2.5
const SNR_LAST = 15
const fmt = (n: number) => String(n).replace('.', ',').replace('-', '−')

/** Etichetta di un bin dell'SNR: «−20…−17,5»; l'ultimo e' «≥ 15». */
export function snrBinLabel(lo: number): string {
  if (lo >= SNR_LAST) return `≥ ${fmt(SNR_LAST)}`
  return `${fmt(lo)}…${fmt(lo + SNR_STEP)}`
}
