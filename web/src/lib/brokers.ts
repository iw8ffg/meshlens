import { maskedKeyLines, type Broker } from './settings'
import type { BrokerStatus } from './types'
import { t } from './i18n/index.svelte'
import { isWeak, keyKind } from './psk'

export const DEFAULT_BROKER_ID = 'default'
export const MAX_CHANNEL_BYTES = 11
export const MAX_BROKERS = 8
export const MAX_BROKER_CHANNELS = 16

const MASK = '••••'
const MASK_REF = /^••••#\d+$/

export function newBroker(): Broker {
  return {
    name: t('settings.br.newName'),
    enabled: true,
    host: '',
    port: 1883,
    tls: false,
    encryption: false,
    username: '',
    password: '',
    topics: ['msh/EU_868/#'],
    channels: [],
    extra_keys: [],
  }
}

/** Broker come arrivano dal server: le PSK mascherate diventano "••••#i" (i = posizione salvata),
 *  così restano riconoscibili se si cancella o si riordina un canale. */
export function fromServer(list: Broker[]): Broker[] {
  return list.map((b) => ({
    ...b,
    topics: [...b.topics],
    channels: b.channels.map((c, i) => ({ ...c, psk: c.psk === MASK ? `${MASK}#${i}` : c.psk })),
    extra_keys: maskedKeyLines(b.extra_keys),
  }))
}

const utf8 = new TextEncoder()

/** `others` = nomi degli altri canali dello stesso broker. */
export function channelNameError(name: string, others: string[]): string | null {
  const n = name.trim()
  const len = utf8.encode(n).length
  if (len < 1 || len > MAX_CHANNEL_BYTES) return t('settings.br.nameLen', { max: MAX_CHANNEL_BYTES })
  if (/[/#+]/.test(n)) return t('settings.br.nameChars')
  if (others.includes(n)) return t('settings.br.nameDup')
  return null
}

function b64Bytes(text: string): number | null {
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(text) || text.length % 4 !== 0) return null
  try {
    return atob(text).length
  } catch {
    return null
  }
}

export function pskError(psk: string): string | null {
  if (MASK_REF.test(psk) || psk === MASK) return null
  const n = b64Bytes(psk.trim())
  if (n === 1 || n === 16 || n === 32) return null
  return t('settings.br.pskBad')
}

/** Chiave che chiunque puo' usare: pubblica (AQ== e varianti di 1 byte), AA== o vuota. */
export function pskWeak(psk: string): boolean {
  return isWeak(keyKind(psk.trim()))
}

/** Passando da/a TLS la porta standard segue; le porte personalizzate restano. */
export function portFor(tls: boolean, port: number): number {
  if (tls && port === 1883) return 8883
  if (!tls && port === 8883) return 1883
  return port
}

export function isChannelLink(text: string): boolean {
  return /^https:\/\/meshtastic\.org\/e\/(\?[^#\s]*)?#[A-Za-z0-9_=-]+$/.test(text.trim())
}

/** Broker da preselezionare: il corrente se ancora attivo, poi il primo attivo connesso, poi il primo attivo. */
export function pickBroker(current: string, list: BrokerStatus[]): string {
  const active = list.filter((b) => b.enabled)
  if (active.some((b) => b.id === current)) return current
  return (active.find((b) => b.connected) ?? active[0])?.id ?? ''
}

/** Nome del broker da mostrare accanto a un messaggio: solo se ce ne sono almeno due attivi. */
export function brokerLabel(id: string | null | undefined, list: BrokerStatus[] | undefined): string | null {
  if (!id || !list || list.filter((b) => b.enabled).length < 2) return null
  return list.find((b) => b.id === id)?.name ?? null
}
