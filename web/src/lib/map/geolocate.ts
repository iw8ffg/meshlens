import { t } from '../i18n/index.svelte'

// «Dove sono»: posizione del browser con messaggi chiari quando non è disponibile.
export function geoErrorText(code: number | 'insecure' | 'unsupported'): string {
  if (code === 'insecure') return t('map.geo.insecure')
  if (code === 'unsupported') return t('map.geo.unsupported')
  if (code === 1) return t('map.geo.denied')
  if (code === 3) return t('map.geo.timeout')
  return t('map.geo.unavailable')
}

export function locate(geo: Geolocation | undefined, secure: boolean): Promise<{ lat: number; lon: number; accuracy: number; time: number }> {
  if (!secure) return Promise.reject(new Error(geoErrorText('insecure')))
  if (!geo) return Promise.reject(new Error(geoErrorText('unsupported')))
  return new Promise((resolve, reject) => {
    geo.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy, time: p.timestamp }),
      (err) => reject(new Error(geoErrorText(err.code))),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    )
  })
}
