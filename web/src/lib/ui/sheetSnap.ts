// Logica pura dei fermi dello Sheet: chiuso, 40%, 78% dell'altezza del contenitore.

export const SHEET_SNAPS = [0, 0.4, 0.78] as const
export type SheetSnap = 0 | 1 | 2

export function clampSnap(i: number): SheetSnap {
  if (!Number.isFinite(i)) return 1
  return Math.min(2, Math.max(0, Math.round(i))) as SheetSnap
}

/** Frazione di altezza durante il trascinamento: trascinare in su (dy < 0) la aumenta. */
export function fractionFromDrag(startFraction: number, dy: number, containerHeight: number): number {
  if (containerHeight <= 0) return startFraction
  const max = SHEET_SNAPS[SHEET_SNAPS.length - 1]
  return Math.min(max, Math.max(0, startFraction - dy / containerHeight))
}

/** Fermo più vicino alla frazione data. */
export function nearestSnap(fraction: number): SheetSnap {
  let best = 0
  let bestD = Infinity
  SHEET_SNAPS.forEach((s, i) => {
    const d = Math.abs(s - fraction)
    if (d < bestD) {
      bestD = d
      best = i
    }
  })
  return best as SheetSnap
}

/** Fermo successivo (dir = 1, espandi) o precedente (dir = -1, riduci), senza uscire dai limiti. */
export function stepSnap(current: SheetSnap, dir: 1 | -1): SheetSnap {
  return clampSnap(current + dir)
}
