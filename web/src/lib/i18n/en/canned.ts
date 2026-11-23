// Testi inglesi: area «canned» (WP4, messaggi predefiniti della radio). Il tipo obbliga a tradurre ogni chiave italiana.
import type { canned as itArea } from '../it/canned'

export const canned: Record<keyof typeof itArea, string> = {
  'canned.err.empty': 'At least one message is required',
  'canned.err.blank': 'Messages cannot be empty',
  'canned.err.pipe': 'Messages cannot contain the | character',
  'canned.err.control': 'Messages cannot contain control characters',
  'canned.err.tooLong': 'Too long: over 200 bytes (separators included)',
  'canned.failed': "Canned messages not available",
  'canned.title': "Canned messages",
  'canned.note': "Used by T-Deck, T-Pager and radios with a keyboard or rotary encoder; MeshLens handles the | separator. If the module is off on the radio, the messages stay saved but are not shown.",
  'canned.read': "Read from the radio",
  'canned.useQuick': "Use my quick replies",
  'canned.quickTruncated': "Took {n} of {total} quick replies: the others do not fit in 200 bytes",
  'canned.item': "Message {n}",
  'canned.up': "Move up",
  'canned.down': "Move down",
  'canned.remove': "Remove",
  'canned.add': "Add message",
  'canned.bytes': "{n} / {max} bytes",
  'canned.write': "Write to the radio",
  'canned.written': "Messages written to the radio",
}
