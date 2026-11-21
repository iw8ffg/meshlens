// Immagini dello sprite disegnate a runtime con i colori dei token, rifatte a ogni cambio di tema:
// anelli della fonte (pieno, tratteggiato, doppio), stella «Preferito», casetta «Mio nodo», punto Range Test mancante.
import type { Map as MLMap } from 'maplibre-gl'
import type { MapTokens } from './tokens'

export type RingKind = 'radio' | 'mqtt' | 'both'

export const RING_IMAGE: Record<RingKind, string> = { radio: 'ring-radio', mqtt: 'ring-mqtt', both: 'ring-both' }
export const STAR_IMAGE = 'star-fav'
export const HOUSE_IMAGE = 'house-mine'
export const MISSING_IMAGE = 'cov-missing'

/** Lato logico delle immagini; sulla mappa sono a pixelRatio 2 (canvas di 2x). */
export const RING_SIZE = 32
export const STAR_SIZE = 20
export const HOUSE_SIZE = 20
export const MISSING_SIZE = 20

export interface RingShape {
  r: number
  width: number
  /** Tratteggio [pieno, vuoto] in pixel logici; assente: linea continua. */
  dash?: [number, number]
}

/** Cerchi che compongono ogni anello (centro dell'immagine). */
export function ringShapes(kind: RingKind): RingShape[] {
  if (kind === 'both') {
    return [
      { r: 14, width: 1.75 },
      { r: 10, width: 1.75 },
    ]
  }
  if (kind === 'mqtt') return [{ r: 11, width: 2.5, dash: [3.5, 2.5] }]
  return [{ r: 11, width: 2.5 }]
}

/** Colore di ogni anello: src-radio, src-mqtt, src-both. */
export function ringColor(kind: RingKind, t: MapTokens): string {
  return kind === 'radio' ? t.srcRadio : kind === 'mqtt' ? t.srcMqtt : t.srcBoth
}

/** Vertici di una stella a 5 punte centrata in (cx, cy). */
export function starPoints(cx: number, cy: number, outer: number, inner: number): [number, number][] {
  const pts: [number, number][] = []
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5
    const r = i % 2 === 0 ? outer : inner
    pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)])
  }
  return pts
}

/** Colori dei marcatori sul nodo: stella = brand-amber, casetta = accent; contorno marker-outline (leggibile nei due temi). */
export function markerColors(t: MapTokens): { star: { fill: string; outline: string }; house: { fill: string; outline: string } } {
  return { star: { fill: t.amber, outline: t.outline }, house: { fill: t.accent, outline: t.outline } }
}

/** Vertici di una casetta (tetto + corpo) in un riquadro di lato `size`. */
export function housePoints(size: number): [number, number][] {
  const m = 2
  const s = size - 2 * m
  const x = (u: number) => m + u * s
  const y = (u: number) => m + u * s
  return [
    [x(0.5), y(0)],
    [x(1), y(0.45)],
    [x(0.85), y(0.45)],
    [x(0.85), y(1)],
    [x(0.15), y(1)],
    [x(0.15), y(0.45)],
    [x(0), y(0.45)],
  ]
}

type Draw = (ctx: CanvasRenderingContext2D, s: number) => void

function render(size: number, draw: Draw): ImageData | null {
  const px = size * 2
  const c = document.createElement('canvas')
  c.width = px
  c.height = px
  const ctx = c.getContext('2d')
  if (!ctx) return null
  ctx.scale(2, 2)
  draw(ctx, size)
  return ctx.getImageData(0, 0, px, px)
}

export function drawRing(ctx: CanvasRenderingContext2D, kind: RingKind, color: string, size: number): void {
  const c = size / 2
  ctx.strokeStyle = color
  for (const s of ringShapes(kind)) {
    ctx.lineWidth = s.width
    ctx.setLineDash(s.dash ?? [])
    ctx.beginPath()
    ctx.arc(c, c, s.r, 0, Math.PI * 2)
    ctx.stroke()
  }
  ctx.setLineDash([])
}

export function drawStar(ctx: CanvasRenderingContext2D, fill: string, outline: string, size: number): void {
  const c = size / 2
  const pts = starPoints(c, c + 0.5, size / 2 - 1.5, size / 5)
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
  ctx.closePath()
  ctx.lineJoin = 'round'
  ctx.lineWidth = 2.5
  ctx.strokeStyle = outline
  ctx.stroke()
  ctx.fillStyle = fill
  ctx.fill()
}

export function drawHouse(ctx: CanvasRenderingContext2D, fill: string, outline: string, size: number): void {
  const pts = housePoints(size)
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
  ctx.closePath()
  ctx.lineJoin = 'round'
  ctx.lineWidth = 2.5
  ctx.strokeStyle = outline
  ctx.stroke()
  ctx.fillStyle = fill
  ctx.fill()
}

export function drawMissing(ctx: CanvasRenderingContext2D, color: string, outline: string, size: number): void {
  const c = size / 2
  const r = size / 2 - 2
  const d = r * 0.5
  for (const [w, col] of [
    [4, outline],
    [1.75, color],
  ] as [number, string][]) {
    ctx.strokeStyle = col
    ctx.lineWidth = w
    ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.arc(c, c, r, 0, Math.PI * 2)
    ctx.moveTo(c - d, c - d)
    ctx.lineTo(c + d, c + d)
    ctx.moveTo(c + d, c - d)
    ctx.lineTo(c - d, c + d)
    ctx.stroke()
  }
}

function put(map: MLMap, name: string, img: ImageData | null): void {
  if (!img) return
  if (map.hasImage(name)) map.removeImage(name)
  map.addImage(name, img, { pixelRatio: 2 })
}

/** (Ri)registra tutte le immagini con i colori correnti: si chiama a ogni style.load. */
export function registerSprites(map: MLMap, t: MapTokens): void {
  for (const kind of ['radio', 'mqtt', 'both'] as RingKind[]) {
    put(map, RING_IMAGE[kind], render(RING_SIZE, (ctx, s) => drawRing(ctx, kind, ringColor(kind, t), s)))
  }
  const mc = markerColors(t)
  put(map, STAR_IMAGE, render(STAR_SIZE, (ctx, s) => drawStar(ctx, mc.star.fill, mc.star.outline, s)))
  put(map, HOUSE_IMAGE, render(HOUSE_SIZE, (ctx, s) => drawHouse(ctx, mc.house.fill, mc.house.outline, s)))
  put(map, MISSING_IMAGE, render(MISSING_SIZE, (ctx, s) => drawMissing(ctx, t.inkMuted, t.outline, s)))
}
