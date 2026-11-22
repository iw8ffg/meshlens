import { locale, t } from './i18n/index.svelte'

export function timeAgo(ts: number | null, now: number): string {
  if (ts === null || !Number.isFinite(ts)) return t('common.never')
  const s = Math.max(0, now - ts)
  if (s < 60) return t('common.justNow')
  if (s < 3600) return t('common.minAgo', { n: Math.floor(s / 60) })
  if (s < 86400) return t('common.hourAgo', { n: Math.floor(s / 3600) })
  return t('common.dayAgo', { n: Math.floor(s / 86400) })
}

export function formatDate(ts: number | null): string {
  if (ts === null || !Number.isFinite(ts)) return t('common.never')
  return new Date(ts * 1000).toLocaleString(locale())
}

export function compareLastHeard(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return b - a
}

/** Separatore decimale della lingua per i numeri già composti con String()/toFixed(): «.» in inglese, «,» in italiano. */
export function decSep(s: string): string {
  return locale() === 'it-IT' ? s.replace('.', ',') : s
}

// --- Formato del design (it-IT o en-GB secondo la lingua) ---

const nfCache = new Map<string, Intl.NumberFormat>()
function nf(decimals: number): Intl.NumberFormat {
  const loc = locale()
  const key = `${loc}:${decimals}`
  let f = nfCache.get(key)
  if (!f) {
    f = new Intl.NumberFormat(loc, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    nfCache.set(key, f)
  }
  return f
}

/** Numero nel formato della lingua: num(3.59, 2) -> "3,59" (it) o "3.59" (en). */
export function num(n: number, decimals = 0): string {
  return nf(decimals).format(n)
}

/** Numero con segno: "+" e meno tipografico "−" (U+2212). signed(-3.5, 1) -> "−3,5". */
export function signed(n: number, decimals = 0): string {
  const s = num(Math.abs(n), decimals)
  if (/^[0.,]+$/.test(s)) return s // arrotondato a zero: nessun segno
  return (n > 0 ? '+' : '−') + s
}

/** Eta relativa da minuti: ora, min, h, g. ago(12) -> "12 min fa". */
export function ago(minutes: number | null): string {
  if (minutes === null || !Number.isFinite(minutes)) return t('common.never')
  if (minutes < 1) return t('common.nowShort')
  if (minutes < 60) return t('common.minAgo', { n: Math.floor(minutes) })
  if (minutes < 1440) return t('common.hourAgo', { n: Math.floor(minutes / 60) })
  return t('common.dayAgo', { n: Math.floor(minutes / 1440) })
}
