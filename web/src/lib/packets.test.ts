import { describe, expect, it } from 'vitest'
import { hexDump, hopsText, packetQuery, relayCandidates, resolveNode, type PacketFilters } from './packets'
import type { Node } from './types'

const EMPTY: PacketFilters = { node: '', kind: '', source: '', status: '', minSnr: '', period: '1h' }
const node = (num: number, short: string | null, long: string | null) =>
  ({ id: `!${num.toString(16).padStart(8, '0')}`, num, short_name: short, long_name: long }) as Node

describe('packetQuery', () => {
  it('filtri vuoti: solo since e limit', () => {
    expect(packetQuery(EMPTY, 10000, null, null)).toBe(`since=${10000 - 3600}&limit=100`)
  })
  it('min_snr non numerico omesso, before_id presente', () => {
    const q = new URLSearchParams(packetQuery({ ...EMPTY, minSnr: 'abc', period: 'all' }, 10000, 42, null))
    expect(q.has('min_snr')).toBe(false)
    expect(q.has('since')).toBe(false)
    expect(q.get('before_id')).toBe('42')
  })
  it('tutti i filtri', () => {
    const q = new URLSearchParams(packetQuery({ ...EMPTY, kind: 'text', source: 'rf', status: 'ok', minSnr: '-5' }, 10000, null, '!0000abcd'))
    expect(q.get('node')).toBe('!0000abcd')
    expect(q.get('kind')).toBe('text')
    expect(q.get('source')).toBe('rf')
    expect(q.get('status')).toBe('ok')
    expect(q.get('min_snr')).toBe('-5')
  })
})

describe('resolveNode', () => {
  const nodes = [node(0x1234abcd, 'ABCD', 'Rifugio Monte Rosa'), node(0x12340001, 'Z1', 'Casa')]
  it('id con e senza punto esclamativo', () => {
    expect(resolveNode('!0000abcd', nodes)).toBe('!0000abcd')
    expect(resolveNode('0000ABCD', nodes)).toBe('!0000abcd')
  })
  it('nome breve e parte del nome lungo', () => {
    expect(resolveNode('z1', nodes)).toBe('!12340001')
    expect(resolveNode('monte', nodes)).toBe('!1234abcd')
  })
  it('non riconosciuto', () => {
    expect(resolveNode('zzz', nodes)).toBeNull()
  })
})

describe('hexDump', () => {
  it('una riga', () => {
    expect(hexDump('48656c6c6f00', 16)).toEqual([{ offset: '0000', hex: '48 65 6c 6c 6f 00', ascii: 'Hello·' }])
  })
  it('venti byte: due righe', () => {
    const r = hexDump('41'.repeat(20), 16)
    expect(r).toHaveLength(2)
    expect(r[1].offset).toBe('0010')
  })
})

describe('relayCandidates', () => {
  const nodes = [node(0x1234abcd, null, null), node(0x12340001, null, null)]
  it('ultimo byte', () => {
    expect(relayCandidates(0xcd, nodes).map((n) => n.num)).toEqual([0x1234abcd])
  })
  it('0 e null: nessuno', () => {
    expect(relayCandidates(0, nodes)).toEqual([])
    expect(relayCandidates(null, nodes)).toEqual([])
  })
})

describe('hopsText', () => {
  it('casi', () => {
    expect(hopsText({ hops: 1, hop_start: 3, hop_limit: 2 })).toBe('1 salto')
    expect(hopsText({ hops: 2, hop_start: 3, hop_limit: 1 })).toBe('2 salti')
    expect(hopsText({ hops: null, hop_start: 3, hop_limit: 1 })).toBe('partito con 3, rimasti 1')
    expect(hopsText({ hops: null, hop_start: null, hop_limit: null })).toBe('–')
  })
})
