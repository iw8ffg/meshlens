import { describe, expect, it } from 'vitest'
import { peekFocus, requestFocus, takeFocus } from './msgfocus'

describe('msgfocus', () => {
  it('la richiesta si consuma una volta sola', () => {
    requestFocus('k')
    expect(peekFocus()).toBe('k')
    expect(takeFocus()).toBe('k')
    expect(takeFocus()).toBeNull()
    expect(peekFocus()).toBeNull()
  })
  it('una nuova richiesta sostituisce la precedente', () => {
    requestFocus('a')
    requestFocus('b')
    expect(takeFocus()).toBe('b')
  })
})
