// Messaggi di errore del server (sempre in italiano): in inglese si traducono con il catalogo
// server-en.json, prima per testo esatto, poi con i modelli (regex con $1, $2…) per le parti variabili.
// Un testo senza corrispondenza resta in italiano.
import catalog from './server-en.json'
import { i18n } from './index.svelte'

interface Catalog {
  exact: Record<string, string>
  patterns: [string, string][]
}
const cat = catalog as unknown as Catalog
let compiled: [RegExp, string][] | null = null

function patterns(): [RegExp, string][] {
  if (!compiled) {
    compiled = []
    for (const [src, repl] of cat.patterns) {
      try {
        compiled.push([new RegExp(src), repl])
      } catch {
        // modello non valido: ignorato, il testo resta in italiano
      }
    }
  }
  return compiled
}

export function translateServer(msg: string): string {
  if (i18n.lang === 'it' || !msg) return msg
  const exact = Object.hasOwn(cat.exact, msg) ? cat.exact[msg] : undefined
  if (exact !== undefined) return exact
  for (const [re, repl] of patterns()) {
    if (re.test(msg)) return msg.replace(re, repl)
  }
  return msg
}
