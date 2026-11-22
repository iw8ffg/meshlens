import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LANG_KEY, i18n, initLang, locale, setLang, t, tn, type MsgKey } from './index.svelte'
import { it as itCat } from './it'
import { en as enCat } from './en'
import { translateServer } from './server'

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    data,
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v
    },
  }
}

let storage: ReturnType<typeof fakeStorage>
let root: { lang: string }

beforeEach(() => {
  storage = fakeStorage()
  root = { lang: '' }
  vi.stubGlobal('localStorage', storage)
  vi.stubGlobal('document', { documentElement: root })
  i18n.lang = 'it'
})
afterEach(() => {
  vi.unstubAllGlobals()
  i18n.lang = 'it'
})

describe('t', () => {
  it('italiano per impostazione predefinita, inglese dopo setLang, con salvataggio e <html lang>', () => {
    expect(t('nav.map')).toBe('Mappa')
    setLang('en')
    expect(t('nav.map')).toBe('Map')
    expect(storage.data[LANG_KEY]).toBe('en')
    expect(root.lang).toBe('en')
    expect(locale()).toBe('en-GB')
    setLang('it')
    expect(locale()).toBe('it-IT')
    expect(root.lang).toBe('it')
  })

  it('sostituisce i parametri {nome}', () => {
    expect(t('common.minAgo', { n: 5 })).toBe('5 min fa')
    setLang('en')
    expect(t('common.minAgo', { n: 5 })).toBe('5 min ago')
  })

  it('una chiave assente in inglese ricade sull italiano', () => {
    setLang('en')
    const saved = (enCat as Record<string, string>)['nav.map']
    delete (enCat as Record<string, string>)['nav.map']
    try {
      expect(t('nav.map')).toBe('Mappa')
    } finally {
      ;(enCat as Record<string, string>)['nav.map'] = saved
    }
  })

  it('una chiave inesistente restituisce la chiave stessa', () => {
    expect(t('non.esiste' as MsgKey)).toBe('non.esiste')
  })

  it('ogni chiave italiana ha la traduzione inglese e gli stessi segnaposto', () => {
    const ph = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
    for (const k of Object.keys(itCat) as MsgKey[]) {
      expect(enCat[k], k).toBeTypeOf('string')
      expect(ph(enCat[k]), k).toEqual(ph(itCat[k]))
    }
  })
})

describe('tn', () => {
  it('plurale in inglese e in italiano', () => {
    setLang('en')
    expect(tn('common.messages', 1)).toBe('1 message')
    expect(tn('common.messages', 3)).toBe('3 messages')
    expect(tn('common.messages', 0)).toBe('0 messages')
    setLang('it')
    expect(tn('common.messages', 1)).toBe('1 messaggio')
    expect(tn('common.messages', 3)).toBe('3 messaggi')
  })
})

describe('initLang', () => {
  it('senza valore salvato: italiano, anche se il browser è in un altra lingua', () => {
    vi.stubGlobal('navigator', { language: 'en-US', languages: ['en-US'] })
    i18n.lang = 'en'
    expect(initLang()).toBe('it')
    expect(i18n.lang).toBe('it')
    expect(root.lang).toBe('it')
  })
  it('legge il valore salvato; un valore sconosciuto vale italiano', () => {
    storage.data[LANG_KEY] = 'en'
    expect(initLang()).toBe('en')
    expect(root.lang).toBe('en')
    storage.data[LANG_KEY] = 'fr'
    expect(initLang()).toBe('it')
  })
  it('localStorage che solleva eccezioni: nessun errore', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('negato')
      },
      setItem: () => {
        throw new Error('negato')
      },
    })
    expect(initLang()).toBe('it')
    expect(() => setLang('en')).not.toThrow()
    expect(i18n.lang).toBe('en')
  })
})

describe('translateServer', () => {
  it('in italiano restituisce il testo del server', () => {
    expect(translateServer('Attendi 7 s prima di una nuova richiesta a questo router')).toBe(
      'Attendi 7 s prima di una nuova richiesta a questo router',
    )
  })
  it('in inglese: testo esatto, modello con numeri e testo sconosciuto', () => {
    setLang('en')
    expect(translateServer('Accesso richiesto')).toBe('Access required')
    expect(translateServer('Attendi 7 s prima di una nuova richiesta a questo router')).toBe(
      'Wait 7 s before a new request to this router',
    )
    expect(translateServer('Mancano 12 riquadri di altitudine: scaricali per continuare')).toBe(
      '12 elevation tiles are missing: download them to continue',
    )
    expect(translateServer('Attendi 30 s')).toBe('Wait 30 s')
    expect(translateServer('toString')).toBe('toString')
    expect(translateServer('Un testo mai visto')).toBe('Un testo mai visto')
    expect(translateServer('')).toBe('')
  })
})
