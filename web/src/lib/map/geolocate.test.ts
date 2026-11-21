import { describe, expect, it, vi } from 'vitest'
import { geoErrorText, locate } from './geolocate'

describe('geolocate', () => {
  it('senza geolocalizzazione rifiuta con unsupported', async () => {
    await expect(locate(undefined, true)).rejects.toThrow(geoErrorText('unsupported'))
  })
  it('contesto non sicuro: rifiuta senza chiamare il browser', async () => {
    const getCurrentPosition = vi.fn()
    await expect(locate({ getCurrentPosition } as unknown as Geolocation, false)).rejects.toThrow(geoErrorText('insecure'))
    expect(getCurrentPosition).not.toHaveBeenCalled()
  })
  it('successo e opzioni', async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback, _err?: PositionErrorCallback, _opts?: PositionOptions) => ok({ coords: { latitude: 45, longitude: 9, accuracy: 20 }, timestamp: 1000 } as GeolocationPosition))
    const r = await locate({ getCurrentPosition } as unknown as Geolocation, true)
    expect(r).toEqual({ lat: 45, lon: 9, accuracy: 20, time: 1000 })
    expect(getCurrentPosition.mock.calls[0][2]).toMatchObject({ enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 })
  })
  it('errore di permesso', async () => {
    const getCurrentPosition = vi.fn((_ok: PositionCallback, err: PositionErrorCallback) => err({ code: 1 } as GeolocationPositionError))
    await expect(locate({ getCurrentPosition } as unknown as Geolocation, true)).rejects.toThrow('Permesso di posizione negato')
  })
  it('testi degli errori', () => {
    expect(geoErrorText(2)).toBe('Posizione non disponibile')
    expect(geoErrorText(3)).toContain('in tempo')
    expect(geoErrorText(99)).toBe('Posizione non disponibile')
  })
})
