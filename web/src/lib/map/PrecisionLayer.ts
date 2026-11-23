// Cerchi di precisione (E5): un punto per nodo con raggio in pixel a zoom 22 (`px22`); la GPU
// scala il cerchio con lo zoom (nessun poligono per nodo). Sta sotto `precision-fill`, cosi' il
// cerchio del nodo selezionato resta sopra.
import type { ExpressionSpecification, Map as MLMap } from 'maplibre-gl'
import { EMPTY } from './NodeLayer'
import type { MapTokens } from './tokens'

/** Raggio in pixel = px22 * 2^(zoom - 22): interpolazione esponenziale di base 2 tra zoom 0 e 22. */
export const PRECISION_RADIUS_EXPR: ExpressionSpecification = ['interpolate', ['exponential', 2], ['zoom'], 0, 0, 22, ['get', 'px22']]

export function addPrecisionLayer(map: MLMap, t: MapTokens): void {
  map.addSource('precision-all', { type: 'geojson', data: EMPTY })
  map.addLayer(
    {
      id: 'precision-all-circle',
      type: 'circle',
      source: 'precision-all',
      minzoom: 8,
      paint: {
        'circle-radius': PRECISION_RADIUS_EXPR,
        'circle-pitch-alignment': 'map',
        'circle-color': t.srcMqtt,
        'circle-opacity': 0.12,
        'circle-stroke-color': t.srcMqtt,
        'circle-stroke-width': 1,
        'circle-stroke-opacity': 0.6,
      },
    },
    'precision-fill',
  )
}
