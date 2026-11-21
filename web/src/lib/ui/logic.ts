// Classi dei colori di dato (stesse soglie su mappa, grafici e tabelle).

export type SnrClass = 'good' | 'mid' | 'bad' | 'none'
export type ContactClass = 'fresh' | 'recent' | 'old'
export type SourceKind = 'radio' | 'mqtt' | 'both'

export function snrClass(v: number | null | undefined): SnrClass {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'none'
  return v >= 0 ? 'good' : v >= -10 ? 'mid' : 'bad'
}

/** Il segno accompagna sempre il colore: ▲ buono, ● medio, ▼ cattivo. */
export function snrGlyph(c: SnrClass): string {
  return c === 'good' ? '▲' : c === 'mid' ? '●' : c === 'bad' ? '▼' : '–'
}

export function contactClass(minutes: number): ContactClass {
  return minutes < 120 ? 'fresh' : minutes < 1440 ? 'recent' : 'old'
}

export function batteryClass(pct: number, usb: boolean): 'usb' | 'low' | 'mid' | '' {
  if (usb) return 'usb'
  return pct < 20 ? 'low' : pct < 40 ? 'mid' : ''
}
