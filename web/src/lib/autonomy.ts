// Autonomia della batteria: solo presentazione. La stima (regressione sulle ultime 72 h, tendenza dei
// nodi solari) è calcolata dal server in health.py; qui non c'è nessun calcolo statistico.
import { t, tn } from './i18n/index.svelte'
import type { HealthNode } from './types'

/** «circa 6 giorni», «circa 1 giorno», «meno di 1 giorno». */
export function daysLabel(daysLeft: number): string {
  if (daysLeft < 1) return t('health.lessThanDay')
  return tn('health.days', Math.max(1, Math.round(daysLeft)))
}

export function statusLabel(n: HealthNode): string {
  switch (n.status) {
    case 'falling':
      return n.days_left === null ? t('health.status.falling') : daysLabel(n.days_left)
    case 'solar':
      switch (n.solar_trend) {
        case 'charging':
          return t('health.status.charging')
        case 'falling':
          return t('health.status.falling')
        case 'stable':
          return t('health.status.stable')
        default:
          return t('health.status.insufficient')
      }
    case 'charging':
      return t('health.status.charging')
    case 'stable':
      return t('health.status.stable')
    case 'insufficient':
      return t('health.status.insufficient')
    case 'external':
      return t('health.status.external')
  }
}

export function statusTone(n: HealthNode): 'warn' | 'ok' | 'muted' {
  if (n.status === 'falling' && n.days_left !== null && n.days_left <= 3) return 'warn'
  if (n.status === 'solar' && n.solar_trend === 'falling') return 'warn'
  if (n.status === 'charging' || (n.status === 'solar' && n.solar_trend === 'charging')) return 'ok'
  return 'muted'
}

/** «3 g 4 h», «5 h 12 min», «42 min»; «—» se manca. */
export function uptimeLabel(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  const total = Math.max(0, Math.floor(seconds / 60)) // minuti
  const d = Math.floor(total / 1440)
  const h = Math.floor((total % 1440) / 60)
  const m = total % 60
  if (d > 0) return t('health.uptime.dh', { d, h })
  if (h > 0) return t('health.uptime.hm', { h, m })
  return t('health.uptime.m', { n: m })
}

/** Livello da mostrare: la stima del server, altrimenti l'ultima lettura (101 = alimentazione esterna). */
export function levelOf(n: HealthNode): number | null {
  if (n.level !== null) return n.level
  return n.battery !== null && n.battery <= 100 ? n.battery : null
}
