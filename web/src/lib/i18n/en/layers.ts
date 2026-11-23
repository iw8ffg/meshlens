// Testi inglesi: area «layers» (WP3, livelli della mappa). Il tipo obbliga a tradurre ogni chiave italiana.
import type { layers as itArea } from '../it/layers'

export const layers: Record<keyof typeof itArea, string> = {
  'layers.title': 'Layers',
  'layers.aria': 'Map layers',
  'layers.precision': 'Precision circles',
  'layers.precision.hint': 'A circle around nodes that hide their exact position: the larger it is, the less precise.',
  'layers.heat': 'Node density',
  'layers.heat.hint': 'A heat map showing where nodes are most numerous.',
  'layers.infra': 'Infrastructure only',
  'layers.infra.hint': 'Shows only nodes with the router and repeater roles (map only).',
  'layers.infra.none': 'No node with a router or repeater role: the map is empty.',
  'layers.linkLabels': 'Link labels',
  'layers.linkLabels.hint': 'SNR on each link and "direct" for direct reception. Visible when zoomed in and with links turned on in the filters.',
  'layers.linkLabels.noGlyphs': 'Not available with this base map (fonts are missing).',
  'layers.label.direct': 'direct',
  'layers.tak': 'ATAK',
  'layers.tak.hint': 'Positions of ATAK contacts received from the network (portnum 72).',
  'layers.legend.heat': 'Node density',
  'layers.legend.heatLow': 'Few',
  'layers.legend.heatHigh': 'Many',
  'layers.legend.tak': 'ATAK contact',
}
