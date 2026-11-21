import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const fromHere = (rel: string) => fileURLToPath(new URL(rel, import.meta.url))

describe('favicon', () => {
  it('index.html links the favicon and apple-touch-icon', () => {
    const html = readFileSync(fromHere('../../index.html'), 'utf8')
    expect(html).toContain('<link rel="icon" href="/favicon.ico" sizes="any" />')
    expect(html).toContain('<link rel="icon" href="/favicon.svg" type="image/svg+xml" />')
    expect(html).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
  })

  it('public folder contains the three icon files', () => {
    for (const name of ['favicon.svg', 'favicon.ico', 'apple-touch-icon.png']) {
      expect(() => readFileSync(fromHere(`../../public/${name}`))).not.toThrow()
    }
  })

  it('favicon.svg is an identical copy of docs/img/logo.svg', () => {
    const svg = readFileSync(fromHere('../../public/favicon.svg'))
    const logo = readFileSync(fromHere('../../../docs/img/logo.svg'))
    expect(svg.equals(logo)).toBe(true)
  })

  it('favicon.ico has the ICO header (reserved 0, type 1)', () => {
    const ico = readFileSync(fromHere('../../public/favicon.ico'))
    expect([...ico.subarray(0, 4)]).toEqual([0x00, 0x00, 0x01, 0x00])
  })

  it('apple-touch-icon.png is 180 px wide', () => {
    const png = readFileSync(fromHere('../../public/apple-touch-icon.png'))
    expect(png.subarray(12, 16).toString('ascii')).toBe('IHDR')
    expect(png.readUInt32BE(16)).toBe(180)
  })
})
