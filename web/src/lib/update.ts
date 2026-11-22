import type { UpdateJob, UpdateStatus } from './types'
import { t } from './i18n/index.svelte'
import { translateServer } from './i18n/server'

/** Riga di sintesi dello stato aggiornamenti. */
export function updateLabel(s: UpdateStatus | null): string {
  if (!s) return t('updates.label.never')
  if (s.error) return translateServer(s.error)
  if (s.available && s.latest) return t('updates.label.available', { v: s.latest })
  if (s.latest === null && s.checked_at === null) return t('updates.label.never')
  return t('updates.label.current')
}

/** L'installazione e' possibile solo con aggiornamento disponibile, download completato e versione installata. */
export function canInstall(s: UpdateStatus | null, job: UpdateJob | null): boolean {
  return !!s && s.available && s.can_install && job?.status === 'done'
}

/** Quando il download passa a "completato" lo stato del server cambia (can_install): va riletto. */
export function shouldReloadStatus(prev: UpdateJob | null, next: UpdateJob): boolean {
  return next.status === 'done' && prev?.status !== 'done'
}
