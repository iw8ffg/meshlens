import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LANG_KEY, i18n, initLang, locale, setLang, t, tn, type MsgKey } from './index.svelte'
import { it as itCat } from './it'
import { en as enCat } from './en'
import { translateServer } from './server'

// frammento finto: il catalogo unito deve leggere anche i frammenti dei pacchetti di lavoro
vi.mock('./server-en/wp3.json', () => ({ default: { exact: { 'Prova WP3': 'WP3 test' }, patterns: [] } }))

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

/** Valori che restano uguali in inglese (sigle, nomi di protocollo, termini Meshtastic). */
const SAME_OK = new Set([
  'MeshLens', 'MQTT', 'SNR', 'Radio', 'Firmware', 'Traceroute', 'Map report', 'Range test', 'Base', 'Gateway', 'Portnum',
  'N', 'NE', 'E', 'SE', 'S', 'via MQTT', 'MQTT ({channel})', 'Menu', 'Auto', 'Broker', '{n} min', 'Lingua / Language',
  // Task 11: sigle, nomi propri e termini Meshtastic/GitHub uguali in ogni lingua
  'Range Test', 'Preset', 'EIRP: {v} dBm', 'RMSE', 'Router', 'USB', 'Bluetooth', '(Meshtastic?)', 'Tracker', 'LoRa', 'Uplink', 'Downlink',
  'Config · {sec}', 'Host', 'Password', 'TLS', 'Area', 'PIN', 'Telegram', 'Russia', 'India', 'Singapore 923 MHz', 'Nepal 865 MHz',
  'GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.',
  'Repository access: Only select repositories → iw8ffg/meshlens.', 'Permissions: Contents → Read-only.',
  // 1.6: tipi di pacchetto delle app (nomi propri)
  'Paxcounter', 'ATAK',
])

describe('test_en_complete', () => {
  it('ogni chiave italiana ha un valore inglese non vuoto e diverso dall italiano (salvo SAME_OK e valori senza parole)', () => {
    const noWords = (s: string) => !/\p{L}{3,}/u.test(s.replace(/\{\w+\}/g, ''))
    const bad: string[] = []
    for (const k of Object.keys(itCat) as MsgKey[]) {
      const en = enCat[k]
      if (typeof en !== 'string' || en.trim() === '') bad.push(`${k}: vuota`)
      else if (en === itCat[k] && !SAME_OK.has(en) && !noWords(en)) bad.push(`${k}: uguale all italiano («${en}»)`)
    }
    expect(bad).toEqual([])
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
  it('formatta n con il formato numerico della lingua', () => {
    setLang('en')
    expect(tn('common.messages', 12345)).toBe('12,345 messages')
    setLang('it')
    expect(tn('common.messages', 12345)).toBe('12.345 messaggi')
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
    expect(translateServer('Impostazione sconosciuta: foo')).toBe('Unknown setting: foo')
    expect(translateServer('toString')).toBe('toString')
    expect(translateServer('Un testo mai visto')).toBe('Un testo mai visto')
    expect(translateServer('')).toBe('')
  })
  it('traduce una volta anche i gruppi catturati dal modello', () => {
    setLang('en')
    expect(translateServer('Chiave PSK non valida (psk): lunghezza PSK non valida: 5 byte')).toBe(
      'Invalid PSK key (psk): Invalid PSK length: 5 bytes',
    )
    expect(translateServer('Broker b1: id non valido')).toBe('Broker b1: invalid id')
  })
})

describe('catalogo del server: principale e frammenti (1.6)', () => {
  afterEach(() => setLang('it'))
  it('traduce le voci di un frammento e continua a tradurre il principale', () => {
    setLang('en')
    expect(translateServer('Prova WP3')).toBe('WP3 test')
    expect(translateServer('update_channel deve essere stable oppure beta')).toBe('update_channel must be stable or beta')
  })
})

describe('aree registrate', () => {
  it('it contiene le chiavi di ogni area esistente', () => {
    const areas = import.meta.glob('./it/*.ts', { eager: true }) as Record<string, Record<string, Record<string, string>>>
    const missing: string[] = []
    for (const [file, mod] of Object.entries(areas)) {
      for (const area of Object.values(mod)) {
        for (const key of Object.keys(area)) if (!Object.hasOwn(itCat, key)) missing.push(`${file}: ${key}`)
      }
    }
    expect(missing).toEqual([])
  })
  it('le aree della 1.6 esistono in italiano e in inglese', () => {
    const it16 = import.meta.glob('./it/*.ts')
    const en16 = import.meta.glob('./en/*.ts')
    for (const a of AREAS_16) {
      expect(Object.hasOwn(it16, `./it/${a}.ts`), a).toBe(true)
      expect(Object.hasOwn(en16, `./en/${a}.ts`), a).toBe(true)
    }
  })
})

const AREAS_16 = ['search', 'quick', 'onboarding', 'alertrules', 'sensors', 'health', 'layers', 'topology', 'tak',
  'nodeflags', 'profiles', 'privacy', 'channels', 'canned', 'tracesched', 'bot', 'retention', 'radiodiag',
  'whatsnew', 'guest']
