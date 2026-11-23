import { safeStorage } from '../storage'
// Lingua dell'interfaccia: italiano (predefinito) o inglese, scelta in Impostazioni e salvata in
// localStorage. `t()` legge `i18n.lang` (stato reattivo): nei template e nei `$derived` i testi si
// aggiornano al cambio lingua senza ricaricare la pagina.
import { it } from './it'
import { en } from './en'

export type Lang = 'it' | 'en'
export type MsgKey = keyof typeof it

export const LANG_KEY = 'meshlens.lang'
export const LANGS: readonly Lang[] = ['it', 'en']
/** Le etichette delle lingue non si traducono: ognuno riconosce la propria. */
export const LANG_LABELS: Record<Lang, string> = { it: 'Italiano', en: 'English' }

export const i18n = $state({ lang: 'it' as Lang })

const dicts: Record<Lang, Partial<Record<MsgKey, string>>> = { it, en }

function fill(text: string, params?: Record<string, string | number>): string {
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}

/** Testo nella lingua corrente; una chiave assente in inglese ricade sull'italiano. */
export function t(key: MsgKey, params?: Record<string, string | number>): string {
  return fill(dicts[i18n.lang][key] ?? it[key] ?? key, params)
}

/** Locale per `Intl` e `toLocale*String`. */
export function locale(): 'it-IT' | 'en-GB' {
  return i18n.lang === 'en' ? 'en-GB' : 'it-IT'
}

const pluralRules = new Map<string, Intl.PluralRules>()
const numberFormats = new Map<string, Intl.NumberFormat>()

function cached<T>(cache: Map<string, T>, loc: string, make: () => T): T {
  let v = cache.get(loc)
  if (!v) {
    v = make()
    cache.set(loc, v)
  }
  return v
}

/** Plurale: sceglie `${base}.one` o `${base}.other` secondo `Intl.PluralRules`; `n` e' passato come
 * parametro, scritto col formato numerico della lingua (1.234 / 1,234). */
export function tn(base: string, n: number, params?: Record<string, string | number>): string {
  const loc = locale()
  const cat = cached(pluralRules, loc, () => new Intl.PluralRules(loc)).select(n)
  const dict = dicts[i18n.lang]
  const key = (`${base}.${cat}` in dict || `${base}.${cat}` in it ? `${base}.${cat}` : `${base}.other`) as MsgKey
  return t(key, { n: cached(numberFormats, loc, () => new Intl.NumberFormat(loc)).format(n), ...params })
}

function store(): Storage | null {
  try {
    return safeStorage()
  } catch {
    return null
  }
}

function applyDocument(lang: Lang): void {
  if (typeof document !== 'undefined') document.documentElement.lang = lang
}

export function parseLang(v: unknown): Lang {
  return v === 'en' || v === 'it' ? v : 'it'
}

export function setLang(l: Lang): void {
  i18n.lang = l
  applyDocument(l)
  try {
    store()?.setItem(LANG_KEY, l)
  } catch {
    // localStorage non disponibile: la scelta vale solo per questa sessione
  }
}

/** Legge la lingua salvata. Il predefinito e' l'italiano, anche con un browser in un'altra lingua. */
export function initLang(): Lang {
  let saved: unknown = null
  try {
    saved = store()?.getItem(LANG_KEY)
  } catch {
    saved = null
  }
  const l = parseLang(saved)
  i18n.lang = l
  applyDocument(l)
  return l
}
