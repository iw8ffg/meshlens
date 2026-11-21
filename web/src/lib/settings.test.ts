import { describe, expect, it, test } from 'vitest'
import { joinLines, maskedKeyLines, parseLines } from './settings'

describe('parseLines', () => {
  it('toglie spazi e righe vuote', () => {
    expect(parseLines(' a \r\n\n  \nb\n')).toEqual(['a', 'b'])
  })
  it('testo vuoto -> lista vuota', () => {
    expect(parseLines('')).toEqual([])
  })
  it('round trip con joinLines', () => {
    expect(parseLines(joinLines(['msh/EU_868/#', 'x']))).toEqual(['msh/EU_868/#', 'x'])
  })
})

import { channelOptions, STANDARD_CHANNELS } from './settings'

test('channelOptions: preset standard piu canali visti, ordinati per conteggio', () => {
  expect(STANDARD_CHANNELS[0]).toBe('LongFast')
  const o = channelOptions([{ name: 'Custom', count_1h: 7, enabled: true }, { name: 'LongFast', count_1h: 3, enabled: true }], ['Old'])
  expect(o.find((x) => x.name === 'Custom')).toEqual({ name: 'Custom', count: 7 })
  expect(o.find((x) => x.name === 'LongFast')).toEqual({ name: 'LongFast', count: 3 })
  expect(o.find((x) => x.name === 'MediumSlow')).toEqual({ name: 'MediumSlow', count: 0 })
  expect(o.find((x) => x.name === 'Old')).toEqual({ name: 'Old', count: 0 })
  expect(o.map((x) => x.name).filter((n) => n === 'LongFast')).toHaveLength(1)
  expect(o[0].name).toBe('Custom')
})

import { checkMqttNodeId } from './settings'

describe('checkMqttNodeId', () => {
  it('vuoto vale: si usa la radio collegata', () => {
    expect(checkMqttNodeId('  ')).toEqual({ ok: true, value: '' })
  })
  it('accetta !8hex e normalizza in minuscolo', () => {
    expect(checkMqttNodeId(' !A1B2c3d4 ')).toEqual({ ok: true, value: '!a1b2c3d4' })
  })
  it.each(['a1b2c3d4', '!a1b2c3d', '!a1b2c3d4e', '!g1b2c3d4', '!'])('rifiuta %s', (v) => {
    expect(checkMqttNodeId(v).ok).toBe(false)
  })
})

describe('maskedKeyLines', () => {
  it('numera le chiavi mascherate e lascia le altre', () => {
    expect(maskedKeyLines(['••••', 'AQ==', '••••'])).toEqual(['••••#0', 'AQ==', '••••#2'])
  })
})

import { deviceLabel, pinError } from './settings'

describe('pinError', () => {
  it('con la rete servono almeno 6 cifre', () => {
    expect(pinError('1234', true)).toBe('Il PIN deve avere da 6 a 12 cifre')
    expect(pinError('123456', true)).toBeNull()
  })
  it('senza rete bastano 4 cifre, solo numeri', () => {
    expect(pinError('1234', false)).toBeNull()
    expect(pinError('12a4', false)).toBe('Il PIN deve avere da 4 a 12 cifre')
    expect(pinError('123', false)).toBe('Il PIN deve avere da 4 a 12 cifre')
    expect(pinError('1234567890123', false)).toBe('Il PIN deve avere da 4 a 12 cifre')
    expect(pinError('', true)).toBe('Il PIN deve avere da 6 a 12 cifre')
  })
})

describe('deviceLabel', () => {
  it('riconosce browser e sistema', () => {
    expect(deviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0')).toBe('Edge su Windows')
    expect(deviceLabel('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36')).toBe('Chrome su Android')
    expect(deviceLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')).toBe('Safari su iOS')
    expect(deviceLabel('Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0')).toBe('Firefox su Linux')
  })
  it('user agent assente o ignoto', () => {
    expect(deviceLabel(null)).toBe('Dispositivo sconosciuto')
    expect(deviceLabel('curl/8.0')).toBe('Dispositivo sconosciuto')
  })
})

import { httpsNote } from './settings'

test('httpsNote: testo con la porta HTTPS, 8687 se non nota', () => {
  expect(httpsNote(null)).toBe(
    "Indirizzo: https://<IP del PC>:8687. Il browser mostrerà un avviso perché il certificato è creato da MeshLens: confronta l'impronta qui sotto. Dal PC resta http://127.0.0.1:8686. Vale dal prossimo avvio; Windows potrebbe chiedere il permesso del firewall per la nuova porta.",
  )
  expect(httpsNote(9000)).toContain('https://<IP del PC>:9000.')
})

import { parseKeywords } from './settings'

describe('parseKeywords', () => {
  it('divide su virgole e a capo, toglie spazi, scarta le voci corte e i doppioni', () => {
    expect(parseKeywords(' Ciao, ciao,\nx, soccorso ')).toEqual(['Ciao', 'soccorso'])
  })
  it('al massimo 20 voci', () => {
    const text = Array.from({ length: 25 }, (_, i) => `parola${i}`).join(',')
    expect(parseKeywords(text)).toHaveLength(20)
    expect(parseKeywords(text)[0]).toBe('parola0')
  })
  it('testo vuoto -> lista vuota', () => {
    expect(parseKeywords('  \n , ')).toEqual([])
  })
})
