// Funzioni pure di mappa, nodi, rete e messaggi: stesso risultato in italiano e testo inglese dopo setLang('en').
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { i18n, setLang } from './index.svelte'
import { activeFilters } from '../filters'
import { cardinal, myOrigin } from '../distance'
import { hopsLabel } from '../nodes'
import { NODE_SORTS } from '../nodesort'
import { statusLabel } from '../chat'
import { buildConversations, previewText } from '../conversations'
import { routingErrorText } from '../reactions'
import { expiryLabel, validateWaypoint } from '../waypoints'
import { hopsText, statusLabel as packetStatus } from '../packets'
import { kindLabel, snrBinLabel } from '../netstats'
import { formatMetric, metricInfo } from '../metrics'
import { coverageCsv, networkCsv, slug } from '../export'
import { geoErrorText } from '../map/geolocate'
import { rulerText } from '../map/ruler'
import type { CoverageDetail, Node, Radio } from '../types'
import { t } from './index.svelte'

beforeEach(() => {
  i18n.lang = 'it'
})
afterEach(() => {
  i18n.lang = 'it'
})

const node = (over: Partial<Node>): Node => ({ id: '!a', lat: 45, lon: 9, is_local_radio: false, ...over }) as Node

describe('in inglese', () => {
  it('filtri attivi, salti e ordinamenti', () => {
    const f = { countries: ['IT', 'FR'], maxAgeH: 168, sources: ['rf'], text: 'abc', links: false, favorites: true }
    expect(activeFilters(f, (c) => c).map((a) => a.label)).toEqual(['2 nazioni', 'Ultimo contatto: 7 g', 'Fonte: Radio', 'Ricerca: “abc”', 'Solo preferiti'])
    setLang('en')
    expect(activeFilters(f, (c) => c).map((a) => a.label)).toEqual(['2 countries', 'Last heard: 7 d', 'Source: Radio', 'Search: “abc”', 'Favourites only'])
    expect(hopsLabel(0)).toBe('0 (direct)')
    expect(NODE_SORTS.map((s) => t(s.labelKey))).toEqual(['Recent', 'Name', 'SNR', 'Hops', 'Distance'])
    expect(cardinal(225)).toBe('SW')
  })

  it('origine delle distanze', () => {
    const radios = [{ id: 'r1', name: 'R1', state: 'connected', my_node_id: '!a' }] as Radio[]
    const nodes = new Map([['!a', node({})]])
    expect(myOrigin(nodes, radios, null)?.label).toBe('dalla radio R1')
    setLang('en')
    expect(myOrigin(nodes, radios, null)).toMatchObject({ label: 'from radio R1', kind: 'radio' })
  })

  it('stato dei messaggi, conversazioni, errori di consegna', () => {
    setLang('en')
    expect(statusLabel('acked')).toBe('Delivered')
    expect(routingErrorText('TIMEOUT')).toBe('No confirmation within the time limit')
    expect(routingErrorText('XYZ')).toBe('Delivery error (XYZ)')
    const items = buildConversations({
      radios: [{ id: 'r1', name: 'R1', channels: [{ index: 0, name: '' }] } as unknown as Radio],
      groups: new Map(),
      summaries: {},
      counts: {},
      label: (k) => k,
      previewOf: () => '',
    })
    expect(items).toHaveLength(2)
    const own = { text: 'ciao', from: '!x', direction: 'out', time: 1 } as never
    expect(previewText(own, (id) => id, new Set())).toBe('You: ciao')
  })

  it('waypoint', () => {
    const ok = { name: 'a', description: '', lat: 1, lon: 1, expireH: null }
    setLang('en')
    expect(validateWaypoint({ ...ok, name: '' })).toBe('Enter a name')
    expect(expiryLabel(null, 1)).toBe('Does not expire')
    expect(expiryLabel(10, 1000)).toBe('Expired')
  })

  it('pacchetti, statistiche, metriche', () => {
    setLang('en')
    expect(hopsText({ hops: 1, hop_start: 3, hop_limit: 2 })).toBe('1 hop')
    expect(hopsText({ hops: 2, hop_start: 3, hop_limit: 1 })).toBe('2 hops')
    expect(hopsText({ hops: null, hop_start: 3, hop_limit: 1 })).toBe('started with 3, 1 left')
    expect(packetStatus('encrypted')).toBe('Encrypted')
    expect(packetStatus('boh')).toBe('boh')
    expect(kindLabel('position')).toBe('Positions')
    expect(snrBinLabel(-17.5)).toBe('−17.5…−15')
    expect(metricInfo('environment.temperature').label).toBe('Temperature')
    expect(formatMetric('environment.temperature', 21.5)).toBe('21.5 °C')
  })

  it('esportazioni e righello', () => {
    setLang('en')
    expect(networkCsv([]).split('\r\n')[0]).toBe('﻿id;name;short_name;model;role;firmware;country;last_heard;battery;voltage;snr;hops;channel_util;tx_airtime;lat;lon;sources')
    expect(coverageCsv({ points: [], missing_points: [] } as unknown as CoverageDetail).split('\r\n')[0]).toBe('﻿seq;segment;time;lat;lon;snr;rssi;hops;distance_m;status')
    expect(slug('🚀')).toBe('unnamed')
    expect(rulerText([], (id) => id)).toBe('Tap the first point on the map')
    expect(geoErrorText('unsupported')).toBe('This browser does not provide a location')
  })
})
