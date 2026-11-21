import { layers } from '@protomaps/basemaps'
import { themedFlavor } from './map/basemap'
import type { MapTokens } from './map/tokens'
import type { StyleSpecification } from 'maplibre-gl'

export type MapMode = 'auto' | 'online' | 'offline'
export type EffectiveMode = 'online' | 'offline' | 'fallback'

export interface StyleInfo {
  has_offline: boolean
  maxzoom: number
  bounds: number[] | null
}

export const SWITCH_MIN_MS = 30_000

/** Stile offline Protomaps; `theme` sceglie il flavor, `tokens` ne ricolora il fondo. Lo sprite segue il tema (light/dark). */
export function offlineStyle(info: Pick<StyleInfo, 'maxzoom'>, theme: 'dark' | 'light' = 'light', tokens?: MapTokens): StyleSpecification {
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
    layers: layers('protomaps', themedFlavor(theme, tokens), { lang: 'it' }) as StyleSpecification['layers'],
    glyphs: location.origin + '/map-assets/fonts/{fontstack}/{range}.pbf',
    sprite: location.origin + `/map-assets/sprites/${theme === 'dark' ? 'dark' : 'light'}`,
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
