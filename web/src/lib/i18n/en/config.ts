// Testi inglesi: area «config». Il tipo obbliga a tradurre ogni chiave italiana.
import type { config as itArea } from '../it/config'

export const config: Record<keyof typeof itArea, string> = {}
