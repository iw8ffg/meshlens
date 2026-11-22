// Testi inglesi: area «map». Il tipo obbliga a tradurre ogni chiave italiana.
import type { map as itArea } from '../it/map'

export const map: Record<keyof typeof itArea, string> = {}
