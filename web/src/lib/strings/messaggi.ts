import { t } from '../i18n/index.svelte'

/**
 * Residuo: i testi della schermata Messaggi stanno ora nel catalogo (`chat.*`). Resta solo questa voce,
 * ancora letta dalle Impostazioni → Notifiche (Task 11); si elimina quando quel componente passa a t().
 */
export const T = {
  get notifyUnsupported(): string {
    return t('chat.notifyUnsupported')
  },
}
