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
