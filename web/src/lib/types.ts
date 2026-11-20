export interface Node {
  id: string
  num: number
  long_name: string | null
  short_name: string | null
  hw_model: string | null
  role: string | null
  firmware: string | null
  lat: number | null
  lon: number | null
  precision_bits: number | null
  position_source: string | null
  position_time: number | null
  country: string | null
  last_heard: number
  sources: string[]
  battery: number | null
  voltage: number | null
  channel_util: number | null
  air_util_tx: number | null
  mqtt_gateways: number
  last_snr: number | null
  hops: number | null
}

export interface Message {
  key: string
  from: string
  from_name: string | null
  to: string
  channel: string
  text: string
  time: number
  country: string | null
  source: string
}

export interface Status {
  mqtt: { connected: boolean; msgs_per_s: number; undecodable: number }
}

export interface AuthStatus {
  pin_set: boolean
  authenticated: boolean
  is_local: boolean
}

// Impostazioni: la forma esatta e' definita dal backend (task successivi).
export type Settings = Record<string, unknown>
