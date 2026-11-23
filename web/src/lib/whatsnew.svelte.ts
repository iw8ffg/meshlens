// Stato della finestra «Novità»: aperta dopo un aggiornamento (una volta per versione) o a
// richiesta da Impostazioni → Aggiornamenti.
import { fetchNotes, markSeen, type ReleaseNotes } from './whatsnew'

export const whatsNew = $state({ open: false, data: null as ReleaseNotes | null, seen: false })

/** All'avvio: mostra le novita' se il server lo chiede; installazione nuova -> registra in silenzio. */
export async function initWhatsNew(): Promise<void> {
  try {
    const data = await fetchNotes()
    whatsNew.data = data
    if (data.show) {
      whatsNew.open = true
    } else if (data.last_seen !== data.version) {
      await markSeen()
      whatsNew.seen = true
    }
  } catch {
    /* accessorio: nessuna finestra */
  }
}

/** Da Impostazioni: le note della versione corrente, sempre. */
export async function requestWhatsNew(): Promise<void> {
  const data = await fetchNotes(true)
  whatsNew.data = data
  whatsNew.open = data.releases.length > 0
}

/** Chiusura: la versione corrente risulta vista (una sola volta). */
export async function closeWhatsNew(): Promise<void> {
  whatsNew.open = false
  if (whatsNew.seen) return
  whatsNew.seen = true
  try {
    await markSeen()
  } catch {
    whatsNew.seen = false
  }
}
