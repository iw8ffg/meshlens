import { formatBytes } from './maps'
import { t, type MsgKey } from './i18n/index.svelte'

export type DbInfo = {
  size_bytes: number
  free_bytes: number
  schema_version: number
  integrity: string
  rows: Record<string, number>
  last_purge: { time: number; deleted: Record<string, number> } | null
}

/** Esito del controllo d'integrità che indica un database danneggiato
 * (non per "ok", per il controllo non ancora fatto o ancora in corso all'avvio). */
export function integrityDamaged(integrity: string): boolean {
  return integrity !== 'ok' && integrity !== 'non controllata' && integrity !== 'in corso'
}

/** Dimensione leggibile: 1536000 -> "1,5 MB". */
export function bytes(n: number): string {
  return formatBytes(n)
}

/** Etichette delle tabelle (getter: seguono la lingua corrente). */
export const TABLE_LABELS: Record<string, string> = {
  get nodes() { return t('settings.table.nodes') },
  get positions() { return t('settings.table.positions') },
  get messages() { return t('settings.table.messages') },
  get telemetry() { return t('settings.table.telemetry') },
  get links() { return t('settings.table.links') },
  get traceroutes() { return t('settings.table.traceroutes') },
  get coverage_points() { return t('settings.table.coverage_points') },
  get sessions() { return t('settings.table.sessions') },
}

export type BackupInfo = { name: string; time: number; reason: string; size_bytes: number }

const REASON_KEYS: Record<string, MsgKey> = {
  'pre-migrazione': 'settings.reason.preMigration',
  'pre-aggiornamento': 'settings.reason.preUpdate',
  settimanale: 'settings.reason.weekly',
  manuale: 'settings.reason.manual',
  'prima-del-ripristino': 'settings.reason.beforeRestore',
}

/** Motivo del backup nella lingua corrente; un motivo sconosciuto resta com'è. */
export function reasonLabel(r: string): string {
  return Object.hasOwn(REASON_KEYS, r) ? t(REASON_KEYS[r]) : r
}

export type ImportResult = { settings: Record<string, unknown>; skipped: string[] }

export function exportUrl(withSecrets: boolean): string {
  return `/api/settings/export?secrets=${withSecrets ? 1 : 0}`
}
