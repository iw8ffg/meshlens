// Azioni dell'amministratore sugli avvisi: chiudere, riaprire i chiusi, accettare la nuova chiave.
// Il server pubblica comunque l'evento `alerts`: l'aggiornamento locale rende solo istantaneo il gesto.
import { acceptKey, alerts as fetchAlerts, dismissAlert, restoreAlerts } from './api'
import { withoutAlert, withoutKeyChanged } from './alerts'
import { app, setAlerts, upsertNodes } from './stores.svelte'

export async function dismiss(key: string): Promise<void> {
  const r = await dismissAlert(key)
  setAlerts(withoutAlert(app.alerts, key), r.hidden)
}

export async function restoreHidden(): Promise<void> {
  const r = await restoreAlerts()
  setAlerts(await fetchAlerts(), r.hidden)
}

export async function acceptNewKey(nodeId: string): Promise<void> {
  upsertNodes([await acceptKey(nodeId)])
  setAlerts(withoutKeyChanged(app.alerts, nodeId))
}
