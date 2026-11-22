// Logica pura del guscio: schede, voci della barra in basso, larghezza del pannello.
import type { IconName } from '../ui/icons'
import type { MsgKey } from '../i18n/index.svelte'

export type Tab = 'map' | 'nodes' | 'network' | 'coverage' | 'chat' | 'radio' | 'settings' | 'more'

/** Schede della barra superiore su desktop (la mappa è sempre visibile). */
export const DESKTOP_TABS: { id: Tab; labelKey: MsgKey; icon: IconName }[] = [
  { id: 'nodes', labelKey: 'nav.nodes', icon: 'nodes' },
  { id: 'network', labelKey: 'nav.network', icon: 'network' },
  { id: 'coverage', labelKey: 'nav.coverage', icon: 'coverage' },
  { id: 'chat', labelKey: 'nav.chat', icon: 'chat' },
  { id: 'radio', labelKey: 'nav.radio', icon: 'radio' },
  { id: 'settings', labelKey: 'nav.settings', icon: 'settings' },
]

/** Barra in basso su telefono. */
export const PHONE_NAV: { id: Tab; labelKey: MsgKey; icon: IconName }[] = [
  { id: 'map', labelKey: 'nav.map', icon: 'map' },
  { id: 'nodes', labelKey: 'nav.nodes', icon: 'nodes' },
  { id: 'chat', labelKey: 'nav.chat', icon: 'chat' },
  { id: 'coverage', labelKey: 'nav.coverage', icon: 'coverage' },
  { id: 'more', labelKey: 'nav.more', icon: 'more' },
]

/** Voci raccolte sotto «Altro». */
export const MORE_TABS: { id: Tab; labelKey: MsgKey; icon: IconName }[] = [
  { id: 'network', labelKey: 'nav.network', icon: 'network' },
  { id: 'radio', labelKey: 'nav.radio', icon: 'radio' },
  { id: 'settings', labelKey: 'nav.settings', icon: 'settings' },
]

/** Pagine lunghe: su desktop occupano tutta l'area sotto la barra. */
export const PAGE_TABS: readonly Tab[] = ['network', 'settings']

export function isMoreTab(t: Tab): boolean {
  return MORE_TABS.some((m) => m.id === t)
}

/** Scheda effettiva: su desktop «Mappa» e «Altro» non esistono come schede. */
export function effectiveTab(tab: Tab, phone: boolean): Tab {
  if (phone) return tab
  return tab === 'map' || tab === 'more' ? 'nodes' : tab
}

/** Voce evidenziata nella barra in basso: le sottovoci di «Altro» accendono «Altro». */
export function navActive(tab: Tab): Tab {
  return isMoreTab(tab) ? 'more' : tab
}

export function isPageTab(tab: Tab): boolean {
  return PAGE_TABS.includes(tab)
}

/** Su telefono: il pannello (Sheet) è visibile se non si è sulla mappa o c'è un nodo selezionato. */
export function sheetVisible(tab: Tab, hasSelection: boolean): boolean {
  return tab !== 'map' || hasSelection
}

export const PANEL_MIN = 320
export const PANEL_MAX = 560
export const PANEL_DEFAULT = 380
export const PANEL_KEY = 'meshlens.panelWidth'

export function clampPanelWidth(w: number): number {
  if (!Number.isFinite(w)) return PANEL_DEFAULT
  return Math.min(PANEL_MAX, Math.max(PANEL_MIN, Math.round(w)))
}

export function loadPanelWidth(storage: Pick<Storage, 'getItem'> | null): number {
  try {
    const raw = storage?.getItem(PANEL_KEY)
    if (raw == null) return PANEL_DEFAULT
    return clampPanelWidth(Number(raw))
  } catch {
    return PANEL_DEFAULT
  }
}

export function savePanelWidth(storage: Pick<Storage, 'setItem'> | null, w: number): void {
  try {
    storage?.setItem(PANEL_KEY, String(clampPanelWidth(w)))
  } catch {
    // localStorage non disponibile: la larghezza vale solo per questa sessione
  }
}
