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

export type BackupInfo = { name: string; time: number; reason: string; size_bytes: number }

const REASON_LABELS: Record<string, string> = {
  'pre-migrazione': 'Prima della migrazione',
  'pre-aggiornamento': "Prima dell'aggiornamento",
  settimanale: 'Settimanale',
  manuale: 'Manuale',
  'prima-del-ripristino': 'Prima del ripristino',
}

/** Motivo del backup in italiano; un motivo sconosciuto resta com'è. */
export function reasonLabel(r: string): string {
  return REASON_LABELS[r] ?? r
}

export type ImportResult = { settings: Record<string, unknown>; skipped: string[] }

export function exportUrl(withSecrets: boolean): string {
  return `/api/settings/export?secrets=${withSecrets ? 1 : 0}`
}
