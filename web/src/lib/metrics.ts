import { num } from './format'
import type { MetricsResponse } from './types'

export interface MetricInfo {
  label: string
  unit: string
  digits: number
  chart?: boolean
}

/** Catalogo delle metriche di telemetria, chiave "<variante>.<metrica>". */
export const METRIC_INFO: Record<string, MetricInfo> = {
  'environment.temperature': { label: 'Temperatura', unit: '°C', digits: 1 },
  'environment.relative_humidity': { label: 'Umidità relativa', unit: '%', digits: 0 },
  'environment.barometric_pressure': { label: 'Pressione', unit: 'hPa', digits: 1 },
  'environment.gas_resistance': { label: 'Resistenza del gas', unit: 'MΩ', digits: 2 },
  'environment.iaq': { label: "Indice qualità dell'aria (IAQ)", unit: '', digits: 0 },
  'environment.lux': { label: 'Luminosità', unit: 'lx', digits: 0 },
  'environment.wind_speed': { label: 'Velocità del vento', unit: 'm/s', digits: 1 },
  'environment.wind_direction': { label: 'Direzione del vento', unit: '°', digits: 0 },
  'environment.rainfall_1h': { label: 'Pioggia (1 h)', unit: 'mm', digits: 1 },
  'environment.rainfall_24h': { label: 'Pioggia (24 h)', unit: 'mm', digits: 1 },
  'environment.voltage': { label: 'Tensione', unit: 'V', digits: 2 },
  'environment.current': { label: 'Corrente', unit: 'mA', digits: 1 },
  'air_quality.pm10_standard': { label: 'PM1,0', unit: 'µg/m³', digits: 0 },
  'air_quality.pm25_standard': { label: 'PM2,5', unit: 'µg/m³', digits: 0 },
  'air_quality.pm100_standard': { label: 'PM10', unit: 'µg/m³', digits: 0 },
  'air_quality.co2': { label: 'CO₂', unit: 'ppm', digits: 0 },
  'power.ch1_voltage': { label: 'Canale 1, tensione', unit: 'V', digits: 2 },
  'power.ch1_current': { label: 'Canale 1, corrente', unit: 'mA', digits: 1 },
  'power.ch2_voltage': { label: 'Canale 2, tensione', unit: 'V', digits: 2 },
  'power.ch2_current': { label: 'Canale 2, corrente', unit: 'mA', digits: 1 },
  'power.ch3_voltage': { label: 'Canale 3, tensione', unit: 'V', digits: 2 },
  'power.ch3_current': { label: 'Canale 3, corrente', unit: 'mA', digits: 1 },
  'health.heart_bpm': { label: 'Battito', unit: 'bpm', digits: 0 },
  'health.spO2': { label: 'Saturazione', unit: '%', digits: 0 },
  'health.temperature': { label: 'Temperatura corporea', unit: '°C', digits: 1 },
  'local_stats.num_packets_tx': { label: 'Pacchetti trasmessi', unit: '', digits: 0 },
  'local_stats.num_packets_rx': { label: 'Pacchetti ricevuti', unit: '', digits: 0 },
  'local_stats.num_packets_rx_bad': { label: 'Pacchetti ricevuti con errori', unit: '', digits: 0 },
  'local_stats.num_rx_dupe': { label: 'Duplicati ricevuti', unit: '', digits: 0 },
  'local_stats.num_online_nodes': { label: 'Nodi online', unit: '', digits: 0 },
  'local_stats.num_total_nodes': { label: 'Nodi conosciuti', unit: '', digits: 0 },
  'local_stats.num_tx_relay': { label: 'Ritrasmessi', unit: '', digits: 0 },
  'local_stats.num_tx_relay_canceled': { label: 'Ritrasmissioni annullate', unit: '', digits: 0 },
  'local_stats.noise_floor': { label: 'Rumore di fondo', unit: 'dBm', digits: 0 },
  'local_stats.uptime_seconds': { label: 'Tempo di attività', unit: 's', digits: 0, chart: false },
  'local_stats.heap_total_bytes': { label: 'Memoria totale', unit: 'B', digits: 0, chart: false },
  'local_stats.heap_free_bytes': { label: 'Memoria libera', unit: 'B', digits: 0, chart: false },
}

const VARIANTS = ['environment', 'air_quality', 'power', 'health', 'local_stats']
const CATALOG_KEYS = Object.keys(METRIC_INFO)

export function metricInfo(key: string): MetricInfo {
  return METRIC_INFO[key] ?? { label: key, unit: '', digits: 2, chart: true }
}

function variantRank(key: string): number {
  const i = VARIANTS.indexOf(key.split('.')[0])
  return i === -1 ? VARIANTS.length : i
}

/** Ordine: variante, poi ordine del catalogo, poi alfabetico. */
export function orderMetrics(keys: string[]): string[] {
  const pos = (k: string) => {
    const i = CATALOG_KEYS.indexOf(k)
    return i === -1 ? Number.MAX_SAFE_INTEGER : i
  }
  return [...keys].sort((a, b) => variantRank(a) - variantRank(b) || pos(a) - pos(b) || a.localeCompare(b))
}

export function formatMetric(key: string, value: number): string {
  const info = metricInfo(key)
  const n = num(value, info.digits).replace('-', '−')
  return info.unit ? `${n} ${info.unit}` : n
}

/** Quota di duplicati ricevuti sui pacchetti ricevuti, null se non calcolabile. */
export function dupeRatio(latest: MetricsResponse['latest']): number | null {
  const dupe = latest['local_stats.num_rx_dupe']?.value
  const rx = latest['local_stats.num_packets_rx']?.value
  if (dupe === undefined || !rx) return null
  return dupe / rx
}
