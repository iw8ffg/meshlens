// Stato dell'avvio guidato (WP1): finestra aperta/chiusa e chiusura per la sessione.
import { send } from './api'
import { translateServer } from './i18n/server'

export const onboardingUi = $state({ open: false, closedThisSession: false, saving: false, error: null as string | null })

export function openOnboarding(): void {
  onboardingUi.error = null
  onboardingUi.open = true
}

/** Chiude fino al prossimo avvio dell'app: non scrive nulla. */
export function closeOnboarding(): void {
  onboardingUi.open = false
  onboardingUi.closedThisSession = true
}

/** «Non mostrare più»: salva `onboarding_done` e chiude; un errore lascia la guida aperta con il messaggio. */
export async function finishOnboarding(): Promise<void> {
  onboardingUi.saving = true
  onboardingUi.error = null
  try {
    await send('PUT', '/settings', { onboarding_done: true })
    closeOnboarding()
  } catch (e) {
    onboardingUi.error = translateServer(e instanceof Error ? e.message : String(e))
  } finally {
    onboardingUi.saving = false
  }
}
