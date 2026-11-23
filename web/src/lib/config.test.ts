import { describe, expect, it } from 'vitest'
import { MASK, SIMPLE_TABS, fieldInput, formChanges, schemaField, enumLabel, genPsk } from './config'
import type { ConfigDict, ConfigSchema } from './types'

const schema: ConfigSchema = {
  owner: { long_name: { type: 'string' }, short_name: { type: 'string' }, is_licensed: { type: 'bool' } },
  config: {
    device: { role: { type: 'enum', enum: ['CLIENT', 'ROUTER', 'REPEATER'] } },
    position: {
      gps_mode: { type: 'enum', enum: ['DISABLED', 'ENABLED', 'NOT_PRESENT'] },
      position_broadcast_secs: { type: 'int' },
      position_broadcast_smart_enabled: { type: 'bool' },
      broadcast_smart_minimum_interval_secs: { type: 'int' },
    },
    lora: {
      region: { type: 'enum', enum: ['UNSET', 'EU_868'] },
      use_preset: { type: 'bool' },
      modem_preset: { type: 'enum', enum: ['LONG_FAST'] },
      hop_limit: { type: 'int' },
      tx_power: { type: 'int' },
      tx_enabled: { type: 'bool' },
    },
    security: { private_key: { type: 'bytes', secret: true } },
  },
  module_config: {
    telemetry: { device_update_interval: { type: 'int' }, environment_update_interval: { type: 'int' } },
    range_test: { enabled: { type: 'bool' }, sender: { type: 'int' }, save: { type: 'bool' } },
    neighbor_info: { enabled: { type: 'bool' }, update_interval: { type: 'int' }, transmit_over_lora: { type: 'bool' } },
  },
  channel: { psk: { type: 'bytes', secret: true }, name: { type: 'string' } },
}

const orig = (): ConfigDict => ({
  owner: { long_name: 'A', short_name: 'a' },
  config: { lora: { hop_limit: 3, region: 'EU_868' }, security: { private_key: MASK } },
  channels: [
    { index: 0, name: 'x', psk: MASK },
    { index: 1, name: 'y', psk: MASK },
  ],
})

describe('formChanges', () => {
  it('riporta solo il campo cambiato', () => {
    const e = orig()
    e.config!.lora.hop_limit = 4
    expect(formChanges(orig(), e)).toEqual({ 'config.lora.hop_limit': 4 })
  })
  it('ignora la maschera invariata', () => {
    expect(formChanges(orig(), orig())).toEqual({})
  })
  it('riporta la psk sostituita', () => {
    const e = orig()
    e.channels![1].psk = 'AAAA'
    expect(formChanges(orig(), e)).toEqual({ 'channels.1.psk': 'AAAA' })
  })
  it('non segnala int64 stringa contro numero', () => {
    const o = orig()
    o.config!.lora.hop_limit = '123'
    const e = orig()
    e.config!.lora.hop_limit = 123
    expect(formChanges(o, e)).toEqual({})
    e.config!.lora.hop_limit = 124
    expect(formChanges(o, e)).toEqual({ 'config.lora.hop_limit': 124 })
  })
  it('gestisce channels.<i>.<campo> e owner', () => {
    const e = orig()
    e.channels![1].name = 'prova'
    e.owner!.long_name = 'B'
    expect(formChanges(orig(), e)).toEqual({ 'channels.1.name': 'prova', 'owner.long_name': 'B' })
  })
})

describe('fieldInput', () => {
  it('select per enum, checkbox per bool', () => {
    expect(fieldInput({ type: 'enum', enum: ['A'] })).toBe('select')
    expect(fieldInput({ type: 'bool' })).toBe('checkbox')
    expect(fieldInput({ type: 'int' })).toBe('number')
    expect(fieldInput({ type: 'string' })).toBe('text')
    expect(fieldInput({ type: 'bytes', secret: true })).toBe('secret')
    expect(fieldInput({ type: 'repeated' })).toBe('readonly')
  })
})

describe('SIMPLE_TABS', () => {
  it('ogni campo esiste nello schema', () => {
    for (const tab of SIMPLE_TABS)
      for (const f of tab.fields) expect(schemaField(schema, f.path), f.path).toBeTruthy()
  })
})

describe('helper', () => {
  it('enumLabel traduce o restituisce il nome', () => {
    expect(enumLabel('config.lora.region', 'EU_868')).toContain('Europa')
    expect(enumLabel('config.lora.region', 'ZZ')).toBe('ZZ')
  })
  it('genPsk produce 32 byte base64', () => {
    expect(atob(genPsk()).length).toBe(32)
  })
})

describe('genPsk (WP4)', () => {
  it('genPsk still 32 bytes, delegata a generatePsk', () => {
    const a = genPsk()
    expect(atob(a).length).toBe(32)
    expect(genPsk()).not.toBe(a)
  })
})
