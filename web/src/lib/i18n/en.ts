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
// 1.6: aree dei pacchetti di lavoro (contratto §8.2)
import { search } from './en/search'
import { quick } from './en/quick'
import { onboarding } from './en/onboarding'
import { alertrules } from './en/alertrules'
import { sensors } from './en/sensors'
import { health } from './en/health'
import { layers } from './en/layers'
import { topology } from './en/topology'
import { tak } from './en/tak'
import { nodeflags } from './en/nodeflags'
import { profiles } from './en/profiles'
import { privacy } from './en/privacy'
import { channels } from './en/channels'
import { canned } from './en/canned'
import { tracesched } from './en/tracesched'
import { bot } from './en/bot'
import { retention } from './en/retention'
import { radiodiag } from './en/radiodiag'
import { whatsnew } from './en/whatsnew'
import { guest } from './en/guest'

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
  ...search,
  ...quick,
  ...onboarding,
  ...alertrules,
  ...sensors,
  ...health,
  ...layers,
  ...topology,
  ...tak,
  ...nodeflags,
  ...profiles,
  ...privacy,
  ...channels,
  ...canned,
  ...tracesched,
  ...bot,
  ...retention,
  ...radiodiag,
  ...whatsnew,
  ...guest,
}
