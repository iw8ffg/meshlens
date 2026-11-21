import { formatBytes } from './maps'

export type DbInfo = {
  size_bytes: number
  free_bytes: number
  schema_version: number
  integrity: string
  rows: Record<string, number>
  last_purge: { time: number; deleted: Record<string, number> } | null
}

/** Dimensione leggibile in italiano: 1536000 -> "1,5 MB". */
export function bytes(n: number): string {
  return formatBytes(n)
}

export const TABLE_LABELS: Record<string, string> = {
  nodes: 'Nodi',
  positions: 'Posizioni',
  messages: 'Messaggi',
  telemetry: 'Telemetria',
  links: 'Collegamenti',
  traceroutes: 'Traceroute',
  coverage_points: 'Punti di copertura',
  sessions: 'Sessioni',
}
