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

export type CoverageMode = 'rangetest' | 'position'

export interface CoverageSession {
  id: number
  name: string
  radio_id: string
  mobile_id: string
  mode: CoverageMode
  channel_index: number | null
  interval_s: number
  started: number
  ended: number | null
  end_reason: 'manual' | 'timeout' | null
  base_lat: number | null
  base_lon: number | null
  notes: string
  received: number
  expected: number | null
  missing: number | null
  loss_pct: number | null
  best_snr: number | null
  worst_snr: number | null
  max_distance_m: number | null
  approx_precision_m: number | null
}

export interface CoveragePoint {
  id: number
  segment: number
  seq: number | null
  time: number
  snr: number | null
  rssi: number | null
  hops: number | null
  lat: number | null
  lon: number | null
  precision_bits: number | null
  distance_m: number | null
}

export interface CoverageMissing {
  seq: number
  time: number
  lat: number | null
  lon: number | null
}

export interface CoverageTrackPoint {
  time: number
  lat: number
  lon: number
  precision_bits: number | null
}

export interface CoverageDetail extends CoverageSession {
  points: CoveragePoint[]
  missing_points: CoverageMissing[]
  track: CoverageTrackPoint[]
}

export interface CoverageCheck {
  radio_connected: boolean
  radio_channels: { index: number; name: string }[]
  mobile_known: boolean
  position_age_s: number | null
  precision_bits: number | null
  precision_m: number | null
  gps_ok: boolean
  rangetest_age_s: number | null
  base_position: { lat: number; lon: number } | null
}

export interface CoverageStartBody {
  name?: string
  radio_id: string
  mobile_id: string
  mode?: CoverageMode
  interval_s?: number
  base_lat?: number
  base_lon?: number
  accept_approx?: boolean
}

// ---- Configurazione (fase 5) ----
export type SchemaFieldType = 'bool' | 'int' | 'float' | 'string' | 'enum' | 'bytes' | 'repeated'
export interface SchemaField {
  type: SchemaFieldType
  enum?: string[]
  secret?: boolean
}
export type SchemaSection = Record<string, SchemaField>
export interface ConfigSchema {
  config: Record<string, SchemaSection>
  module_config: Record<string, SchemaSection>
  channel: SchemaSection
  owner: SchemaSection
}

export type ConfigValue = string | number | boolean | null | undefined | unknown[]
export interface ConfigChannel {
  index: number
  role?: string
  name?: string
  psk?: string
  position_precision?: number
  uplink_enabled?: boolean
  downlink_enabled?: boolean
  [k: string]: unknown
}
export interface ConfigDict {
  owner?: Record<string, ConfigValue>
  config?: Record<string, Record<string, ConfigValue>>
  module_config?: Record<string, Record<string, ConfigValue>>
  channels?: ConfigChannel[]
}

export interface ConfigJob {
  id: number
  node_id: string
  radio_id: string
  kind: 'read' | 'apply' | 'reboot' | 'fixed_position'
  status: 'running' | 'done' | 'failed'
  step: string
  progress: [number, number] | null
  error: string | null
  error_code: 'unauthorized' | 'timeout' | 'error' | 'busy' | 'skipped' | null
  result_id: number | null
  verify: 'verified' | 'mismatch' | null
  started: number
  ended: number | null
}

export interface ConfigSaved {
  id: number
  node_id: string
  radio_id: string
  time: number
  config: ConfigDict
  sections: string[]
}

export interface ConfigChange {
  path: string
  old: unknown
  new: unknown
  risky: boolean
  reason: string | null
}
export interface ConfigPreview {
  preview_id: string
  node_id: string
  radio_id: string
  changes: ConfigChange[]
  risky: boolean
  backup_sections: string[]
}

export interface ConfigBackup {
  id: number
  node_id: string
  time: number
  reason: 'before_apply' | 'coverage_prepare' | 'manual'
  label: string
  sections: string[]
  config?: ConfigDict
}

// ---- Prepara le radio (fase 5) ----
export interface CoveragePlanStep {
  node_id: string
  role: 'mobile' | 'base'
  preview: ConfigPreview
}
/** Piano di preparazione o di ripristino: mobile prima, base dopo. */
export interface CoveragePlan {
  plan_id: number
  steps: CoveragePlanStep[]
}
/** Ultimo piano applicato e non ripristinato. */
export interface CoverageLastPlan {
  plan_id: number
  steps: { node_id: string; role: 'mobile' | 'base'; backup_id?: number | null }[]
  jobs?: ConfigJob[]
}

export type MapKind = 'world' | 'italy' | 'area'
export type Bbox = [number, number, number, number]

export interface OfflineMap {
  id: string
  name: string
  kind: MapKind
  bbox: Bbox | null
  maxzoom: number
  size_bytes: number
  created: number | string
  source_date: string | null
}

export interface MapJob {
  id: number | string
  kind: 'tool' | MapKind
  name: string
  status: 'running' | 'done' | 'failed' | 'cancelled'
  step: string
  bytes_done: number
  bytes_total: number | null
  error: string | null
  started: number | null
  ended: number | null
}

export interface MapsState {
  maps: OfflineMap[]
  tool: { installed: boolean; version: string | null; size_bytes: number }
  job: MapJob | null
  disk_free_bytes: number
  mode: 'auto' | 'online' | 'offline'
}

export interface MapEstimate {
  estimate_bytes: number
  source_url: string
  source_date: string | null
  needs_tool: boolean
  tool_size_bytes: number
}

export interface UpdateJob {
  id: number | string
  status: 'running' | 'done' | 'failed'
  bytes_done: number
  bytes_total: number | null
  error: string | null
}

export interface UpdateStatus {
  current: string
  latest: string | null
  available: boolean
  notes: string | null
  published_at: string | number | null
  checked_at: string | number | null
  error: string | null
  job: UpdateJob | null
  can_install: boolean
  frozen: boolean
}
