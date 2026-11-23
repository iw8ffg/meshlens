import { describe, expect, it } from 'vitest'
import { qrMatrix, qrPath, type QrMatrix } from './qr'

function finderOk(m: QrMatrix, r0: number, c0: number): boolean {
  for (let r = 0; r < 7; r++)
    for (let c = 0; c < 7; c++) {
      const edge = r === 0 || r === 6 || c === 0 || c === 6
      const ring = !edge && (r === 1 || r === 5 || c === 1 || c === 5)
      const want = !ring // bordo scuro, anello chiaro, centro 3x3 scuro
      if (m.cells[r0 + r][c0 + c] !== want) return false
    }
  return true
}

function darkRuns(m: QrMatrix): number {
  let n = 0
  for (const row of m.cells) for (let x = 0; x < row.length; x++) if (row[x] && (x === 0 || !row[x - 1])) n++
  return n
}

describe('qrMatrix', () => {
  it('finder patterns e dimensione regolare', () => {
    const m = qrMatrix('https://meshtastic.org/e/#CgMSAQE')
    expect(m.size % 2).toBe(1)
    expect(m.size).toBeGreaterThanOrEqual(21)
    expect((m.size - 17) % 4).toBe(0)
    expect(m.cells.length).toBe(m.size)
    expect(m.cells[0].length).toBe(m.size)
    expect(finderOk(m, 0, 0)).toBe(true)
    expect(finderOk(m, 0, m.size - 7)).toBe(true)
    expect(finderOk(m, m.size - 7, 0)).toBe(true)
    expect(qrMatrix('https://meshtastic.org/e/#CgMSAQE')).toEqual(m)
  })

  it('link lungo dei canali', () => {
    const url = 'https://meshtastic.org/e/#' + 'A'.repeat(274)
    expect(url.length).toBe(300)
    const m = qrMatrix(url)
    expect(m.size).toBeLessThanOrEqual(177)
    const p = qrPath(m)
    expect(p.viewBox).toBe(`0 0 ${m.size + 8} ${m.size + 8}`)
    expect((p.d.match(/M/g) ?? []).length).toBe(darkRuns(m))
  })

  it('bordo personalizzato', () => {
    const m: QrMatrix = { size: 2, cells: [[true, true], [false, true]] }
    expect(qrPath(m, 1)).toEqual({ d: 'M1 1h2v1h-2zM2 2h1v1h-1z', viewBox: '0 0 4 4' })
  })
})
