// Copertura prevista: tipi del contratto, validazione dei parametri, colori del raster e chiamate al server.
import { getJSON, send } from './api'
import type { MapTokens } from './map/tokens'
import { decSep } from './format'
import { t } from './i18n/index.svelte'

export interface PredictionParams {
  lat: number
  lon: number
  height_m: number
  tx_power_dbm: number
  antenna_gain_dbi: number
  cable_loss_db: number
  rx_height_m: number
  rx_gain_dbi: number
  frequency_mhz: number
  preset: string
  radius_km: number
}

export type PredictionBbox = [number, number, number, number]

export interface PredictionMeta {
  id: string
  name: string
  created: number
  params: PredictionParams
  sensitivity_dbm: number
  eirp_dbm: number
  bbox: PredictionBbox
  width: number
  height: number
  covered_km2: number
}

export interface PredictionGrid extends PredictionMeta {
  values: string
  nodata: number
}

export interface PredictionJob {
  id: string
  status: 'running' | 'done' | 'failed' | 'cancelled'
  step: string | null
  done: number
  total: number
  error: string | null
  result_id: string | null
  started: number
  ended: number | null
}

export interface PredictionEstimate {
  tiles_total: number
  tiles_missing: number
  download_bytes: number
  bbox: PredictionBbox
}

export interface PredictionCompare {
  received: number
  missing: number
  received_covered: number
  received_uncovered: number
  missing_covered: number
  missing_uncovered: number
  outside: number
  agreement_pct: number | null
  rssi_bias_db: number | null
  rssi_rmse_db: number | null
  points: { lat: number; lon: number; received: boolean; measured_rssi: number | null; predicted_rssi: number | null }[]
}

/** Stessa lista di PRESETS lato server. */
export const PRESET_OPTIONS = [
  'SHORT_TURBO', 'SHORT_FAST', 'SHORT_SLOW', 'MEDIUM_FAST', 'MEDIUM_SLOW', 'LONG_FAST', 'LONG_MODERATE', 'LONG_SLOW',
] as const

export const EU868_MAX_EIRP_DBM = 29.15

export function defaultParams(pos?: { lat: number; lon: number }): PredictionParams {
  return {
    lat: pos?.lat ?? 40.85,
    lon: pos?.lon ?? 14.27,
    height_m: 10,
    tx_power_dbm: 22,
    antenna_gain_dbi: 2,
    cable_loss_db: 0,
    rx_height_m: 1.5,
    rx_gain_dbi: 2,
    frequency_mhz: 869.525,
    preset: 'LONG_FAST',
    radius_km: 15,
  }
}

type NumKey = Exclude<keyof PredictionParams, 'preset'>

/** Campi numerici con etichetta nella lingua corrente (getter), unita' e limiti (come lato server). */
export const PARAM_FIELDS: { key: NumKey; label: string; unit: string; min: number; max: number; step: number }[] = [
  { key: 'lat', get label() { return t('prediction.f.lat') }, unit: '°', min: -85, max: 85, step: 0.0001 },
  { key: 'lon', get label() { return t('prediction.f.lon') }, unit: '°', min: -180, max: 180, step: 0.0001 },
  { key: 'height_m', get label() { return t('prediction.f.height_m') }, unit: 'm', min: 0.5, max: 200, step: 0.5 },
  { key: 'tx_power_dbm', get label() { return t('prediction.f.tx_power_dbm') }, unit: 'dBm', min: 0, max: 30, step: 1 },
  { key: 'antenna_gain_dbi', get label() { return t('prediction.f.antenna_gain_dbi') }, unit: 'dBi', min: -5, max: 15, step: 0.5 },
  { key: 'cable_loss_db', get label() { return t('prediction.f.cable_loss_db') }, unit: 'dB', min: 0, max: 20, step: 0.5 },
  { key: 'rx_height_m', get label() { return t('prediction.f.rx_height_m') }, unit: 'm', min: 0.5, max: 30, step: 0.5 },
  { key: 'rx_gain_dbi', get label() { return t('prediction.f.rx_gain_dbi') }, unit: 'dBi', min: -5, max: 15, step: 0.5 },
  { key: 'frequency_mhz', get label() { return t('prediction.f.frequency_mhz') }, unit: 'MHz', min: 863, max: 870, step: 0.025 },
  { key: 'radius_km', get label() { return t('prediction.f.radius_km') }, unit: 'km', min: 1, max: 50, step: 1 },
]

const fmt = (n: number) => decSep(String(n)).replace('-', '−')

/** Primo errore dei parametri, nella lingua corrente; null se tutto e' valido. */
export function validateParams(p: PredictionParams): string | null {
  for (const f of PARAM_FIELDS) {
    const v = p[f.key]
    if (typeof v !== 'number' || !Number.isFinite(v) || v < f.min || v > f.max) {
      return t('prediction.range', { label: f.label, min: fmt(f.min), max: fmt(f.max), unit: f.unit })
    }
  }
  if (!(PRESET_OPTIONS as readonly string[]).includes(p.preset)) return t('prediction.badPreset')
  return null
}

export function eirpDbm(p: PredictionParams): number {
  return p.tx_power_dbm + p.antenna_gain_dbi - p.cable_loss_db
}

export function overLegalLimit(p: PredictionParams): boolean {
  return eirpDbm(p) > EU868_MAX_EIRP_DBM
}

export type MarginBand = 'good' | 'mid' | 'weak'

/** Fascia del margine in dB: ≥ 10 buono, 0..9 al limite, −10..−1 debole; il resto (e −128) non e' coperto. */
export function marginBand(v: number): MarginBand | null {
  if (v >= 10) return 'good'
  if (v >= 0) return 'mid'
  if (v >= -10 && v !== -128) return 'weak'
  return null
}

export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) h = [...h].map((x) => x + x).join('')
  const n = parseInt(h.slice(0, 6), 16)
  if (!Number.isFinite(n)) return [0, 0, 0]
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

const ALPHA: Record<MarginBand, number> = { good: 140, mid: 115, weak: 80 }

/** Griglia dei margini → pixel RGBA con i colori dei token; fuori fascia = trasparente. */
export function gridToRgba(values: Int8Array, t: MapTokens): Uint8ClampedArray {
  const rgb: Record<MarginBand, [number, number, number]> = {
    good: hexToRgb(t.snrGood), mid: hexToRgb(t.snrMid), weak: hexToRgb(t.snrBad),
  }
  const out = new Uint8ClampedArray(values.length * 4)
  for (let i = 0; i < values.length; i++) {
    const b = marginBand(values[i])
    if (!b) continue
    out.set([...rgb[b], ALPHA[b]], i * 4)
  }
  return out
}

export function decodeValues(b64: string): Int8Array {
  const bin = atob(b64)
  const out = new Int8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = (bin.charCodeAt(i) << 24) >> 24
  return out
}

/** Angoli dell'immagine per MapLibre: NO, NE, SE, SO. */
export function imageCoordinates(b: number[]): number[][] {
  const [w, s, e, n] = b
  return [[w, n], [e, n], [e, s], [w, s]]
}

export const estimatePrediction = (p: PredictionParams) => send<PredictionEstimate>('POST', '/prediction/estimate', p)
export const startPrediction = (params: PredictionParams, name: string | null, download: boolean) =>
  send<PredictionJob>('POST', '/prediction/jobs', { params, name, download })
export const cancelPrediction = (id: string) => send<PredictionJob>('POST', `/prediction/jobs/${encodeURIComponent(id)}/cancel`)
export const listPredictions = () => getJSON<PredictionMeta[]>('/predictions')
export const getPrediction = (id: string) => getJSON<PredictionGrid>(`/predictions/${encodeURIComponent(id)}`)
export const deletePrediction = (id: string) => send<void>('DELETE', `/predictions/${encodeURIComponent(id)}`)
export const comparePrediction = (id: string, sessionId: number) =>
  getJSON<PredictionCompare>(`/predictions/${encodeURIComponent(id)}/compare?session_id=${sessionId}`)
