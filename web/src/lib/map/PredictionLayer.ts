// Copertura prevista: immagine raster (colori dai token) sotto la traccia della prova.
import type { ImageSource, Map as MLMap } from 'maplibre-gl'

export const PRED_SOURCE = 'pred-image'
export const PRED_LAYER = 'pred-raster'
// PNG 1x1 trasparente: segnaposto finche' non c'e' una previsione da mostrare
const BLANK =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const BLANK_COORDS = [[0, 1], [1, 1], [1, 0], [0, 0]]

export function addPredictionLayer(map: MLMap): void {
  map.addSource(PRED_SOURCE, {
    type: 'image',
    url: BLANK,
    coordinates: BLANK_COORDS as [[number, number], [number, number], [number, number], [number, number]],
  })
  map.addLayer(
    { id: PRED_LAYER, type: 'raster', source: PRED_SOURCE, layout: { visibility: 'none' }, paint: { 'raster-opacity': 1 } },
    map.getLayer('cov-track') ? 'cov-track' : undefined,
  )
}

export function setPredictionImage(map: MLMap, shown: { url: string; coords: number[][] } | null): void {
  const src = map.getSource(PRED_SOURCE) as ImageSource | undefined
  if (!src || !map.getLayer(PRED_LAYER)) return
  if (!shown) {
    map.setLayoutProperty(PRED_LAYER, 'visibility', 'none')
    return
  }
  src.updateImage({ url: shown.url, coordinates: shown.coords as [[number, number], [number, number], [number, number], [number, number]] })
  map.setLayoutProperty(PRED_LAYER, 'visibility', 'visible')
}
