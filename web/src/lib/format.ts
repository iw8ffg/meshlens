export function timeAgo(ts: number | null, now: number): string {
  if (ts === null || !Number.isFinite(ts)) return 'mai'
  const s = Math.max(0, now - ts)
  if (s < 60) return 'adesso'
  if (s < 3600) return `${Math.floor(s / 60)} min fa`
  if (s < 86400) return `${Math.floor(s / 3600)} h fa`
  return `${Math.floor(s / 86400)} g fa`
}

export function formatDate(ts: number | null): string {
  if (ts === null || !Number.isFinite(ts)) return 'mai'
  return new Date(ts * 1000).toLocaleString('it-IT')
}

export function compareLastHeard(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0
  if (a === null) return 1
  if (b === null) return -1
  return b - a
}

export function flag(code: string | null): string {
  if (!code || !/^[A-Za-z]{2}$/.test(code)) return '🏳️'
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}

// --- Formato del design (it-IT) ---

const nfCache = new Map<number, Intl.NumberFormat>()
function nf(decimals: number): Intl.NumberFormat {
  let f = nfCache.get(decimals)
  if (!f) {
    f = new Intl.NumberFormat('it-IT', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    nfCache.set(decimals, f)
  }
  return f
}

/** Numero in formato italiano: num(3.59, 2) -> "3,59". */
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
  if (minutes === null || !Number.isFinite(minutes)) return 'mai'
  if (minutes < 1) return 'ora'
  if (minutes < 60) return `${Math.floor(minutes)} min fa`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} h fa`
  return `${Math.floor(minutes / 1440)} g fa`
}
