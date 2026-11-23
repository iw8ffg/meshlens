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
  is_favorite?: boolean
  /** Salti minimi noti quando `hops` e' nullo (1 = non diretto, distanza ignota). */
  hops_min?: number | null
  /** Chiave pubblica (base64), se nota. */
  public_key?: string | null
  /** Secondi epoch dell'ultimo cambio di chiave pubblica. */
  key_changed?: number | null
  /** Nodo ignorato: nascosto ovunque (mappa, elenco, messaggi, avvisi), mai cancellato. */
  is_ignored?: boolean
}

/** 'heard': inviato via MQTT e sentito in radio da un gateway o da una radio locale. */
export type MessageStatus = 'sending' | 'sent' | 'acked' | 'heard' | 'failed'

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
  /** Invii MQTT: chi l'ha sentito in radio (`!id` del gateway o del nodo della radio, oppure `radio:<id>`). */
  heard_by?: string[] | null
  replaces?: string | null
  /** Canale di invio dei messaggi in uscita. */
  via?: 'radio' | 'mqtt'
  /** Id del broker MQTT che ha consegnato il messaggio. */
  broker?: string | null
  /** `packet_id` del messaggio a cui risponde o reagisce. */
  reply_id?: number | null
  /** Vero se e' una reazione: il testo e' l'emoji. */
  emoji?: boolean
  /** DM ricevuto cifrato con la chiave pubblica. */
  pki?: boolean
  /** Codice `Routing.Error` (es. "NO_ROUTE") per lo stato `failed`. */
  error?: string | null
}

export interface Waypoint {
  id: number
  from: string
  from_name: string | null
  lat: number
  lon: number
  name: string
  description: string
  /** Carattere del codepoint, oppure "" se manca o non e' valido. */
  icon: string
  /** Secondi epoch di scadenza; null se non scade mai. */
  expire: number | null
  locked_to: string | null
  time: number
  source: string
  radio_id: string | null
  channel: string
  mine: boolean
}

export interface ConvSummary {
  key: string
  last_time: number
  last_text: string
  last_from: string
  last_emoji: boolean
  unread: number
  read_time: number
}

/** Stato del connettore MQTT. I campi oltre i primi tre sono facoltativi: il client regge un server vecchio. */
export interface MqttStatus {
  connected: boolean
  msgs_per_s: number
  undecodable: number
  connected_since?: number | null
  last_msg_age_s?: number | null
  reconnects?: number
  watchdog_restarts?: number
  last_error?: string | null
  last_error_at?: number | null
  decoded?: number
  drops?: Partial<Record<'empty' | 'unsupported_port' | 'undecodable' | 'json_topic' | 'not_protobuf', number>>
  filtered_channel?: number
  queue_dropped?: number
  queue_size?: number
  /** Topic la cui sottoscrizione e' stata rifiutata dal broker (connessione corrente). */
  refused_topics?: string[]
  brokers?: BrokerStatus[]
}

/** Stato di un singolo broker (anche disattivato). */
export interface BrokerStatus extends MqttStatus {
  id: string
  name: string
  enabled: boolean
  host: string
  tls: boolean
  encryption: boolean
}

export interface Status {
  mqtt: MqttStatus
}

export interface AuthStatus {
  pin_set: boolean
  authenticated: boolean
  is_local: boolean
  /** PIN sotto le 6 cifre con l'accesso dalla rete attivo; null se la lunghezza non è nota. */
  pin_short?: boolean | null
  /** Cifre minime per un PIN nuovo: 6 con l'accesso dalla rete, altrimenti 4. */
  pin_min?: number
  /** Ruolo della sessione (1.6): admin oppure ospite in sola lettura. */
  role?: Role
}

/** Una sessione aperta (dispositivo collegato). Tempi in secondi epoch. */
export interface SessionInfo {
  id: string
  created: number
  last_seen: number
  user_agent: string | null
  ip: string | null
  current: boolean
}

// Impostazioni: la forma esatta e' definita dal backend (task successivi).
export type Settings = Record<string, unknown>

export type RadioKind = 'usb' | 'ble' | 'tcp'
export type RadioState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error'

export interface Radio {
  id: string
  name: string
  kind: RadioKind
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
  source: 'neighborinfo' | 'traceroute' | 'rf_direct' | 'mqtt_gateway'
  snr: number | null
  time: number
}

export type AlertKind = 'battery_low' | 'silent' | 'key_changed' | 'chutil_high' | 'back_online' | 'firmware_old'
  | 'rule_keyword' | 'rule_snr' | 'rule_geofence' | 'rule_battery' | 'rule_silent' | 'sensor_detection' | 'autonomy_low'
export type Role = 'admin' | 'guest'

export interface Alert {
  key: string
  kind: AlertKind
  node_id: string
  node_name: string
  /** Percentuale per battery_low, ore di silenzio per silent, media canale per chutil_high. */
  value: number
  since: number
  /** Versione firmware letta, solo per firmware_old. */
  detail?: string
  /** Regola che ha prodotto l'avviso (avvisi rule_*). */
  rule_id?: number
}

export interface TelemetryPoint {
  time: number
  battery: number | null
  voltage: number | null
  channel_util: number | null
  air_util_tx: number | null
}

export interface MetricsResponse {
  latest: Record<string, { value: number; time: number }>
  series: Record<string, [number, number][]>
}

export interface SnrPoint {
  time: number
  source: 'rf' | 'mqtt'
  snr_avg: number | null
  snr_max: number | null
  packets: number
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
  /** Lanciato dallo scheduler dei traceroute automatici. */
  auto?: boolean
  /** Firma del percorso di andata (id uniti da ">"), solo per status ok. */
  route?: string | null
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

export interface NetworkStats {
  hours: number
  since: number
  totals: { nodes: number; packets: number }
  online: { time: number; nodes: number }[]
  packets: { time: number; kind: string; packets: number; receptions: number }[]
  snr: { bins: number[]; rf: number[]; mqtt: number[] }
  hops: { hops: number | null; nodes: number }[]
  top: { id: string; name: string; packets: number; per_hour: number }[]
  hardware: { value: string; nodes: number }[]
  roles: { value: string; nodes: number }[]
  other_hardware: number
}

export interface PacketRow {
  id: number
  time: number
  from: string
  from_name: string | null
  to: string
  packet_id: number | null
  source: 'rf' | 'mqtt'
  broker: string | null
  radio_id: string | null
  channel: string | number | null
  portnum: number | string | null
  kind: string
  status: string
  snr: number | null
  rssi: number | null
  hops: number | null
  hop_start: number | null
  hop_limit: number | null
  relay_node: number | null
  gateway: string | null
  copies: number
  size: number | null
}

export interface PacketReception {
  source: 'rf' | 'mqtt'
  broker: string | null
  radio_id: string | null
  gateway: string | null
  snr: number | null
  rssi: number | null
  hops: number | null
  relay_node: number | null
  time: number
}

export interface PacketDetail extends PacketRow {
  receptions: PacketReception[]
  summary: Record<string, unknown> | null
  raw_hex: string
}

// ---- 1.6: tipi condivisi (WP0) ----

export type AlertRuleKind = 'keyword' | 'snr_low' | 'geofence' | 'battery' | 'silent' | 'detection'
export interface AlertRule {
  id: number; kind: AlertRuleKind; name: string; enabled: boolean
  node_id: string | null; channel: string | null; threshold: number | null
  params: Record<string, unknown>; cooldown_min: number
  created: number; updated: number; last_fired: number | null
}
export interface SensorEvent {
  id: number; node_id: string; time: number; kind: 'detection'
  text: string | null; value: number | null; source: 'rf' | 'mqtt'
}
export interface TraceTarget {
  node_id: string; enabled: boolean; interval_min: number; radio_id: string | null
  created: number; last_run: number | null; last_status: string | null
  last_traceroute_id: number | null; fail_count: number
}
export interface TakContact {
  node_id: string; callsign: string | null; device_callsign: string | null
  team: string | null; role: string | null; battery: number | null
  lat: number | null; lon: number | null; altitude: number | null
  speed: number | null; course: number | null; compressed: boolean
  time: number; source: 'rf' | 'mqtt'
}
export interface ConfigProfile {
  id: number; name: string; created: number; updated: number
  source_node_id: string | null; source_hw: string | null; firmware: string | null
  sections: string[]; notes: string | null
}
export interface ConfigProfileDetail extends ConfigProfile { data: { config: Record<string, unknown>; module_config: Record<string, unknown> } }
export interface MessageSearchHit { message: Message; snippet: string | null; conv: string | null }
export interface MessageSearchResult { hits: MessageSearchHit[]; next: string | null; engine: 'fts5' | 'like' }
export interface BotStatus { enabled: boolean; queued: number; sent_last_hour: number; paused_until: number | null; last_error: string | null }
/** Poligono di una zona: coppie [lon, lat], chiuso implicitamente, almeno 3 punti (ZoneEditor, geofence). */
export type ZonePolygon = [number, number][]

// ---- 1.6: WP1 ----

// ---- 1.6: WP2 ----

// ---- 1.6: WP3 ----

// ---- 1.6: WP4 ----
/** Tipo di chiave di un canale letto (additivo, non rivela la chiave). */
export type ChannelKeyKind = 'none' | 'default' | 'custom'
export interface ConfigChannelKeyed extends ConfigChannel {
  key_kind?: ChannelKeyKind
}
/** Preferito/ignorato nel NodeDB di una radio collegata. */
export interface RadioFlags {
  radio_id: string
  radio_name: string | null
  favorite: boolean
  ignored: boolean
  muted: boolean | null
}
export interface RadioFlagResult {
  radio_id: string
  ok: boolean
  error: string | null
}
export type AdminCommandKind = 'reboot' | 'set_time' | 'nodedb_reset' | 'shutdown'
export interface AdminStatus {
  node_id: string
  radio_id: string
  local: boolean
  authorized: boolean | null
  radio_public_key: string | null
  read_time: number | null
  reason: string | null
}
export interface CannedMessages {
  messages: string[]
  bytes: number
  max_bytes: number
}
export interface ChannelExport {
  url: string
  channels: { index: number; name: string }[]
}
export type PrivacyReason = 'no_key' | 'public_key' | 'mqtt_uplink' | 'mqtt_map'
export interface PrivacyRisk {
  kind: 'channel' | 'map_report'
  channel_index?: number
  channel_name?: string
  precision_bits: number
  precision_m: number | null
  reasons: PrivacyReason[]
  suggested_bits: number | null
}
export interface PrivacyRadio {
  radio_id: string
  node_id: string | null
  name: string | null
  risks: PrivacyRisk[]
  error: string | null
}
export interface ProfileCompareRow {
  path: string
  a: unknown
  b: unknown
  excluded: boolean
}
export interface ProfileCompare {
  a: { label: string; time: number }
  b: { label: string; time: number }
  sections: string[]
  rows: ProfileCompareRow[]
}
export interface ProfilePreview {
  preview: ConfigPreview
  skipped: string[]
}

// ---- 1.6: WP5 ----

// ---- 1.6: WP6 ----
