import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getJSON: vi.fn(async () => ({})), send: vi.fn(async () => ({})) }))

import { getJSON, send } from './api'
import { i18n, t } from './i18n/index.svelte'
import { FIX_CHOICES, getPrivacy, precisionText, previewPrivacyFix, radiosAtRisk, reasonKey } from './privacy'
import type { PrivacyRadio } from './types'

beforeEach(() => {
  vi.clearAllMocks()
  i18n.lang = 'it'
})

describe('privacy', () => {
  it('precisionText', () => {
    expect(precisionText(32, null)).toBe(t('privacy.exact'))
    expect(precisionText(14, 1459)).toContain('1,5 km')
    expect(precisionText(15, 730)).toContain('730 m')
    expect(precisionText(0, null)).toBe(t('privacy.notSent'))
    i18n.lang = 'en'
    expect(precisionText(14, 1459)).toContain('1.5 km')
    expect(precisionText(32, null)).toBe('exact')
  })

  it('reasonKey e scelte', () => {
    expect(reasonKey('public_key')).toBe('privacy.reason.public_key')
    expect(t(reasonKey('mqtt_uplink'))).not.toBe('privacy.reason.mqtt_uplink')
    expect(FIX_CHOICES).toEqual([14, 13, 12, 11, 10, 0])
  })

  it('radiosAtRisk filtra le radio senza rischi', () => {
    const list: PrivacyRadio[] = [
      { radio_id: 'a', node_id: '!1', name: 'A', risks: [], error: null },
      {
        radio_id: 'b', node_id: '!2', name: 'B', error: null,
        risks: [{ kind: 'channel', channel_index: 0, channel_name: 'LongFast', precision_bits: 32, precision_m: null, reasons: ['public_key'], suggested_bits: 14 }],
      },
    ]
    expect(radiosAtRisk(list).map((r) => r.radio_id)).toEqual(['b'])
  })

  it('chiamate HTTP', async () => {
    await getPrivacy()
    expect(getJSON).toHaveBeenCalledWith('/privacy')
    await previewPrivacyFix('!00000001', 14, null)
    expect(send).toHaveBeenCalledWith('POST', '/privacy/!00000001/preview', { bits: 14, channels: null })
  })
})
