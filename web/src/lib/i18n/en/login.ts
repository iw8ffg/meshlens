// Testi inglesi: area «login». Il tipo obbliga a tradurre ogni chiave italiana.
import type { login as itArea } from '../it/login'

export const login: Record<keyof typeof itArea, string> = {
  'login.mismatch': 'The two PINs do not match',
  'login.tooMany': 'Too many attempts',
  'login.tooManyLater': 'Too many attempts: try again in a few minutes',
  'login.wrong': 'Wrong PIN',
  'login.error': 'Login error',
  'login.remoteTitle': 'Set up MeshLens from the PC',
  'login.remoteBody': 'The first PIN is chosen on the computer MeshLens is running on.',
  'login.setupTitle': 'Choose a PIN',
  'login.enterTitle': 'Enter the PIN',
  'login.setupSub': '{min} to 12 digits. You will need it to open MeshLens from this and other devices.',
  'login.pin': 'PIN',
  'login.hint': '4 to 12 digits',
  'login.repeat': 'Repeat the PIN',
  'login.verifying': 'Checking…',
  'login.retryIn': 'Try again in {n} s',
  'login.set': 'Set PIN',
  'login.enter': 'Log in',
  'login.retryBanner': 'Try again in {n} seconds.',
}
