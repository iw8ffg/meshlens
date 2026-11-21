import type { Bbox, MapJob } from './types'

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

/** Dimensione leggibile (unita' decimali, virgola): 2000000000 -> "2,0 GB". */
export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  let i = 0
  let v = n
  while (v >= 1000 && i < UNITS.length - 1) {
    v /= 1000
    i++
  }
  const text = i >= 2 ? v.toFixed(1) : String(Math.round(v))
  return `${text.replace('.', ',')} ${UNITS[i]}`
}

/** Avanzamento 0..100, oppure null se il totale non e' noto. */
export function jobPercent(job: Pick<MapJob, 'bytes_done' | 'bytes_total'>): number | null {
  if (job.bytes_total === null || job.bytes_total <= 0) return null
  return Math.min(100, Math.max(0, Math.round((job.bytes_done / job.bytes_total) * 100)))
}

interface BoundsLike {
  getWest(): number
  getSouth(): number
  getEast(): number
  getNorth(): number
}

const r4 = (v: number) => Math.round(v * 10000) / 10000
const clamp = (v: number, lim: number) => Math.min(lim, Math.max(-lim, v))

/** [minLon, minLat, maxLon, maxLat] arrotondata a 4 decimali, limitata a lon ±180 e lat ±85. */
export function bboxFromBounds(b: BoundsLike | number[]): Bbox {
  const [w, s, e, n] = Array.isArray(b) ? b : [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
  return [r4(clamp(w, 180)), r4(clamp(s, 85)), r4(clamp(e, 180)), r4(clamp(n, 85))]
}
