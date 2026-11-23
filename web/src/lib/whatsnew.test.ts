import { describe, expect, it } from 'vitest'
import { parseNotes, pickLang } from './whatsnew'

describe('parseNotes', () => {
  it('titoli, elenchi e grassetto', () => {
    const b = parseNotes('#### Aggiunto\n- **Bot:** risponde a !ping\n- altro')
    expect(b.map((x) => x.type)).toEqual(['h', 'li', 'li'])
    expect(b[0].parts).toEqual([{ text: 'Aggiunto', bold: false }])
    expect(b[1].parts[0]).toEqual({ text: 'Bot:', bold: true })
    expect(b[1].parts[1]).toEqual({ text: ' risponde a !ping', bold: false })
  })

  it('nessun markup interpretato, backtick tolti, righe vuote ignorate', () => {
    const b = parseNotes('\n\n<script>x</script>\n\n- usa `!ping`\n')
    expect(b).toEqual([
      { type: 'p', parts: [{ text: '<script>x</script>', bold: false }] },
      { type: 'li', parts: [{ text: 'usa !ping', bold: false }] },
    ])
  })

  it('testo vuoto', () => {
    expect(parseNotes('')).toEqual([])
  })
})

describe('pickLang', () => {
  it('lingua scelta con ripiego', () => {
    expect(pickLang({ it: 'a', en: 'b' }, 'en')).toBe('b')
    expect(pickLang({ it: 'a', en: 'b' }, 'it')).toBe('a')
    expect(pickLang({ it: 'a', en: '' }, 'en')).toBe('a')
    expect(pickLang({ it: '', en: 'b' }, 'it')).toBe('b')
  })
})
