// «Novità» dopo un aggiornamento (E18): tipi, lettura sicura del Markdown del CHANGELOG (mai HTML:
// il testo si rende come testo) e chiamate a /api/update/notes e /api/update/seen.
import { getJSON, send } from './api'
import type { Lang } from './i18n/index.svelte'

export interface ReleaseNote {
  version: string
  date: string | null
  it: string
  en: string
}

export interface ReleaseNotes {
  version: string
  last_seen: string
  show: boolean
  releases: ReleaseNote[]
}

export interface BlockPart {
  text: string
  bold: boolean
}

export interface Block {
  type: 'h' | 'li' | 'p'
  parts: BlockPart[]
}

function parts(line: string): BlockPart[] {
  const clean = line.replace(/`/g, '')
  const out: BlockPart[] = []
  clean.split('**').forEach((text, i) => {
    if (text !== '') out.push({ text, bold: i % 2 === 1 })
  })
  return out
}

/** Titoli `###`/`####`, elenchi `- `/`* `, paragrafi; `**grassetto**`; backtick tolti. */
export function parseNotes(md: string): Block[] {
  const blocks: Block[] = []
  for (const raw of (md ?? '').split(/\r?\n/)) {
    const line = raw.trim()
    if (line === '') continue
    const h = /^#{2,6}\s+(.*)$/.exec(line)
    if (h) {
      blocks.push({ type: 'h', parts: parts(h[1]) })
      continue
    }
    const li = /^[-*]\s+(.*)$/.exec(line)
    if (li) {
      blocks.push({ type: 'li', parts: parts(li[1]) })
      continue
    }
    blocks.push({ type: 'p', parts: parts(line) })
  }
  return blocks
}

/** Testo nella lingua scelta; se manca, quello dell'altra lingua. */
export function pickLang(release: Pick<ReleaseNote, 'it' | 'en'>, lang: Lang): string {
  const first = lang === 'en' ? release.en : release.it
  return first || (lang === 'en' ? release.it : release.en) || ''
}

export const fetchNotes = (force = false) => getJSON<ReleaseNotes>(`/update/notes${force ? '?force=1' : ''}`)
export const markSeen = () => send<{ last_seen_version: string }>('POST', '/update/seen', {})
