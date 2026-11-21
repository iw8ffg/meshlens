// Fondo mappa in tema: ricolora lo stile OpenFreeMap (online) e il flavor Protomaps (offline)
// con i valori dei token map-land / map-water / map-road / map-label.
import { namedFlavor } from '@protomaps/basemaps'
import type { Flavor } from '@protomaps/basemaps'
import type { StyleSpecification } from 'maplibre-gl'
import { mix } from './tokens'
import type { MapTokens } from './tokens'

type Dict = Record<string, unknown>

const ROADISH = /highway|road|street|path|bridge|tunnel|rail|aeroway|transit|ferry|track|ramp|motorway|trunk|link|service|pedestrian/
const GREEN = /park|wood|forest|grass|landcover|landuse|scrub|farm|garden|golf|pitch|cemetery|wetland/

/**
 * Copia dello stile OpenFreeMap (liberty) con terra, acqua, strade ed etichette dei token.
 * Gli altri colori (parchi, edifici, confini) sono miscele dei quattro per restare in tinta.
 */
export function recolorLiberty(style: StyleSpecification, t: MapTokens): StyleSpecification {
  const out = structuredClone(style) as StyleSpecification
  const soft = mix(t.land, t.road, 0.3)
  const casing = mix(t.land, t.road, 0.5)
  for (const layer of out.layers as unknown as Dict[]) {
    const id = String(layer.id).toLowerCase()
    const type = String(layer.type)
    const paint = (layer.paint ??= {}) as Dict
    const layout = (layer.layout ?? {}) as Dict
    if (type === 'background') {
      paint['background-color'] = t.land
    } else if (type === 'fill') {
      const water = id.includes('water')
      paint['fill-color'] = water ? t.water : id.includes('building') ? casing : GREEN.test(id) ? soft : t.land
      if ('fill-outline-color' in paint) paint['fill-outline-color'] = paint['fill-color']
    } else if (type === 'fill-extrusion') {
      paint['fill-extrusion-color'] = casing
    } else if (type === 'line') {
      let c = t.road
      if (id.includes('water')) c = t.water
      else if (id.includes('boundary') || id.includes('admin')) c = mix(t.label, t.land, 0.45)
      else if (id.includes('casing')) c = casing
      else if (!ROADISH.test(id)) c = casing
      paint['line-color'] = c
    } else if (type === 'symbol') {
      if (layout['text-field'] !== undefined) {
        paint['text-color'] = t.label
        paint['text-halo-color'] = t.land
      }
    } else if (type === 'raster') {
      paint['raster-opacity'] = 0
    } else if (type === 'hillshade') {
      paint['hillshade-exaggeration'] = 0
    }
  }
  return out
}

/** Flavor Protomaps (chiaro o scuro) con i colori di fondo dei token. */
export function themedFlavor(theme: 'dark' | 'light', t?: MapTokens): Flavor {
  const f: Flavor = { ...namedFlavor(theme) }
  if (!t) return f
  const soft = mix(t.land, t.road, 0.3)
  const casing = mix(t.land, t.road, 0.5)
  Object.assign(f, {
    background: t.land,
    earth: t.land,
    water: t.water,
    park_a: soft,
    park_b: soft,
    wood_a: soft,
    wood_b: soft,
    scrub_a: soft,
    scrub_b: soft,
    pedestrian: t.land,
    buildings: casing,
    other: t.road,
    minor_service: t.road,
    minor_a: t.road,
    minor_b: t.road,
    link: t.road,
    major: t.road,
    highway: t.road,
    minor_service_casing: casing,
    minor_casing: casing,
    link_casing: casing,
    major_casing_early: casing,
    major_casing_late: casing,
    highway_casing_early: casing,
    highway_casing_late: casing,
    boundaries: mix(t.label, t.land, 0.45),
    roads_label_minor: t.label,
    roads_label_major: t.label,
    ocean_label: t.label,
    subplace_label: t.label,
    city_label: t.label,
    state_label: t.label,
    country_label: t.label,
    address_label: t.label,
    roads_label_minor_halo: t.land,
    roads_label_major_halo: t.land,
    subplace_label_halo: t.land,
    city_label_halo: t.land,
    state_label_halo: t.land,
    address_label_halo: t.land,
  })
  if (f.landcover) f.landcover = Object.fromEntries(Object.keys(f.landcover).map((k) => [k, soft])) as unknown as Flavor['landcover']
  return f
}
