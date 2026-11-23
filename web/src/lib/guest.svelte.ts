// Ruolo della sessione corrente (E19). Impostato da App dopo /auth/status.
import type { Role } from './types'

export const session = $state({ role: 'admin' as Role })

export function setRole(role: Role | undefined): void {
  session.role = role === 'guest' ? 'guest' : 'admin'
}

/** Sessione ospite: guscio in sola lettura. */
export function isGuest(): boolean {
  return session.role === 'guest'
}
