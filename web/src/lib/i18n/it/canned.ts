// Testi italiani: area «canned» (WP4, messaggi predefiniti della radio). Chiavi `canned.*`.
export const canned = {
  'canned.err.empty': 'Serve almeno un messaggio',
  'canned.err.blank': 'I messaggi non possono essere vuoti',
  'canned.err.pipe': 'I messaggi non possono contenere il carattere |',
  'canned.err.control': 'I messaggi non possono contenere caratteri di controllo',
  'canned.err.tooLong': 'Troppo lunghi: oltre 200 byte (separatori compresi)',
} as const
