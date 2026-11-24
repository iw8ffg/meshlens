import { afterEach, describe, expect, it } from 'vitest'
import { i18n } from './i18n/index.svelte'
import {
  canEnable, confirmedBrokers, errorKey, isLoopbackHost, pausedLabel, sameTarget, targetKey, targetLabel,
  toggleTarget, utf8Bytes, validChannelName, validateLimit, validateReplyText, validateTrigger, webhookCodeLabel,
} from './bot'
import type { BotTarget } from './settings'

afterEach(() => {
  i18n.lang = 'it'
})

const RF: BotTarget = { kind: 'radio', radio_id: 'r1', channel_index: 1 }
const MQ: BotTarget = { kind: 'mqtt', broker: 'b1', channel: 'LongFast' }

describe('validateTrigger', () => {
  it('lunghezza, spazi, doppioni', () => {
    expect(validateTrigger('a')).toBe('bot.err.triggerLength')
    expect(validateTrigger('x'.repeat(33))).toBe('bot.err.triggerLength')
    expect(validateTrigger('orari', ['ORARI'])).toBe('bot.err.triggerDup')
    expect(validateTrigger(' x')).toBe('bot.err.triggerSpaces')
    expect(validateTrigger('orari', ['meteo'])).toBeNull()
  })
})

describe('validateReplyText', () => {
  it('1..195 byte, niente caratteri di controllo', () => {
    expect(validateReplyText('a'.repeat(196))).toBe('bot.err.replyLength')
    expect(validateReplyText('è'.repeat(98))).toBe('bot.err.replyLength') // 196 byte
    expect(validateReplyText('riga\naltra')).toBe('bot.err.replyControl')
    expect(validateReplyText('')).toBe('bot.err.replyLength')
    expect(validateReplyText('a'.repeat(195))).toBeNull()
    expect(utf8Bytes('è')).toBe(2)
  })
})

describe('validateLimit', () => {
  it('interi negli intervalli del server', () => {
    expect(validateLimit('bot_min_interval_s', 14)).toBe(false)
    expect(validateLimit('bot_min_interval_s', 15)).toBe(true)
    expect(validateLimit('bot_max_per_hour', 121)).toBe(false)
    expect(validateLimit('bot_node_cooldown_s', 30.5)).toBe(false)
    expect(validateLimit('bot_node_cooldown_s', null)).toBe(false)
  })
})

describe('canEnable', () => {
  it('serve almeno un bersaglio e ogni broker confermato', () => {
    expect(canEnable({ targets: [], confirmedBrokers: [] })).toEqual({ ok: false, reason: 'bot.enable.noTarget' })
    expect(canEnable({ targets: [MQ], confirmedBrokers: [] }).ok).toBe(false)
    expect(canEnable({ targets: [MQ], confirmedBrokers: [] }).reason).toBe('bot.enable.brokerNotConfirmed')
    expect(canEnable({ targets: [MQ, RF], confirmedBrokers: ['b1'] })).toEqual({ ok: true, reason: null })
    expect(canEnable({ targets: [RF], confirmedBrokers: [] }).ok).toBe(true)
  })
})

describe('errorKey', () => {
  it('codici noti e generico', () => {
    expect(errorKey('duty_cycle_limit')).toBe('bot.err.duty_cycle_limit')
    expect(errorKey('broker_not_confirmed')).toBe('bot.err.broker_not_confirmed')
    expect(errorKey('max_retransmit')).toBe('bot.err.generic')
    expect(errorKey(null)).toBe('bot.err.generic')
  })
})

describe('targetLabel', () => {
  const radios = [{ id: 'r1', name: 'Heltec', channels: [{ index: 1, name: 'Club', role: 'SECONDARY' }] }]
  const brokers = [{ id: 'b1', name: 'Privato' }]
  it('radio + canale e broker + canale', () => {
    expect(targetLabel(RF, radios, brokers)).toBe('Heltec · Club')
    expect(targetLabel({ ...RF, channel_index: 3 }, radios, brokers)).toBe('Heltec · canale 3')
    expect(targetLabel(MQ, radios, brokers)).toBe('Privato · LongFast')
    expect(targetLabel({ ...MQ, broker: 'zz' }, radios, brokers)).toBe('zz · LongFast')
  })
  it('chiave stabile', () => {
    expect(targetKey(RF)).toBe('radio:r1:1')
    expect(targetKey(MQ)).toBe('mqtt:b1:LongFast')
    expect(sameTarget(RF, { kind: 'radio', radio_id: 'r1', channel_index: 1 })).toBe(true)
  })
})

describe('pausedLabel', () => {
  it('vuoto se la pausa e finita', () => {
    expect(pausedLabel(100, 200)).toBe('')
    expect(pausedLabel(null, 200)).toBe('')
    expect(pausedLabel(1000, 200)).toMatch(/^In pausa fino alle /)
  })
})

describe('webhookCodeLabel', () => {
  it('codici e risposte HTTP', () => {
    expect(webhookCodeLabel('ok')).toBe('riuscito')
    expect(webhookCodeLabel('http_404')).toBe('risposta HTTP 404')
    expect(webhookCodeLabel('strano')).toBe('errore')
    expect(webhookCodeLabel('blocked_target')).toBe('indirizzo non consentito (locale o privato)')
    i18n.lang = 'en'
    expect(webhookCodeLabel('redirect')).toBe('redirect not followed')
    expect(webhookCodeLabel('blocked_target')).toBe('address not allowed (local or private)')
  })
})

describe('confirmedBrokers, validChannelName, toggleTarget', () => {
  it('conferme dei broker', () => {
    expect(confirmedBrokers({ mqtt_send_confirmed_brokers: ['b1'] })).toEqual(['b1'])
    expect(confirmedBrokers({ mqtt_send_confirmed: true })).toEqual(['default'])
    expect(confirmedBrokers({})).toEqual([])
  })
  it('nomi di canale validi', () => {
    expect(validChannelName('LongFast')).toBe(true)
    expect(validChannelName('')).toBe(false)
    expect(validChannelName('x'.repeat(12))).toBe(false)
    expect(validChannelName('a/b')).toBe(false)
  })
  it('aggiunge, toglie, rispetta il massimo', () => {
    expect(toggleTarget([], RF, true)).toEqual([RF])
    expect(toggleTarget([RF, MQ], RF, false)).toEqual([MQ])
    expect(toggleTarget([RF], { ...RF }, true)).toEqual([RF])
    const full: BotTarget[] = Array.from({ length: 16 }, (_, i): BotTarget => ({ kind: 'mqtt', broker: 'b', channel: `c${i}` }))
    expect(toggleTarget(full, RF, true)).toBe(full)
  })
})

describe('isLoopbackHost', () => {
  it('solo questo PC', () => {
    expect(isLoopbackHost('127.0.0.1')).toBe(true)
    expect(isLoopbackHost('localhost')).toBe(true)
    expect(isLoopbackHost('[::1]')).toBe(true)
    expect(isLoopbackHost('192.168.1.5')).toBe(false)
  })
})
