import { layers, namedFlavor } from '@protomaps/basemaps'
import type { StyleSpecification } from 'maplibre-gl'

export type MapMode = 'auto' | 'online' | 'offline'
export type EffectiveMode = 'online' | 'offline' | 'fallback'

export interface StyleInfo {
  has_offline: boolean
  maxzoom: number
  bounds: number[] | null
}

export const SWITCH_MIN_MS = 30_000

export function offlineStyle(info: Pick<StyleInfo, 'maxzoom'>): StyleSpecification {
  return {
    version: 8,
    sources: {
      protomaps: {
        type: 'vector',
        tiles: [location.origin + '/tiles/{z}/{x}/{y}.mvt'],
        maxzoom: info.maxzoom,
        attribution: '© OpenStreetMap contributors · Protomaps',
      },
    },
    layers: layers('protomaps', namedFlavor('light'), { lang: 'it' }) as StyleSpecification['layers'],
    glyphs: '/map-assets/fonts/{fontstack}/{range}.pbf',
    sprite: location.origin + '/map-assets/sprites/light',
  }
}

export function chooseMode(mode: MapMode, online: boolean, hasOffline: boolean, onlineFailed: boolean): EffectiveMode {
  if (mode === 'online') return 'online'
  if (mode === 'offline') return 'offline'
  if (online && !onlineFailed) return 'online'
  return hasOffline ? 'offline' : 'fallback'
}

export function canSwitch(lastSwitch: number, now: number): boolean {
  return now - lastSwitch >= SWITCH_MIN_MS
}
