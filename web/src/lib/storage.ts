// Accesso sicuro a localStorage. Alcuni browser (privacy stretta, iframe, cookie bloccati) lanciano
// SecurityError alla sola lettura di `localStorage`: senza protezione la pagina resta vuota. Qui si
// restituisce il vero localStorage quando accessibile, altrimenti uno shim in memoria (la scelta
// vale solo per questa sessione). Legge `globalThis` a ogni chiamata, non all'import.

function createMemoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (key: string) => (data.has(key) ? data.get(key)! : null),
    key: (index: number) => [...data.keys()][index] ?? null,
    removeItem: (key: string) => {
      data.delete(key)
    },
    setItem: (key: string, value: string) => {
      data.set(key, String(value))
    },
  } as Storage
}

let fallback: Storage | null = null

/** localStorage del browser, o uno shim in memoria se l'accesso è negato o non esiste. Non lancia mai. */
export function safeStorage(): Storage {
  try {
    const s = (globalThis as { localStorage?: Storage }).localStorage
    if (s) return s
  } catch {
    // accesso negato: si usa lo shim
  }
  fallback ??= createMemoryStorage()
  return fallback
}
