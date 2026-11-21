// Posizione del browser («Dove sono»): scritta dalla mappa, letta da myOrigin per le distanze.
export const geopos = $state({ pos: null as { lat: number; lon: number; accuracy: number; time: number } | null })
