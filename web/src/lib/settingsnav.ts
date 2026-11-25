// Navigazione rapida della scheda Impostazioni: elenco delle sezioni, filtro e sezione attiva.
import type { MsgKey } from './i18n/index.svelte'

export interface SettingsSection {
  id: string
  labelKey: MsgKey
  /** vero se la sezione compare solo dopo il caricamento delle impostazioni dal server */
  needsLoaded: boolean
}

/** Sezioni nell'ordine in cui compaiono nella pagina. Gli id coincidono con quelli della ricerca globale. */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  { id: 'appearance', labelKey: 'settings.appearance', needsLoaded: false },
  { id: 'countries', labelKey: 'settings.nav.countries', needsLoaded: true },
  { id: 'retention', labelKey: 'settings.retention', needsLoaded: true },
  { id: 'db', labelKey: 'settings.db.title', needsLoaded: true },
  { id: 'alerts', labelKey: 'settings.nav.alerts', needsLoaded: true },
  { id: 'notify', labelKey: 'notify.title', needsLoaded: true },
  { id: 'quick', labelKey: 'quick.title', needsLoaded: true },
  { id: 'alertrules', labelKey: 'alertrules.title', needsLoaded: true },
  { id: 'automations', labelKey: 'settings.nav.automations', needsLoaded: true },
  { id: 'net', labelKey: 'settings.net.title', needsLoaded: true },
  { id: 'dev', labelKey: 'settings.dev.title', needsLoaded: true },
  { id: 'guest', labelKey: 'guest.card.title', needsLoaded: true },
  { id: 'ignored', labelKey: 'nodeflags.settings.title', needsLoaded: true },
  { id: 'mqtt', labelKey: 'settings.mqtt.title', needsLoaded: true },
  { id: 'chan', labelKey: 'settings.nav.chan', needsLoaded: true },
  { id: 'maps', labelKey: 'maps.title', needsLoaded: true },
  { id: 'updates', labelKey: 'updates.title', needsLoaded: true },
  { id: 'diag', labelKey: 'settings.diag.title', needsLoaded: false },
  { id: 'about', labelKey: 'settings.about.title', needsLoaded: false },
]

/** Sezioni effettivamente presenti: prima del caricamento (o se fallito) solo quelle sempre visibili. */
export function visibleSections(loaded: boolean): SettingsSection[] {
  return SETTINGS_SECTIONS.filter((s) => loaded || !s.needsLoaded)
}

export const sectionDomId = (id: string) => `set-${id}`

/**
 * Sezione attiva: l'ultima la cui cima ha superato la linea di lettura (`line`, in px dal bordo
 * superiore dell'area); se nessuna l'ha superata, la prima. `tops` e' nell'ordine della pagina.
 */
export function pickActive(tops: { id: string; top: number }[], line: number): string | null {
  if (!tops.length) return null
  let cur = tops[0].id
  for (const s of tops) if (s.top <= line) cur = s.id
  return cur
}

// Richiesta di salto da fuori (ricerca globale): la scheda puo' non essere ancora montata.
let pending: string | null = null
export const JUMP_EVENT = 'meshlens:settings-jump'

export function requestSettingsJump(id: string): void {
  pending = id
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(JUMP_EVENT))
}

export function takeSettingsJump(): string | null {
  const id = pending
  pending = null
  return id
}
