import { num } from './format'
import { t, type MsgKey } from './i18n/index.svelte'
import type { MetricsResponse } from './types'

export interface MetricInfo {
  /** Nome nella lingua corrente. */
  label: string
  unit: string
  digits: number
  chart?: boolean
}

type MetricDef = Omit<MetricInfo, 'label'>

/** Catalogo delle metriche di telemetria, chiave "<variante>.<metrica>". */
/** Le etichette stanno nel catalogo, chiave `nodes.metric.<variante>.<metrica>`. */
export const METRIC_INFO: Record<string, MetricDef> = {
  'environment.temperature': { unit: '°C', digits: 1 },
  'environment.relative_humidity': { unit: '%', digits: 0 },
  'environment.barometric_pressure': { unit: 'hPa', digits: 1 },
  'environment.gas_resistance': { unit: 'MΩ', digits: 2 },
  'environment.iaq': { unit: '', digits: 0 },
  'environment.lux': { unit: 'lx', digits: 0 },
  'environment.wind_speed': { unit: 'm/s', digits: 1 },
  'environment.wind_direction': { unit: '°', digits: 0 },
  'environment.rainfall_1h': { unit: 'mm', digits: 1 },
  'environment.rainfall_24h': { unit: 'mm', digits: 1 },
  'environment.voltage': { unit: 'V', digits: 2 },
  'environment.current': { unit: 'mA', digits: 1 },
  'air_quality.pm10_standard': { unit: 'µg/m³', digits: 0 },
  'air_quality.pm25_standard': { unit: 'µg/m³', digits: 0 },
  'air_quality.pm100_standard': { unit: 'µg/m³', digits: 0 },
  'air_quality.co2': { unit: 'ppm', digits: 0 },
  'power.ch1_voltage': { unit: 'V', digits: 2 },
  'power.ch1_current': { unit: 'mA', digits: 1 },
  'power.ch2_voltage': { unit: 'V', digits: 2 },
  'power.ch2_current': { unit: 'mA', digits: 1 },
  'power.ch3_voltage': { unit: 'V', digits: 2 },
  'power.ch3_current': { unit: 'mA', digits: 1 },
  'health.heart_bpm': { unit: 'bpm', digits: 0 },
  'health.spO2': { unit: '%', digits: 0 },
  'health.temperature': { unit: '°C', digits: 1 },
  'local_stats.num_packets_tx': { unit: '', digits: 0 },
  'local_stats.num_packets_rx': { unit: '', digits: 0 },
  'local_stats.num_packets_rx_bad': { unit: '', digits: 0 },
  'local_stats.num_rx_dupe': { unit: '', digits: 0 },
  'local_stats.num_online_nodes': { unit: '', digits: 0 },
  'local_stats.num_total_nodes': { unit: '', digits: 0 },
  'local_stats.num_tx_relay': { unit: '', digits: 0 },
  'local_stats.num_tx_relay_canceled': { unit: '', digits: 0 },
  'local_stats.noise_floor': { unit: 'dBm', digits: 0 },
  'local_stats.uptime_seconds': { unit: 's', digits: 0, chart: false },
  'local_stats.heap_total_bytes': { unit: 'B', digits: 0, chart: false },
  'local_stats.heap_free_bytes': { unit: 'B', digits: 0, chart: false },
  // 1.6: Paxcounter (conteggio di dispositivi Wi-Fi/Bluetooth); le etichette stanno in `sensors.metric.*`
  'paxcounter.wifi': { unit: '', digits: 0 },
  'paxcounter.ble': { unit: '', digits: 0 },
  'paxcounter.uptime': { unit: 's', digits: 0, chart: false },
}

const VARIANTS = ['environment', 'air_quality', 'power', 'health', 'local_stats', 'paxcounter']
const CATALOG_KEYS = Object.keys(METRIC_INFO)

export function metricInfo(key: string): MetricInfo {
  const def = Object.hasOwn(METRIC_INFO, key) ? METRIC_INFO[key] : undefined
  if (!def) return { label: key, unit: '', digits: 2, chart: true }
  const area = key.startsWith('paxcounter.') ? 'sensors.metric' : 'nodes.metric'
  return { ...def, label: t(`${area}.${key}` as MsgKey) }
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
