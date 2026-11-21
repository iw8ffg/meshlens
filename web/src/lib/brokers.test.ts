import { describe, expect, it } from 'vitest'
import {
  brokerLabel,
  channelNameError,
  fromServer,
  isChannelLink,
  newBroker,
  pickBroker,
  portFor,
  pskError,
} from './brokers'
import type { Broker } from './settings'
import type { BrokerStatus } from './types'

const b64 = (n: number) => btoa(String.fromCharCode(...new Array(n).fill(7)))

function broker(over: Partial<Broker> = {}): Broker {
  return { ...newBroker(), id: 'x', ...over }
}
function st(id: string, over: Partial<BrokerStatus> = {}): BrokerStatus {
  return { id, name: `Nome ${id}`, enabled: true, host: 'h', tls: false, encryption: false, connected: false, msgs_per_s: 0, undecodable: 0, ...over }
}

describe('newBroker', () => {
  it('parte con i valori predefiniti e senza id', () => {
    const b = newBroker()
    expect(b.name).toBe('Nuovo broker')
    expect(b.port).toBe(1883)
    expect(b.topics).toEqual(['msh/EU_868/#'])
    expect(b.enabled).toBe(true)
    expect(b.tls).toBe(false)
    expect(b.encryption).toBe(false)
    expect(b.id).toBeUndefined()
  })
})

describe('fromServer', () => {
  it('numera le PSK mascherate e lascia le altre', () => {
    const out = fromServer([broker({ channels: [{ name: 'a', psk: '••••' }, { name: 'b', psk: '••••' }, { name: 'c', psk: 'AQ==' }] })])
    expect(out[0].channels.map((c) => c.psk)).toEqual(['••••#0', '••••#1', 'AQ=='])
  })
  it('numera le chiavi extra', () => {
    const out = fromServer([broker({ extra_keys: ['••••', '••••'] })])
    expect(out[0].extra_keys).toEqual(['••••#0', '••••#1'])
  })
})

describe('channelNameError', () => {
  it('accetta un nome valido', () => expect(channelNameError('Squadra', [])).toBeNull())
  it('rifiuta più di 11 byte UTF-8', () => expect(channelNameError('ÀÀÀÀÀÀ', [])).toBe('Il nome deve avere da 1 a 11 caratteri'))
  it('rifiuta il nome vuoto', () => expect(channelNameError('', [])).toBe('Il nome deve avere da 1 a 11 caratteri'))
  it('rifiuta / # +', () => {
    for (const n of ['a/b', 'a#', '+a']) expect(channelNameError(n, [])).toBe('Il nome non può contenere / # +')
  })
  it('rifiuta i doppioni', () => expect(channelNameError('Uno', ['Due', 'Uno'])).toBe('Esiste già un canale con questo nome'))
})

describe('pskError', () => {
  it('accetta 1, 16 e 32 byte e i riferimenti', () => {
    expect(pskError('AQ==')).toBeNull()
    expect(pskError(b64(16))).toBeNull()
    expect(pskError(b64(32))).toBeNull()
    expect(pskError('••••#3')).toBeNull()
  })
  it('rifiuta il resto', () => {
    const msg = 'La chiave deve essere in base64 e lunga 1, 16 o 32 byte'
    expect(pskError('abc')).toBe(msg)
    expect(pskError(b64(8))).toBe(msg)
    expect(pskError('')).toBe(msg)
  })
})

describe('portFor', () => {
  it('commuta solo le porte standard', () => {
    expect(portFor(true, 1883)).toBe(8883)
    expect(portFor(false, 8883)).toBe(1883)
    expect(portFor(true, 1999)).toBe(1999)
  })
})

describe('isChannelLink', () => {
  it('riconosce i link meshtastic.org/e/#', () => {
    expect(isChannelLink('https://meshtastic.org/e/#CgM')).toBe(true)
    expect(isChannelLink('  https://meshtastic.org/e/#CgM  ')).toBe(true)
    expect(isChannelLink('https://example.com/#x')).toBe(false)
  })
})

describe('pickBroker', () => {
  const list = [st('a', { enabled: false }), st('b'), st('c', { connected: true })]
  it('tiene il corrente se attivo', () => expect(pickBroker('b', list)).toBe('b'))
  it('se disattivato sceglie il primo attivo connesso', () => expect(pickBroker('a', list)).toBe('c'))
  it('altrimenti il primo attivo', () => expect(pickBroker('zz', [st('a', { enabled: false }), st('b')])).toBe('b'))
  it('senza attivi, vuoto', () => expect(pickBroker('a', [st('a', { enabled: false })])).toBe(''))
})

describe('brokerLabel', () => {
  it('mostra il nome con almeno due broker attivi', () => {
    expect(brokerLabel('b1', [st('default'), st('b1')])).toBe('Nome b1')
  })
  it('null con un solo attivo, id ignoto o assente', () => {
    expect(brokerLabel('b1', [st('default', { enabled: false }), st('b1')])).toBeNull()
    expect(brokerLabel('zz', [st('default'), st('b1')])).toBeNull()
    expect(brokerLabel(null, [st('default'), st('b1')])).toBeNull()
    expect(brokerLabel('b1', undefined)).toBeNull()
  })
})
