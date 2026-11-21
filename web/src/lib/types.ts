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
  last_heard: number | null
  sources: string[]
  battery: number | null
  voltage: number | null
  channel_util: number | null
  air_util_tx: number | null
  mqtt_gateways: number
  last_snr: number | null
  hops: number | null
  heard_by?: Record<string, { snr: number | null; rssi: number | null; hops: number | null; time: number }>
  is_local_radio?: boolean
  is_mine?: boolean
}

export type MessageStatus = 'sending' | 'sent' | 'acked' | 'failed'

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
  direction?: 'in' | 'out'
  radio_id?: string | null
  channel_index?: number | null
  packet_id?: number | null
  status?: MessageStatus | null
  replaces?: string | null
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

export type RadioState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error'

export interface Radio {
  id: string
  name: string
  kind: 'usb' | 'ble'
  address: string
  auto_connect: boolean
  state: RadioState
  error: string | null
  my_node_id: string | null
  my_node_name: string | null
  channels: { index: number; name: string; role: string }[]
}

export interface Port {
  device: string
  description: string
  vid: string | null
  pid: string | null
  likely_meshtastic: boolean
  in_use_by: string | null
}

export interface BleDevice {
  address: string
  name: string
}

export interface Link {
  from_id: string
  to_id: string
  source: 'neighborinfo' | 'traceroute' | 'rf_direct'
  snr: number | null
  time: number
}

export interface Alert {
  key: string
  kind: 'battery_low' | 'silent'
  node_id: string
  node_name: string
  /** Percentuale per battery_low, ore di silenzio per silent. */
  value: number
  since: number
}

export interface TelemetryPoint {
  time: number
  battery: number | null
  voltage: number | null
  channel_util: number | null
  air_util_tx: number | null
}

export interface TracerouteHop {
  id: string
  snr: number | null
}

export type TracerouteStatus = 'pending' | 'ok' | 'failed' | 'timeout'

export interface Traceroute {
  id: number
  radio_id: string
  target_id: string
  time: number
  status: TracerouteStatus
  error: string | null
  forward: TracerouteHop[]
  back: TracerouteHop[]
}
