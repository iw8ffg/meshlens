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
