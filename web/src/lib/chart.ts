export interface Pt {
  t: number
  v: number | null
}

const r = (n: number) => Math.round(n * 10) / 10

/** Path SVG: un valore null interrompe la linea e riparte con un nuovo M. */
export function linePath(points: Pt[], x0: number, x1: number, y0: number, y1: number, w: number, h: number): string {
  const dx = x1 === x0 ? 1 : x1 - x0
  const dy = y1 === y0 ? 1 : y1 - y0
  let d = ''
  let pen = false
  for (const p of points) {
    if (p.v === null) {
      pen = false
      continue
    }
    const x = r(((p.t - x0) / dx) * w)
    const y = r(h - ((p.v - y0) / dy) * h)
    d += `${pen ? 'L' : 'M'}${x},${y}`
    pen = true
  }
  return d
}

/** Batteria in %: 101 = alimentazione esterna, non e' una percentuale e viene scartato. */
export function batterySeries(points: { time: number; battery: number | null }[]): Pt[] {
  return points.map((p) => ({ t: p.time, v: p.battery === null || p.battery > 100 ? null : p.battery }))
}

export function voltageSeries(points: { time: number; voltage: number | null }[]): Pt[] {
  return points.map((p) => ({ t: p.time, v: p.voltage }))
}

/** Intervallo [min, max] con margine `pad`; mai di ampiezza zero. */
export function niceRange(values: number[], pad: number): [number, number] {
  if (values.length === 0) return [0, 1]
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (hi - lo < pad) {
    lo -= pad
    hi += pad
  }
  return [Math.floor((lo - pad) * 10) / 10, Math.ceil((hi + pad) * 10) / 10]
}

/** Punti validi senza vicini validi: linePath non li disegna, quindi si mostrano come cerchietti. */
export function isolatedPoints(points: Pt[], x0: number, x1: number, y0: number, y1: number, w: number, h: number): { x: number; y: number }[] {
  const dx = x1 === x0 ? 1 : x1 - x0
  const dy = y1 === y0 ? 1 : y1 - y0
  const out: { x: number; y: number }[] = []
  points.forEach((p, i) => {
    if (p.v === null) return
    if (points[i - 1]?.v != null || points[i + 1]?.v != null) return
    out.push({ x: r(((p.t - x0) / dx) * w), y: r(h - ((p.v - y0) / dy) * h) })
  })
  return out
}
