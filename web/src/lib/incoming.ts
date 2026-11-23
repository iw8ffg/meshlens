import { safeStorage } from './storage'
import { localNodeIds } from './chat'
import { loadNotifyPrefs, shouldNotify } from './notify'
import { navigate } from './shell/navigate'
import { app, openChat } from './stores.svelte'
import { t } from './i18n/index.svelte'
import { getActiveConv, noteIncoming } from './unread.svelte'
import type { Message } from './types'

/** Messaggio nuovo dal WebSocket: aggiorna i non letti e, per i diretti a scheda nascosta, notifica. */
export function onIncoming(m: Message): void {
  const visible = document.visibilityState === 'visible'
  const key = noteIncoming(m, localNodeIds(app.radios), getActiveConv(), visible)
  if (key === null) return
  const permission = typeof Notification === 'undefined' ? 'denied' : Notification.permission
  if (!shouldNotify(m, key, loadNotifyPrefs(safeStorage()), permission, !visible)) return
  try {
    const n = new Notification(t('chat.dmNotifyTitle', { name: m.from_name || m.from }), { body: m.text, tag: key })
    n.onclick = () => {
      window.focus()
      openChat(key)
      navigate('chat')
      n.close()
    }
  } catch {
    /* notifica non creabile (es. contesto non sicuro): ignorata */
  }
}
