// Testi inglesi: area «canned» (WP4, messaggi predefiniti della radio). Il tipo obbliga a tradurre ogni chiave italiana.
import type { canned as itArea } from '../it/canned'

export const canned: Record<keyof typeof itArea, string> = {
  'canned.err.empty': 'At least one message is required',
  'canned.err.blank': 'Messages cannot be empty',
  'canned.err.pipe': 'Messages cannot contain the | character',
  'canned.err.control': 'Messages cannot contain control characters',
  'canned.err.tooLong': 'Too long: over 200 bytes (separators included)',
}
