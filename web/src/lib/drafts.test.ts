import { describe, expect, it } from 'vitest'
import { DRAFTS_KEY, draftSentUnchanged, loadDraft, saveDraft } from './drafts'

describe('draftSentUnchanged', () => {
  it('svuota solo se il testo e ancora quello inviato', () => {
    expect(draftSentUnchanged('ciao ', 'ciao')).toBe(true)
    expect(draftSentUnchanged('ciao e altro', 'ciao')).toBe(false)
    expect(draftSentUnchanged('', 'ciao')).toBe(false)
  })
})

function mem(init: Record<string, string> = {}) {
  const data = new Map(Object.entries(init))
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    data,
  }
}

describe('drafts', () => {
  it('salva e rilegge', () => {
    const s = mem()
    saveDraft(s, 'dm:r1:!b', 'ciao')
    expect(loadDraft(s, 'dm:r1:!b')).toBe('ciao')
    expect(JSON.parse(s.data.get(DRAFTS_KEY)!)).toEqual({ v: 1, drafts: { 'dm:r1:!b': 'ciao' } })
  })
  it('il testo vuoto rimuove la voce', () => {
    const s = mem()
    saveDraft(s, 'a', 'x')
    saveDraft(s, 'a', '')
    expect(loadDraft(s, 'a')).toBe('')
    expect(JSON.parse(s.data.get(DRAFTS_KEY)!).drafts).toEqual({})
  })
  it('oltre 50 voci scompare la più vecchia', () => {
    const s = mem()
    for (let i = 0; i < 51; i++) saveDraft(s, `ch:r1:${i}`, `t${i}`)
    expect(loadDraft(s, 'ch:r1:0')).toBe('')
    expect(loadDraft(s, 'ch:r1:1')).toBe('t1')
    expect(loadDraft(s, 'ch:r1:50')).toBe('t50')
    expect(Object.keys(JSON.parse(s.data.get(DRAFTS_KEY)!).drafts)).toHaveLength(50)
  })
  it('JSON rotto: nessuna bozza e nessuna eccezione', () => {
    const s = mem({ [DRAFTS_KEY]: '{' })
    expect(loadDraft(s, 'a')).toBe('')
    expect(() => saveDraft(s, 'a', 'x')).not.toThrow()
    expect(loadDraft(s, 'a')).toBe('x')
  })
})
