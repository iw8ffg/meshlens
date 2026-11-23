import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getJSON: vi.fn(async () => ({})), send: vi.fn(async () => ({})) }))

import { getJSON, send } from './api'
import { i18n } from './i18n/index.svelte'
import {
  compareProfiles,
  deleteProfile,
  exportProfileUrl,
  importProfile,
  parseProfileFile,
  previewProfile,
  saveProfile,
  sectionGroups,
  sectionLabel,
} from './profiles'

beforeEach(() => {
  vi.clearAllMocks()
  i18n.lang = 'it'
})

describe('profiles', () => {
  it('sectionGroups divide configurazione e moduli', () => {
    expect(sectionGroups(['config.lora', 'module_config.mqtt', 'config.device', 'boh'])).toEqual({
      config: ['config.lora', 'config.device'],
      module_config: ['module_config.mqtt'],
    })
  })

  it('sectionLabel tradotta, con ripiego sul nome', () => {
    expect(sectionLabel('config.lora')).toBe('LoRa')
    expect(sectionLabel('module_config.futuro')).toBe('futuro')
  })

  it('parseProfileFile: JSON non valido o formato sbagliato', () => {
    expect(() => parseProfileFile('{nope')).toThrowError('profiles.err.badJson')
    expect(() => parseProfileFile('[]')).toThrowError('profiles.err.badFormat')
    expect(() => parseProfileFile('{"format": "altro"}')).toThrowError('profiles.err.badFormat')
    expect(parseProfileFile('{"format": "meshlens-profile", "version": 1}')).toEqual({
      format: 'meshlens-profile',
      version: 1,
    })
  })

  it('chiamate HTTP', async () => {
    await saveProfile({ node_id: '!00000001', name: 'Base' })
    expect(send).toHaveBeenLastCalledWith('POST', '/profiles', { node_id: '!00000001', name: 'Base' })
    await deleteProfile(3)
    expect(send).toHaveBeenLastCalledWith('DELETE', '/profiles/3', { confirm: true })
    await previewProfile(3, '!00000002', null)
    expect(send).toHaveBeenLastCalledWith('POST', '/profiles/3/preview', { node_id: '!00000002', sections: null })
    await importProfile({ format: 'meshlens-profile' })
    expect(send).toHaveBeenLastCalledWith('POST', '/profiles/import', { profile: { format: 'meshlens-profile' }, name: null })
    await compareProfiles({ profile: 3, b: '!00000002', sections: ['config.lora', 'config.device'] })
    expect(getJSON).toHaveBeenLastCalledWith('/profiles/compare?b=%2100000002&profile=3&sections=config.lora%2Cconfig.device')
    await compareProfiles({ a: '!00000001', b: '!00000002' })
    expect(getJSON).toHaveBeenLastCalledWith('/profiles/compare?b=%2100000002&a=%2100000001')
    expect(exportProfileUrl(7)).toBe('/api/profiles/7/export')
  })
})
