// Rileva che il server e' stato aggiornato mentre la pagina restava aperta: il WebSocket si
// riconnette da solo, ma il JavaScript in esecuzione e' quello vecchio.
export const ver = $state<{ loaded: string | null; server: string | null }>({ loaded: null, server: null })

/** Registra la versione letta dal server: la prima e' quella con cui la pagina e' stata caricata. */
export function noteServerVersion(v: unknown): void {
  if (typeof v !== 'string' || !v) return
  if (ver.loaded === null) ver.loaded = v
  ver.server = v
}

/** Versione nuova da proporre, o null se la pagina e' allineata. */
export function staleVersion(s: { loaded: string | null; server: string | null }): string | null {
  return s.loaded !== null && s.server !== null && s.server !== s.loaded ? s.server : null
}

export async function checkServerVersion(): Promise<void> {
  try {
    const r = await fetch('/api/ping', { cache: 'no-store' })
    if (!r.ok) return
    const j = await r.json()
    if (j && j.app === 'meshlens') noteServerVersion(j.version)
  } catch {
    // server non raggiungibile: si riprova alla prossima riconnessione
  }
}
