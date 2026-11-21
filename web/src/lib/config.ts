import type { ConfigDict, ConfigSchema, ConfigValue, SchemaField } from './types'

export const MASK = '••••'

export type InputKind = 'select' | 'checkbox' | 'number' | 'text' | 'secret' | 'readonly'

/** Tipo di controllo da usare per un campo dello schema. */
export function fieldInput(f: SchemaField): InputKind {
  if (f.secret) return 'secret'
  switch (f.type) {
    case 'enum':
      return 'select'
    case 'bool':
      return 'checkbox'
    case 'int':
    case 'float':
      return 'number'
    case 'repeated':
      return 'readonly'
    default:
      return 'text'
  }
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

function diffSection(
  prefix: string,
  o: Record<string, ConfigValue> | undefined,
  e: Record<string, ConfigValue> | undefined,
  out: Record<string, unknown>,
): void {
  if (!e) return
  for (const [k, v] of Object.entries(e)) {
    if (v === MASK) continue // segreto invariato
    if (v === undefined) continue
    if (!same(o?.[k], v)) out[`${prefix}.${k}`] = v
  }
}

/** Solo i percorsi cambiati; i segreti mascherati invariati non compaiono mai. */
export function formChanges(original: ConfigDict, edited: ConfigDict): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  diffSection('owner', original.owner, edited.owner, out)
  for (const [sec, vals] of Object.entries(edited.config ?? {})) diffSection(`config.${sec}`, original.config?.[sec], vals, out)
  for (const [sec, vals] of Object.entries(edited.module_config ?? {}))
    diffSection(`module_config.${sec}`, original.module_config?.[sec], vals, out)
  for (const ch of edited.channels ?? []) {
    const o = original.channels?.find((c) => c.index === ch.index)
    diffSection(`channels.${ch.index}`, o as Record<string, ConfigValue> | undefined, ch as Record<string, ConfigValue>, out)
  }
  return out
}

/** Campo dello schema dal percorso puntato (owner.x, config.s.f, module_config.s.f, channels.i.f). */
export function schemaField(schema: ConfigSchema, path: string): SchemaField | undefined {
  const p = path.split('.')
  if (p[0] === 'owner') return schema.owner[p[1]]
  if (p[0] === 'config' || p[0] === 'module_config') return schema[p[0]][p[1]]?.[p[2]]
  if (p[0] === 'channels') return schema.channel[p[2]]
  return undefined
}

export function getPath(c: ConfigDict, path: string): ConfigValue {
  const p = path.split('.')
  if (p[0] === 'owner') return c.owner?.[p[1]]
  if (p[0] === 'config' || p[0] === 'module_config') return c[p[0]]?.[p[1]]?.[p[2]]
  if (p[0] === 'channels') return c.channels?.find((x) => x.index === Number(p[1]))?.[p[2]] as ConfigValue
  return undefined
}

export function setPath(c: ConfigDict, path: string, v: ConfigValue): void {
  const p = path.split('.')
  if (p[0] === 'owner') (c.owner ??= {})[p[1]] = v
  else if (p[0] === 'config' || p[0] === 'module_config') ((c[p[0]] ??= {})[p[1]] ??= {})[p[2]] = v
  else if (p[0] === 'channels') {
    const ch = c.channels?.find((x) => x.index === Number(p[1]))
    if (ch) ch[p[2]] = v
  }
}

export function cloneConfig(c: ConfigDict): ConfigDict {
  return JSON.parse(JSON.stringify(c))
}

export interface SimpleField {
  path: string
  label: string
  help?: string
}
export interface SimpleTab {
  id: string
  label: string
  fields: SimpleField[]
}

export const SIMPLE_TABS: SimpleTab[] = [
  {
    id: 'general',
    label: 'Generale',
    fields: [
      { path: 'owner.long_name', label: 'Nome lungo', help: 'Il nome mostrato agli altri nella rete.' },
      { path: 'owner.short_name', label: 'Nome breve', help: 'Fino a 4 caratteri, mostrato sugli schermi piccoli.' },
      { path: 'config.device.role', label: 'Ruolo del nodo', help: 'REPEATER fa solo da ripetitore: il nodo non è più usabile come client.' },
    ],
  },
  {
    id: 'position',
    label: 'Posizione',
    fields: [
      { path: 'config.position.gps_mode', label: 'Modalità GPS', help: 'Acceso, spento o assente.' },
      { path: 'config.position.position_broadcast_secs', label: 'Invio posizione (secondi)', help: 'Ogni quanto il nodo trasmette la posizione.' },
      { path: 'config.position.position_broadcast_smart_enabled', label: 'Invio intelligente', help: 'Trasmette più spesso solo se ti muovi.' },
      { path: 'config.position.broadcast_smart_minimum_interval_secs', label: 'Intervallo minimo intelligente (s)', help: 'Attesa minima tra due invii in modalità intelligente.' },
    ],
  },
  {
    id: 'telemetry',
    label: 'Telemetria',
    fields: [
      { path: 'module_config.telemetry.device_update_interval', label: 'Telemetria dispositivo (s)', help: 'Batteria, tensione, uso del canale.' },
      { path: 'module_config.telemetry.environment_update_interval', label: 'Telemetria ambientale (s)', help: 'Temperatura, umidità e simili.' },
    ],
  },
  {
    id: 'lora',
    label: 'LoRa',
    fields: [
      { path: 'config.lora.region', label: 'Regione', help: 'Deve corrispondere alla frequenza legale del tuo paese.' },
      { path: 'config.lora.use_preset', label: 'Usa preset', help: 'Se spento si usano i parametri radio manuali.' },
      { path: 'config.lora.modem_preset', label: 'Preset modem', help: 'Compromesso tra portata e velocità.' },
      { path: 'config.lora.hop_limit', label: 'Salti massimi', help: 'Quante volte un messaggio può essere ripetuto (max 7).' },
      { path: 'config.lora.tx_power', label: 'Potenza TX (dBm)', help: '0 = valore predefinito della regione.' },
      { path: 'config.lora.tx_enabled', label: 'Trasmissione attiva', help: 'Se spenta il nodo non trasmette più.' },
    ],
  },
  {
    id: 'modules',
    label: 'Moduli',
    fields: [
      { path: 'module_config.range_test.enabled', label: 'Range Test attivo', help: 'Abilita la prova di portata.' },
      { path: 'module_config.range_test.sender', label: 'Range Test: intervallo invio (s)', help: '0 = solo ricezione.' },
      { path: 'module_config.range_test.save', label: 'Range Test: salva sul nodo', help: 'Salva i risultati in un file sul nodo.' },
      { path: 'module_config.neighbor_info.enabled', label: 'NeighborInfo attivo', help: 'Condivide l’elenco dei vicini.' },
      { path: 'module_config.neighbor_info.update_interval', label: 'NeighborInfo: intervallo (s)', help: 'Minimo 14400 s su LoRa.' },
      { path: 'module_config.neighbor_info.transmit_over_lora', label: 'NeighborInfo via LoRa', help: 'Trasmette anche via radio, non solo MQTT.' },
    ],
  },
]

const ENUM_LABELS: Record<string, Record<string, string>> = {
  'config.device.role': {
    CLIENT: 'Client (predefinito)',
    CLIENT_MUTE: 'Client muto',
    ROUTER: 'Router',
    REPEATER: 'Ripetitore (rischioso)',
    TRACKER: 'Tracker',
    SENSOR: 'Sensore',
    CLIENT_HIDDEN: 'Client nascosto',
  },
  'config.position.gps_mode': { DISABLED: 'Spento', ENABLED: 'Acceso', NOT_PRESENT: 'Assente' },
  'config.lora.region': {
    UNSET: 'Non impostata',
    EU_433: 'Europa 433 MHz',
    EU_868: 'Europa 868 MHz',
    US: 'Stati Uniti',
    ANZ: 'Australia / Nuova Zelanda',
  },
  'config.lora.modem_preset': {
    LONG_FAST: 'Lunga distanza, veloce (predefinito)',
    LONG_SLOW: 'Lunga distanza, lento',
    MEDIUM_FAST: 'Media distanza, veloce',
    MEDIUM_SLOW: 'Media distanza, lento',
    SHORT_FAST: 'Corta distanza, veloce',
    SHORT_SLOW: 'Corta distanza, lento',
    LONG_MODERATE: 'Lunga distanza, moderato',
    SHORT_TURBO: 'Corta distanza, turbo',
  },
  'channel.role': { DISABLED: 'Disattivato', PRIMARY: 'Primario', SECONDARY: 'Secondario' },
}

export function enumLabel(path: string, value: string): string {
  return ENUM_LABELS[path]?.[value] ?? value
}

export const CHANNEL_LABELS: Record<string, string> = {
  role: 'Ruolo',
  name: 'Nome',
  psk: 'Chiave (psk)',
  position_precision: 'Precisione posizione',
  uplink_enabled: 'Uplink',
  downlink_enabled: 'Downlink',
}

/** Etichetta italiana di un percorso, se nota. */
export function pathLabel(path: string): string {
  for (const t of SIMPLE_TABS) {
    const f = t.fields.find((x) => x.path === path)
    if (f) return f.label
  }
  const m = /^channels\.(\d+)\.(.+)$/.exec(path)
  if (m) return `Canale ${m[1]} · ${CHANNEL_LABELS[m[2]] ?? m[2]}`
  return path
}

/** Percorsi gia' coperti dalle schede semplici. */
export const SIMPLE_PATHS = new Set(SIMPLE_TABS.flatMap((t) => t.fields.map((f) => f.path)))

/** Nuova psk casuale: 32 byte in base64. */
export function genPsk(): string {
  const b = new Uint8Array(32)
  crypto.getRandomValues(b)
  let s = ''
  for (const x of b) s += String.fromCharCode(x)
  return btoa(s)
}

export interface AdvField {
  path: string
  name: string
  field: SchemaField
}
export interface AdvSection {
  key: string
  label: string
  fields: AdvField[]
}

/** Sezioni avanzate: tutto cio' che non e' nelle schede semplici, raggruppato per sezione. */
export function advancedSections(schema: ConfigSchema): AdvSection[] {
  const out: AdvSection[] = []
  const owner = Object.entries(schema.owner)
    .map(([name, field]) => ({ path: `owner.${name}`, name, field }))
    .filter((f) => !SIMPLE_PATHS.has(f.path))
  if (owner.length) out.push({ key: 'owner', label: 'Proprietario', fields: owner })
  for (const root of ['config', 'module_config'] as const) {
    for (const [sec, fields] of Object.entries(schema[root])) {
      const list = Object.entries(fields)
        .map(([name, field]) => ({ path: `${root}.${sec}.${name}`, name, field }))
        .filter((f) => !SIMPLE_PATHS.has(f.path))
      if (list.length) out.push({ key: `${root}.${sec}`, label: `${root === 'config' ? 'Config' : 'Modulo'} · ${sec}`, fields: list })
    }
  }
  return out
}

/** Testo di avanzamento "Lettura LoRa (3/25)…". */
export function jobText(step: string, progress: [number, number] | null): string {
  return progress ? `${step} (${progress[0]}/${progress[1]})…` : `${step}…`
}

export function backupReasonLabel(r: string): string {
  if (r === 'before_apply') return 'Prima di una modifica'
  if (r === 'coverage_prepare') return 'Prima della prova di copertura'
  return 'Manuale'
}
