// Privacy della posizione (WP4): canali pubblici o inoltrati a MQTT con posizione troppo precisa.
import { getJSON, send } from './api'
import { locale, t, type MsgKey } from './i18n/index.svelte'
import type { ConfigPreview, PrivacyRadio } from './types'

export const getPrivacy = () => getJSON<{ radios: PrivacyRadio[] }>('/privacy')
export const previewPrivacyFix = (nodeId: string, bits: number, channels: number[] | null) =>
  send<ConfigPreview>('POST', `/privacy/${encodeURIComponent(nodeId)}/preview`, { bits, channels })

/** Precisioni proposte (bit): 14 ~ 1,5 km ... 10 ~ 23 km; 0 = non inviare la posizione. */
export const FIX_CHOICES = [14, 13, 12, 11, 10, 0] as const

/** Raggio di incertezza in metri (come coverage.precision_m del server). */
export function precisionMeters(bits: number): number | null {
  if (bits >= 32) return null
  return Math.round(2 ** (32 - bits) * 1e-7 * 111320 / 2)
}

/** "esatta" / "≈ 1,5 km" / "≈ 730 m" / "non inviata". */
export function precisionText(bits: number | null, m: number | null): string {
  if (bits === 0) return t('privacy.notSent')
  if (m === null || (bits !== null && bits >= 32)) return t('privacy.exact')
  if (m >= 1000) {
    const km = new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(m / 1000)
    return `≈ ${km} km`
  }
  return `≈ ${new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(m)} m`
}

export function reasonKey(r: string): MsgKey {
  return `privacy.reason.${r}` as MsgKey
}

export function radiosAtRisk(list: PrivacyRadio[]): PrivacyRadio[] {
  return list.filter((r) => r.risks.length > 0)
}
