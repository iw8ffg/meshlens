// Mappa di calore della densita' dei nodi (E5): punti non raggruppati, nessuna proprieta'; sta sotto
// cluster, nodi e icone. L'opacita' scende con lo zoom per non coprire i nodi.
import type { ExpressionSpecification, Map as MLMap } from 'maplibre-gl'
import { EMPTY } from './NodeLayer'
import type { MapTokens } from './tokens'

/** Rampa dalla densita': trasparente, poi i token (radio, contatto recente, SNR cattivo). */
export function heatColorExpr(t: MapTokens): ExpressionSpecification {
  return ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(0,0,0,0)', 0.2, t.srcRadio, 0.55, t.contactRecent, 1, t.snrBad]
}

export function addHeatLayer(map: MLMap, t: MapTokens): void {
  map.addSource('heat', { type: 'geojson', data: EMPTY })
  const before = map.getLayer('precision-all-circle') ? 'precision-all-circle' : 'precision-fill'
  map.addLayer(
    {
      id: 'heat-layer',
      type: 'heatmap',
      source: 'heat',
      paint: {
        'heatmap-weight': 1,
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 12, 12, 40],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 12, 2],
        'heatmap-color': heatColorExpr(t),
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.85, 12, 0.35],
      },
    },
    before,
  )
}
