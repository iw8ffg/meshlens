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
  mqtt: MqttSettings
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
