// Catalogo inglese: unisce i moduli per area di ./en/*.ts. Ogni modulo e' tipizzato sulla propria
// area italiana, e il tipo di `en` obbliga ad avere ogni chiave di `it`.
import type { MsgKey } from './index.svelte'
import { nav } from './en/nav'
import { shell } from './en/shell'
import { common } from './en/common'
import { map } from './en/map'
import { nodes } from './en/nodes'
import { chat } from './en/chat'
import { coverage } from './en/coverage'
import { prediction } from './en/prediction'
import { sf } from './en/sf'
import { radios } from './en/radios'
import { config } from './en/config'
import { settings } from './en/settings'
import { maps } from './en/maps'
import { updates } from './en/updates'
import { login } from './en/login'
import { network } from './en/network'
import { packets } from './en/packets'
import { notify } from './en/notify'
import { waypoints } from './en/waypoints'

export const en: Record<MsgKey, string> = {
  ...nav,
  ...shell,
  ...common,
  ...map,
  ...nodes,
  ...chat,
  ...coverage,
  ...prediction,
  ...sf,
  ...radios,
  ...config,
  ...settings,
  ...maps,
  ...updates,
  ...login,
  ...network,
  ...packets,
  ...notify,
  ...waypoints,
}
