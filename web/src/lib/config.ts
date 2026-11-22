import type { ConfigDict, ConfigSchema, ConfigValue, SchemaField } from './types'
import { t, type MsgKey } from './i18n/index.svelte'
import { translateServer } from './i18n/server'

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

const NUMERIC = /^-?\d+(\.\d+)?$/

/** Uguaglianza che tratta come uguali un int64 stringa e il numero corrispondente ("123" e 123). */
function same(a: unknown, b: unknown): boolean {
  if (typeof a !== typeof b) {
    const [n, s] = typeof a === 'number' ? [a, b] : [b, a]
    if (typeof n === 'number' && typeof s === 'string' && NUMERIC.test(s)) return Number(s) === n
  }
  return JSON.stringify(a) === JSON.stringify(b)
}

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
    get label() { return t('config.tab.general') },
    fields: [
      { path: 'owner.long_name', get label() { return t('config.f.owner.long_name.label' as MsgKey) }, get help() { return t('config.f.owner.long_name.help' as MsgKey) } },
      { path: 'owner.short_name', get label() { return t('config.f.owner.short_name.label' as MsgKey) }, get help() { return t('config.f.owner.short_name.help' as MsgKey) } },
      { path: 'config.device.role', get label() { return t('config.f.config.device.role.label' as MsgKey) }, get help() { return t('config.f.config.device.role.help' as MsgKey) } },
    ],
  },
  {
    id: 'position',
    get label() { return t('config.tab.position') },
    fields: [
      { path: 'config.position.gps_mode', get label() { return t('config.f.config.position.gps_mode.label' as MsgKey) }, get help() { return t('config.f.config.position.gps_mode.help' as MsgKey) } },
      { path: 'config.position.position_broadcast_secs', get label() { return t('config.f.config.position.position_broadcast_secs.label' as MsgKey) }, get help() { return t('config.f.config.position.position_broadcast_secs.help' as MsgKey) } },
      { path: 'config.position.position_broadcast_smart_enabled', get label() { return t('config.f.config.position.position_broadcast_smart_enabled.label' as MsgKey) }, get help() { return t('config.f.config.position.position_broadcast_smart_enabled.help' as MsgKey) } },
      { path: 'config.position.broadcast_smart_minimum_interval_secs', get label() { return t('config.f.config.position.broadcast_smart_minimum_interval_secs.label' as MsgKey) }, get help() { return t('config.f.config.position.broadcast_smart_minimum_interval_secs.help' as MsgKey) } },
    ],
  },
  {
    id: 'telemetry',
    get label() { return t('config.tab.telemetry') },
    fields: [
      { path: 'module_config.telemetry.device_update_interval', get label() { return t('config.f.module_config.telemetry.device_update_interval.label' as MsgKey) }, get help() { return t('config.f.module_config.telemetry.device_update_interval.help' as MsgKey) } },
      { path: 'module_config.telemetry.environment_update_interval', get label() { return t('config.f.module_config.telemetry.environment_update_interval.label' as MsgKey) }, get help() { return t('config.f.module_config.telemetry.environment_update_interval.help' as MsgKey) } },
    ],
  },
  {
    id: 'lora',
    get label() { return t('config.tab.lora') },
    fields: [
      { path: 'config.lora.region', get label() { return t('config.f.config.lora.region.label' as MsgKey) }, get help() { return t('config.f.config.lora.region.help' as MsgKey) } },
      { path: 'config.lora.use_preset', get label() { return t('config.f.config.lora.use_preset.label' as MsgKey) }, get help() { return t('config.f.config.lora.use_preset.help' as MsgKey) } },
      { path: 'config.lora.modem_preset', get label() { return t('config.f.config.lora.modem_preset.label' as MsgKey) }, get help() { return t('config.f.config.lora.modem_preset.help' as MsgKey) } },
      { path: 'config.lora.hop_limit', get label() { return t('config.f.config.lora.hop_limit.label' as MsgKey) }, get help() { return t('config.f.config.lora.hop_limit.help' as MsgKey) } },
      { path: 'config.lora.tx_power', get label() { return t('config.f.config.lora.tx_power.label' as MsgKey) }, get help() { return t('config.f.config.lora.tx_power.help' as MsgKey) } },
      { path: 'config.lora.tx_enabled', get label() { return t('config.f.config.lora.tx_enabled.label' as MsgKey) }, get help() { return t('config.f.config.lora.tx_enabled.help' as MsgKey) } },
    ],
  },
  {
    id: 'modules',
    get label() { return t('config.tab.modules') },
    fields: [
      { path: 'module_config.range_test.enabled', get label() { return t('config.f.module_config.range_test.enabled.label' as MsgKey) }, get help() { return t('config.f.module_config.range_test.enabled.help' as MsgKey) } },
      { path: 'module_config.range_test.sender', get label() { return t('config.f.module_config.range_test.sender.label' as MsgKey) }, get help() { return t('config.f.module_config.range_test.sender.help' as MsgKey) } },
      { path: 'module_config.range_test.save', get label() { return t('config.f.module_config.range_test.save.label' as MsgKey) }, get help() { return t('config.f.module_config.range_test.save.help' as MsgKey) } },
      { path: 'module_config.neighbor_info.enabled', get label() { return t('config.f.module_config.neighbor_info.enabled.label' as MsgKey) }, get help() { return t('config.f.module_config.neighbor_info.enabled.help' as MsgKey) } },
      { path: 'module_config.neighbor_info.update_interval', get label() { return t('config.f.module_config.neighbor_info.update_interval.label' as MsgKey) }, get help() { return t('config.f.module_config.neighbor_info.update_interval.help' as MsgKey) } },
      { path: 'module_config.neighbor_info.transmit_over_lora', get label() { return t('config.f.module_config.neighbor_info.transmit_over_lora.label' as MsgKey) }, get help() { return t('config.f.module_config.neighbor_info.transmit_over_lora.help' as MsgKey) } },
    ],
  },
]

/** Testo del catalogo se la chiave esiste, altrimenti null (t() restituisce la chiave stessa se manca). */
function lookup(key: string): string | null {
  const text = t(key as MsgKey)
  return text === key ? null : text
}

/** Etichetta di un valore di enum nella lingua corrente; un valore senza voce resta com'e'. */
export function enumLabel(path: string, value: string): string {
  return lookup(`config.enum.${path}.${value}`) ?? value
}

export const CHANNEL_LABELS: Record<string, string> = {
  get role() { return t('config.ch.role') },
  get name() { return t('config.ch.name') },
  get psk() { return t('config.ch.psk') },
  get position_precision() { return t('config.ch.position_precision') },
  get uplink_enabled() { return t('config.ch.uplink_enabled') },
  get downlink_enabled() { return t('config.ch.downlink_enabled') },
}

/** Etichetta di un percorso nella lingua corrente, se nota. */
export function pathLabel(path: string): string {
  for (const t of SIMPLE_TABS) {
    const f = t.fields.find((x) => x.path === path)
    if (f) return f.label
  }
  const m = /^channels\.(\d+)\.(.+)$/.exec(path)
  if (m) return t('config.channelPath', { n: m[1], label: CHANNEL_LABELS[m[2]] ?? m[2] })
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
  if (owner.length) out.push({ key: 'owner', label: t('config.adv.owner'), fields: owner })
  for (const root of ['config', 'module_config'] as const) {
    for (const [sec, fields] of Object.entries(schema[root])) {
      const list = Object.entries(fields)
        .map(([name, field]) => ({ path: `${root}.${sec}.${name}`, name, field }))
        .filter((f) => !SIMPLE_PATHS.has(f.path))
      if (list.length) out.push({ key: `${root}.${sec}`, label: t(root === 'config' ? 'config.adv.config' : 'config.adv.module', { sec }), fields: list })
    }
  }
  return out
}

/** Testo di avanzamento "Lettura LoRa (3/25)…". */
export function jobText(step: string, progress: [number, number] | null): string {
  const text = translateServer(step)
  return progress ? `${text} (${progress[0]}/${progress[1]})…` : `${text}…`
}

export function backupReasonLabel(r: string): string {
  if (r === 'before_apply') return t('config.backup.beforeApply')
  if (r === 'coverage_prepare') return t('config.backup.coveragePrepare')
  return t('config.backup.manual')
}
