import type { UpdateJob, UpdateStatus } from './types'

/** Riga di sintesi dello stato aggiornamenti. */
export function updateLabel(s: UpdateStatus | null): string {
  if (!s) return 'Non ancora controllato'
  if (s.error) return s.error
  if (s.available && s.latest) return `Disponibile MeshLens ${s.latest}`
  if (s.latest === null && s.checked_at === null) return 'Non ancora controllato'
  return 'MeshLens è aggiornato'
}

/** L'installazione e' possibile solo con aggiornamento disponibile, download completato e versione installata. */
export function canInstall(s: UpdateStatus | null, job: UpdateJob | null): boolean {
  return !!s && s.available && s.can_install && job?.status === 'done'
}
