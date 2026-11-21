// Logica pura del guscio: schede, voci della barra in basso, larghezza del pannello.
import type { IconName } from '../ui/icons'

export type Tab = 'map' | 'nodes' | 'network' | 'coverage' | 'chat' | 'radio' | 'settings' | 'more'

/** Schede della barra superiore su desktop (la mappa è sempre visibile). */
export const DESKTOP_TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: 'nodes', label: 'Nodi', icon: 'nodes' },
  { id: 'network', label: 'Rete', icon: 'network' },
  { id: 'coverage', label: 'Copertura', icon: 'coverage' },
  { id: 'chat', label: 'Chat', icon: 'chat' },
  { id: 'radio', label: 'Radio', icon: 'radio' },
  { id: 'settings', label: 'Impostazioni', icon: 'settings' },
]

/** Barra in basso su telefono. */
export const PHONE_NAV: { id: Tab; label: string; icon: IconName }[] = [
  { id: 'map', label: 'Mappa', icon: 'map' },
  { id: 'nodes', label: 'Nodi', icon: 'nodes' },
  { id: 'chat', label: 'Chat', icon: 'chat' },
  { id: 'coverage', label: 'Copertura', icon: 'coverage' },
  { id: 'more', label: 'Altro', icon: 'more' },
]

/** Voci raccolte sotto «Altro». */
export const MORE_TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: 'network', label: 'Rete', icon: 'network' },
  { id: 'radio', label: 'Radio', icon: 'radio' },
  { id: 'settings', label: 'Impostazioni', icon: 'settings' },
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
