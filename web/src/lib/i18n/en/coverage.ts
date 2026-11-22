// Testi inglesi: area «coverage». Il tipo obbliga a tradurre ogni chiave italiana.
import type { coverage as itArea } from '../it/coverage'

export const coverage: Record<keyof typeof itArea, string> = {}
