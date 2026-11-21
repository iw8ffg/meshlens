export interface MqttSettings {
  host: string
  port: number
  username: string
  password: string
  topics: string[]
  extra_keys: string[]
}

export interface AppSettings {
  saved_countries: string[]
  retention_messages_days: number
  retention_positions_days: number
  retention_telemetry_days: number
  storage_cap_mb: number
  lan_access: boolean
  battery_alert_pct: number
  silent_alert_hours: number
  mqtt: MqttSettings
  map_mode?: 'auto' | 'online' | 'offline'
  maps_source_url?: string
  update_repo?: string
  /** Mascherato: "••••" se impostato, "" altrimenti. */
  update_token?: string
  update_auto_check?: boolean
  /** Vuoto = tutti i canali MQTT. */
  mqtt_channels?: string[]
  /** Id nodo per l'invio MQTT: "" = id della prima radio collegata, altrimenti "!xxxxxxxx". */
  mqtt_node_id?: string
  /** Conferma di pubblicazione già data: la gestisce il server, non va riscritta da qui. */
  mqtt_send_confirmed?: boolean
}

// Una voce per riga: spazi tolti, righe vuote scartate
export function parseLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l !== '')
}

export function joinLines(items: string[]): string {
  return items.join('\n')
}

/** Preset di modem MQTT noti; LongFast e' il canale pubblico predefinito. */
export const STANDARD_CHANNELS = [
  'LongFast', 'MediumFast', 'MediumSlow', 'ShortFast', 'ShortSlow', 'LongModerate', 'LongSlow', 'ShortTurbo',
]

export interface MqttChannel {
  name: string
  count_1h: number
  enabled: boolean
}

/** Elenco per le caselle: preset standard, canali visti e gia' scelti; piu' attivi per primi. */
export function channelOptions(seen: MqttChannel[], selected: string[]): { name: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const n of [...STANDARD_CHANNELS, ...selected]) counts.set(n, 0)
  for (const c of seen) counts.set(c.name, c.count_1h)
  const order = new Map([...counts.keys()].map((n, i) => [n, i]))
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || order.get(a.name)! - order.get(b.name)!)
}

export type NodeIdCheck = { ok: true; value: string } | { ok: false; error: string }

/** Id nodo per l'invio MQTT: vuoto (= id della radio collegata) oppure "!" e 8 cifre esadecimali. */
export function checkMqttNodeId(text: string): NodeIdCheck {
  const v = text.trim()
  if (v === '') return { ok: true, value: '' }
  if (/^![0-9a-fA-F]{8}$/.test(v)) return { ok: true, value: v.toLowerCase() }
  return { ok: false, error: 'Formato non valido: usa il punto esclamativo e 8 cifre esadecimali, per esempio !a1b2c3d4' }
}
