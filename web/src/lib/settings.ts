export interface MqttSettings {
  host: string
  port: number
  username: string
  password: string
  topics: string[]
  extra_keys: string[]
}

export interface BrokerChannel {
  name: string
  psk: string
}

export interface Broker {
  /** Assente nei broker non ancora salvati: lo assegna il server. */
  id?: string
  name: string
  enabled: boolean
  host: string
  port: number
  tls: boolean
  encryption: boolean
  username: string
  password: string
  topics: string[]
  channels: BrokerChannel[]
  extra_keys: string[]
}

export interface AppSettings {
  saved_countries: string[]
  retention_messages_days: number
  retention_positions_days: number
  retention_telemetry_days: number
  storage_cap_mb: number
  lan_access: boolean
  /** HTTPS sulla porta 8687 per l'accesso dalla rete (vale dal prossimo avvio). */
  lan_https?: boolean
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
  /** Broker (id) con la conferma di pubblicazione già data. */
  mqtt_send_confirmed_brokers?: string[]
  mqtt_brokers?: Broker[]
  /** Notifiche di Windows (toast) per i messaggi e gli eventi. */
  notify_toast?: boolean
  notify_telegram?: boolean
  /** Mascherato: "••••" se impostato, "" altrimenti. */
  telegram_token?: string
  telegram_chat_id?: string
  notify_mine_status?: boolean
  notify_new_node?: boolean
  notify_keywords?: string[]
  /** Ispettore dei pacchetti: spento, nodi archiviati e radio, o tutto il traffico. */
  packet_log_mode?: 'off' | 'archived' | 'all'
  retention_packets_hours?: number
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

/** Parole chiave per le notifiche: separate da virgola o a capo, senza doppioni (maiuscole ignorate), al massimo 20. */
export function parseKeywords(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of text.split(/[,\r\n]+/)) {
    const w = raw.trim()
    if (w.length < 2) continue
    const k = w.toLowerCase()
    if (seen.has(k)) continue
    seen.add(k)
    out.push(w)
    if (out.length === 20) break
  }
  return out
}

export type NodeIdCheck = { ok: true; value: string } | { ok: false; error: string }

/** Id nodo per l'invio MQTT: vuoto (= id della radio collegata) oppure "!" e 8 cifre esadecimali. */
export function checkMqttNodeId(text: string): NodeIdCheck {
  const v = text.trim()
  if (v === '') return { ok: true, value: '' }
  if (/^![0-9a-fA-F]{8}$/.test(v)) return { ok: true, value: v.toLowerCase() }
  return { ok: false, error: 'Formato non valido: usa il punto esclamativo e 8 cifre esadecimali, per esempio !a1b2c3d4' }
}

const KEY_MASK = '••••'

/** Chiavi PSK extra come righe: quelle mascherate dal server diventano "••••#n" (n = posizione
 *  salvata), così restano riconoscibili anche se se ne cancella una. */
export function maskedKeyLines(keys: string[]): string[] {
  return keys.map((k, i) => (k === KEY_MASK ? `${KEY_MASK}#${i}` : k))
}

export const MIN_PIN = 4
export const MIN_PIN_LAN = 6
export const MAX_PIN = 12

/** Errore di un PIN nuovo: solo cifre, da 6 a 12 con l'accesso dalla rete, da 4 a 12 senza. */
export function pinError(pin: string, lan: boolean): string | null {
  const min = lan ? MIN_PIN_LAN : MIN_PIN
  if (!/^\d+$/.test(pin) || pin.length < min || pin.length > MAX_PIN) return `Il PIN deve avere da ${min} a ${MAX_PIN} cifre`
  return null
}

/** Nome leggibile del dispositivo dal user agent, per esempio "Chrome su Windows". */
export function deviceLabel(ua: string | null | undefined): string {
  if (!ua) return 'Dispositivo sconosciuto'
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /OPR\/|Opera/.test(ua)
      ? 'Opera'
      : /Firefox\/|FxiOS\//.test(ua)
        ? 'Firefox'
        : /Chrome\/|CriOS\//.test(ua)
          ? 'Chrome'
          : /Safari\//.test(ua)
            ? 'Safari'
            : null
  const os = /Windows/.test(ua)
    ? 'Windows'
    : /Android/.test(ua)
      ? 'Android'
      : /iPhone|iPad|iPod/.test(ua)
        ? 'iOS'
        : /Mac OS X|Macintosh/.test(ua)
          ? 'macOS'
          : /Linux/.test(ua)
            ? 'Linux'
            : null
  if (browser && os) return `${browser} su ${os}`
  return browser ?? os ?? 'Dispositivo sconosciuto'
}

/** Stato dell'HTTPS per la rete (GET /api/tls). */
export interface TlsInfo {
  enabled: boolean
  port: number | null
  /** SHA-256 del certificato, esadecimale separato da ":". */
  fingerprint_sha256: string | null
  /** Scadenza del certificato, secondi epoch. */
  not_after: number | null
  error: string | null
}

export const HTTPS_PORT = 8687

/** Nota sotto l'interruttore dell'HTTPS. */
export function httpsNote(port: number | null | undefined): string {
  return (
    `Indirizzo: https://<IP del PC>:${port ?? HTTPS_PORT}. Il browser mostrerà un avviso perché il certificato è creato da MeshLens: ` +
    "confronta l'impronta qui sotto. Dal PC resta http://127.0.0.1:8686. Vale dal prossimo avvio; " +
    'Windows potrebbe chiedere il permesso del firewall per la nuova porta.'
  )
}
