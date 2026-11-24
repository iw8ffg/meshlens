// Diagnosi del collegamento radio (E20): tipi, passi concreti per ogni consiglio del server e
// chiamate a /api/radios/diagnose. Il server fa solo letture (porte, Bluetooth, rete).
import { send } from './api'
import type { MsgKey } from './i18n/index.svelte'
import type { RadioKind } from './types'

export type DiagStatus = 'ok' | 'warn' | 'fail' | 'skip'

export interface DiagCheck {
  check: string
  status: DiagStatus
  advice: string | null
  params: Record<string, unknown>
}

export interface Diagnosis {
  kind: RadioKind
  address: string
  checks: DiagCheck[]
  advice: string | null
  radio_state: string | null
}

export const ADVICE_CODES = [
  'usb_port_missing', 'usb_driver_missing', 'usb_port_busy', 'usb_unknown_chip', 'usb_not_meshtastic',
  'ble_off', 'ble_not_visible', 'ble_stale_pairing', 'ble_pair_needed', 'ble_connect_failed',
  'tcp_bad_address', 'tcp_not_found', 'tcp_refused', 'tcp_unreachable', 'tcp_not_meshtastic_or_busy',
  'in_use_by_meshlens', 'timeout',
] as const

const STEPS: Record<string, MsgKey[]> = {
  usb_port_missing: ['radiodiag.step.cable', 'radiodiag.step.otherPort', 'radiodiag.step.refreshPorts'],
  usb_port_busy: ['radiodiag.step.closeApps', 'radiodiag.step.closeSerial', 'radiodiag.step.replug'],
  usb_unknown_chip: ['radiodiag.step.rightPort', 'radiodiag.step.tryAnyway'],
  usb_not_meshtastic: ['radiodiag.step.firmware', 'radiodiag.step.dfu', 'radiodiag.step.replug'],
  ble_off: ['radiodiag.step.btOn', 'radiodiag.step.btAdapter'],
  ble_not_visible: ['radiodiag.step.bleNear', 'radiodiag.step.bleOtherDevice', 'radiodiag.step.bleEnabled'],
  ble_stale_pairing: ['radiodiag.step.bleRemovePair', 'radiodiag.step.blePairPin', 'radiodiag.step.bleConnect'],
  ble_pair_needed: ['radiodiag.step.bleAdd', 'radiodiag.step.blePairPin', 'radiodiag.step.bleConnect'],
  ble_connect_failed: ['radiodiag.step.bleNear', 'radiodiag.step.bleOtherDevice', 'radiodiag.step.bleRepair'],
  tcp_bad_address: ['radiodiag.step.tcpFormat', 'radiodiag.step.tcpIpv6'],
  tcp_not_found: ['radiodiag.step.tcpUseIp', 'radiodiag.step.tcpFindIp'],
  tcp_refused: ['radiodiag.step.tcpWifiOn', 'radiodiag.step.tcpPort'],
  tcp_unreachable: ['radiodiag.step.tcpSameNet', 'radiodiag.step.tcpFindIp', 'radiodiag.step.tcpFirewall'],
  tcp_not_meshtastic_or_busy: ['radiodiag.step.tcpOneClient', 'radiodiag.step.tcpPort'],
  in_use_by_meshlens: ['radiodiag.step.disconnectFirst', 'radiodiag.step.repeat'],
  timeout: ['radiodiag.step.repeat', 'radiodiag.step.replug'],
}
const DRIVER_STEPS: Record<string, MsgKey> = {
  CP210x: 'radiodiag.step.driverCp210x',
  CH340: 'radiodiag.step.driverCh340',
  'ESP32/native': 'radiodiag.step.driverEsp32',
  'Adafruit/Seeed': 'radiodiag.step.driverNrf',
}
const GENERIC: MsgKey[] = ['radiodiag.step.replug', 'radiodiag.step.restart']

/** Passi concreti (2-4) per il consiglio; il driver dipende dal chip USB rilevato. */
export function adviceSteps(code: string | null | undefined, params: Record<string, unknown> = {}): MsgKey[] {
  if (code === 'usb_driver_missing') {
    const chip = typeof params.chip === 'string' ? params.chip : ''
    const first = Object.hasOwn(DRIVER_STEPS, chip) ? DRIVER_STEPS[chip] : 'radiodiag.step.driverGeneric'
    return [first, 'radiodiag.step.replugAfterDriver', 'radiodiag.step.deviceManager']
  }
  return code && Object.hasOwn(STEPS, code) ? STEPS[code] : GENERIC
}

export function adviceTitleKey(code: string | null | undefined): MsgKey {
  return (code && (ADVICE_CODES as readonly string[]).includes(code)
    ? `radiodiag.advice.${code}`
    : 'radiodiag.advice.generic') as MsgKey
}

export function statusKind(status: string): 'ok' | 'warn' | 'danger' | 'neutral' {
  return status === 'ok' ? 'ok' : status === 'warn' ? 'warn' : status === 'fail' ? 'danger' : 'neutral'
}

export function statusLabelKey(status: string): MsgKey {
  return (['ok', 'warn', 'fail', 'skip'].includes(status) ? `radiodiag.status.${status}` : 'radiodiag.status.skip') as MsgKey
}

export const CHECKS = [
  'port_listed', 'usb_driver', 'port_open', 'meshtastic_probe', 'bt_adapter', 'ble_visible', 'ble_pairing',
  'address_valid', 'dns', 'tcp_connect', 'last_error', 'timeout',
] as const

export function checkLabelKey(check: string): MsgKey {
  return ((CHECKS as readonly string[]).includes(check) ? `radiodiag.check.${check}` : 'radiodiag.check.unknown') as MsgKey
}

/** Il server ha saltato i controlli di rete perche' la radio non e' salvata (M8: si
 * collega solo all'host:porta di una radio salvata): va salvata e la diagnosi ripetuta. */
export function needsSave(d: Diagnosis | null | undefined): boolean {
  return !!d?.checks.some((c) => c.params?.reason === 'not_saved')
}

export const diagnoseSaved =(radioId: string) =>
  send<Diagnosis>('POST', `/radios/${encodeURIComponent(radioId)}/diagnose`, {})
export const diagnoseAddress = (kind: RadioKind, address: string) =>
  send<Diagnosis>('POST', '/radios/diagnose', { kind, address })
