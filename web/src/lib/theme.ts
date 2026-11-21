// Tema: Auto / Scuro / Chiaro. `data-theme` su <html>, preferenza in localStorage,
// `<meta name="color-scheme">` per barre di scorrimento e campi nativi.

export type ThemePref = 'auto' | 'dark' | 'light'
export type Theme = 'dark' | 'light'

export const THEME_KEY = 'meshlens.theme'
export const THEME_LABELS: Record<ThemePref, string> = { auto: 'Auto', dark: 'Scuro', light: 'Chiaro' }

export function parsePref(v: unknown): ThemePref {
  return v === 'dark' || v === 'light' || v === 'auto' ? v : 'auto'
}

export function resolveTheme(pref: ThemePref, systemDark: boolean): Theme {
  if (pref === 'auto') return systemDark ? 'dark' : 'light'
  return pref
}

/** Valore per `<meta name="color-scheme">`: in Auto il browser sceglie da solo. */
export function colorSchemeFor(pref: ThemePref): string {
  return pref === 'auto' ? 'dark light' : pref
}

export function loadPref(storage: Pick<Storage, 'getItem'> | null): ThemePref {
  try {
    return parsePref(storage?.getItem(THEME_KEY))
  } catch {
    return 'auto'
  }
}

export function savePref(storage: Pick<Storage, 'setItem'> | null, pref: ThemePref): void {
  try {
    storage?.setItem(THEME_KEY, pref)
  } catch {
    // localStorage non disponibile: la scelta vale solo per questa sessione
  }
}

export interface ThemeEnv {
  storage: Pick<Storage, 'getItem' | 'setItem'> | null
  root: { setAttribute(name: string, value: string): void }
  meta: { setAttribute(name: string, value: string): void } | null
  media: {
    matches: boolean
    addEventListener(type: 'change', cb: (e: { matches: boolean }) => void): void
    removeEventListener(type: 'change', cb: (e: { matches: boolean }) => void): void
  }
}

export interface ThemeController {
  pref(): ThemePref
  theme(): Theme
  setPref(pref: ThemePref): void
  /** Notifica a ogni applicazione del tema; restituisce la disiscrizione. */
  subscribe(cb: (theme: Theme, pref: ThemePref) => void): () => void
  destroy(): void
}

export function createTheme(env: ThemeEnv): ThemeController {
  let pref = loadPref(env.storage)
  let systemDark = env.media.matches
  const subs = new Set<(t: Theme, p: ThemePref) => void>()

  const apply = () => {
    const t = resolveTheme(pref, systemDark)
    env.root.setAttribute('data-theme', t)
    env.meta?.setAttribute('content', colorSchemeFor(pref))
    for (const cb of subs) cb(t, pref)
  }
  const onMedia = (e: { matches: boolean }) => {
    systemDark = e.matches
    apply()
  }
  env.media.addEventListener('change', onMedia)
  apply()

  return {
    pref: () => pref,
    theme: () => resolveTheme(pref, systemDark),
    setPref(p) {
      pref = parsePref(p)
      savePref(env.storage, pref)
      apply()
    },
    subscribe(cb) {
      subs.add(cb)
      return () => {
        subs.delete(cb)
      }
    },
    destroy() {
      env.media.removeEventListener('change', onMedia)
      subs.clear()
    },
  }
}

let current: ThemeController | null = null

/** Avvia il tema sul documento (una sola volta). */
export function initTheme(): ThemeController {
  if (current) return current
  let storage: Storage | null = null
  try {
    storage = window.localStorage
  } catch {
    storage = null
  }
  current = createTheme({
    storage,
    root: document.documentElement,
    meta: document.querySelector('meta[name="color-scheme"]'),
    media: window.matchMedia('(prefers-color-scheme: dark)'),
  })
  return current
}

export function getTheme(): ThemeController {
  return current ?? initTheme()
}
