import { formatBytes } from './maps'
import { t, type MsgKey } from './i18n/index.svelte'

export type DbInfo = {
  size_bytes: number
  free_bytes: number
  schema_version: number
  integrity: string
  rows: Record<string, number>
  last_purge: { time: number; deleted: Record<string, number> } | null
  /** Byte per tabella (indici compresi): misura esatta con dbstat, altrimenti stima. */
  table_bytes?: Record<string, number>
  table_bytes_method?: 'dbstat' | 'estimate'
}

export interface RetentionBroker {
  id: string
  name: string
  messages: number
  oldest: number | null
  days: number | null
  would_delete: number
}

export interface RetentionPreview {
  brokers: RetentionBroker[]
  messages_days: number
  traceroutes: { rows: number; would_delete: number; days: number }
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
  get metrics() { return t('settings.table.metrics') },
  get packets() { return t('settings.table.packets') },
}

/** Nome leggibile di una tabella: etichette storiche (area settings), poi quelle della 1.6
 * (`retention.table.*`), altrimenti il nome grezzo. */
export function tableLabel(name: string): string {
  if (Object.hasOwn(TABLE_LABELS, name)) return TABLE_LABELS[name]
  const key = `retention.table.${name}`
  const text = t(key as MsgKey)
  return text === key ? name : text
}

export interface TableSpace {
  name: string
  bytes: number
  rows: number | null
  share: number
}

/** Tabelle in ordine di spazio decrescente con la quota sul totale (0..1). */
export function sortedTableBytes(info: Pick<DbInfo, 'table_bytes' | 'rows'>): TableSpace[] {
  const entries = Object.entries(info.table_bytes ?? {})
  const total = entries.reduce((a, [, b]) => a + Math.max(0, b), 0)
  return entries
    .map(([name, bytes]) => ({
      name,
      bytes,
      rows: Object.hasOwn(info.rows ?? {}, name) ? info.rows[name] : null,
      share: total > 0 ? Math.max(0, bytes) / total : 0,
    }))
    .sort((a, b) => b.bytes - a.bytes || a.name.localeCompare(b.name))
}

/** Giorni effettivi per un broker: vale il minore fra il suo valore e la regola generale. */
export function effectiveBrokerDays(brokerDays: number | null | undefined, generalDays: number): number {
  return brokerDays == null ? generalDays : Math.min(brokerDays, generalDays)
}

export function validateBrokerDays(n: number | null | undefined): MsgKey | null {
  return typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 3650 ? null : 'retention.err.days'
}

/** Mappa da salvare: toglie le voci vuote (= regola generale). */
export function buildBrokerRetention(map: Record<string, number | null | undefined>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [id, v] of Object.entries(map)) if (typeof v === 'number' && Number.isFinite(v)) out[id] = v
  return out
}

export type BackupInfo ={ name: string; time: number; reason: string; size_bytes: number }

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
