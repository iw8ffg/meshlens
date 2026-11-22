import { describe, expect, it } from 'vitest'
import { WP_ICONS, expiryLabel, validateWaypoint, waypointData, wpImageChar, wpImageName } from './waypoints'
import { t } from './i18n/index.svelte'
import type { Waypoint } from './types'

const wp = (o: Partial<Waypoint>): Waypoint => ({
  id: 1, from: '!a', from_name: null, lat: 45, lon: 9, name: 'x', description: '', icon: '📍', expire: null,
  locked_to: null, time: 1000, source: 'rf', radio_id: null, channel: '0', mine: false, ...o,
})
const ok = { name: 'Ritrovo', description: '', lat: 45, lon: 9, expireH: null }

describe('waypointData', () => {
  it('esclude gli scaduti e usa il codepoint come immagine', () => {
    const fc = waypointData([wp({ id: 1, expire: 500 }), wp({ id: 2, expire: 5000, mine: true })], 1000)
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].properties).toEqual({ id: 2, name: 'x', img: 'wp-1f4cd', mine: true })
  })
  it('icona vuota: wp-default; expire null non scade', () => {
    const fc = waypointData([wp({ icon: '' })], 1e12)
    expect(fc.features[0].properties?.img).toBe('wp-default')
  })
  it('immagine e carattere sono uno l\'inverso dell\'altro; ogni icona e\' un solo codepoint', () => {
    for (const i of WP_ICONS) {
      expect(wpImageChar(wpImageName(i))).toBe(i)
      expect([...i]).toHaveLength(1)
    }
  })
})

describe('validateWaypoint', () => {
  it('valido', () => expect(validateWaypoint(ok)).toBeNull())
  it('nome vuoto o solo spazi', () => {
    expect(validateWaypoint({ ...ok, name: '' })).toBe(t('waypoints.errName'))
    expect(validateWaypoint({ ...ok, name: '  ' })).toBe(t('waypoints.errName'))
  })
  it('nome di 31 byte (à × 16)', () => expect(validateWaypoint({ ...ok, name: 'à'.repeat(16) })).toBe(t('waypoints.errNameLong')))
  it('descrizione oltre 100 byte', () => expect(validateWaypoint({ ...ok, description: 'a'.repeat(101) })).toBe(t('waypoints.errDescLong')))
  it('coordinate fuori intervallo o non finite', () => {
    expect(validateWaypoint({ ...ok, lat: 91 })).toBe(t('waypoints.errCoords'))
    expect(validateWaypoint({ ...ok, lon: -181 })).toBe(t('waypoints.errCoords'))
    expect(validateWaypoint({ ...ok, lat: NaN })).toBe(t('waypoints.errCoords'))
  })
})

describe('expiryLabel', () => {
  it('mai', () => expect(expiryLabel(null, 1000)).toBe(t('waypoints.noExpiry')))
  it('data it-IT', () => expect(expiryLabel(2000000000, 1000)).toMatch(/^Scade il .*2033/))
  it('scaduto', () => expect(expiryLabel(10, 1000)).toBe(t('waypoints.expired')))
})
