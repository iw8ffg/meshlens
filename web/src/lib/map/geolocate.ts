// «Dove sono»: posizione del browser con messaggi chiari quando non è disponibile.
export function geoErrorText(code: number | 'insecure' | 'unsupported'): string {
  if (code === 'insecure') return 'La posizione del browser richiede HTTPS: attivalo in Impostazioni → Rete, oppure usa MeshLens su questo PC'
  if (code === 'unsupported') return 'Questo browser non fornisce la posizione'
  if (code === 1) return 'Permesso di posizione negato: consentilo nelle impostazioni del browser'
  if (code === 3) return "Posizione non trovata in tempo: riprova all'aperto"
  return 'Posizione non disponibile'
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
