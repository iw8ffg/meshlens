// Guardia contro i testi italiani rimasti nel markup: ogni componente .svelte che non e' in PENDING
// non deve contenere testo letterale (parole di almeno 3 lettere) fuori da <script> e <style>, ne'
// attributi aria-label / title / placeholder / label letterali. I testi passano da t() / tn().
// Chi migra un componente lo toglie da PENDING (un componente per riga, raggruppati per area).
import { describe, expect, it } from 'vitest'

// tutti i .svelte sotto src/, letti come testo (chiavi «/src/…»)
const SOURCES = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

/** Componenti non ancora migrati (percorsi relativi a src/, con «/»). Task 10 e 11 li tolgono. */
const PENDING = new Set<string>([
])

/** Parole o sigle che restano uguali in ogni lingua (nomi propri, protocolli, unita'). */
const ALLOW = [
  'MeshLens',
  'Meshtastic',
  'MQTT',
  'SNR',
  'RSSI',
  'LoRa',
  'PMTiles',
  'ITM',
  'NTIA',
  'USB',
  'BLE',
  'Italiano',
  'English',
  'PIN',
  'GPS',
  'TLS',
  'HTTPS',
  'HTTP',
  'URL',
  'JSON',
  'CSV',
  'GPX',
  'SHA',
  'DM',
  'msg',
  'dBm',
  'dB',
  'MHz',
  'kHz',
  'km',
  'min',
  'GeoJSON',
  'KML',
  'OpenStreetMap',
  'contributors',
  'Protomaps',
]
const ALLOW_RE = new RegExp(`\\b(?:${ALLOW.join('|')})\\b`, 'gi')

/** Rimuove i blocchi `{…}` di Svelte (anche annidati), lasciando un segnaposto neutro. */
export function stripMustaches(src: string): string {
  let out = ''
  let depth = 0
  for (const ch of src) {
    if (ch === '{') {
      if (depth === 0) out += '\u0001'
      depth++
    } else if (ch === '}') {
      if (depth > 0) depth--
      else out += ch
    } else if (depth === 0) out += ch
  }
  return out
}

function words(text: string): string[] {
  return (
    text
      .replace(/&[a-z]+;|&#\d+;/gi, ' ')
      .replace(ALLOW_RE, ' ')
      .match(/\p{L}{3,}/gu) ?? []
  )
}

const ATTR_RE = /\b(aria-label|title|placeholder|label)\s*=\s*"([^"]*)"/g

/** Frammenti di testo letterale del markup (testo fra i tag e attributi che si leggono). */
export function literalTexts(source: string): string[] {
  const markup = stripMustaches(
    source
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '')
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/g, '')
      .replace(/<!--[\s\S]*?-->/g, ''),
  )
  const found: string[] = []
  for (const m of markup.matchAll(ATTR_RE)) {
    const w = words(m[2])
    if (w.length) found.push(`${m[1]}="${m[2]}"`)
  }
  const text = markup.replace(/<[^>]*>/g, '\u0002')
  for (const part of text.split('\u0002')) {
    const w = words(part)
    if (w.length) found.push(part.replace(/\u0001/g, ' ').replace(/\s+/g, ' ').trim())
  }
  return found
}

describe('literalTexts', () => {
  it('trova testo e attributi letterali, ignora script, stile e segnaposto', () => {
    const src = `<script>const a = 'Ciao mondo'</script>
<button aria-label="Chiudi" title="{x}">Salva {n} cose</button>
<span>MQTT</span><b>{t('a.b')}</b><input placeholder="Cerca…" />
<style>.a { content: 'Testo' }</style>`
    expect(literalTexts(src)).toEqual(['aria-label="Chiudi"', 'placeholder="Cerca…"', 'Salva cose'])
  })
  it('un {…} annidato o con > dentro non spezza i tag', () => {
    expect(literalTexts(`<button onclick={() => go({ a: 1 })}>{t('x')}</button>`)).toEqual([])
  })
})

describe('nessun testo italiano nel markup dei componenti migrati', () => {
  const files = Object.keys(SOURCES).map((k) => k.slice('/src/'.length)).sort()

  it('PENDING contiene solo file che esistono', () => {
    for (const p of PENDING) expect(files, p).toContain(p)
  })

  it('PENDING e' vuoto: ogni componente e' stato migrato', () => {
    expect([...PENDING]).toEqual([])
  })

  for (const f of files.filter((x) => !PENDING.has(x))) {
    it(f, () => {
      const found = literalTexts(SOURCES['/src/' + f])
      expect(found, `testo letterale in ${f}: usa t() o tn()`).toEqual([])
    })
  }
})
