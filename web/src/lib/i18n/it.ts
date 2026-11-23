// Catalogo italiano (lingua predefinita): unisce i moduli per area di ./it/*.ts.
// Le chiavi nuove si aggiungono solo nel modulo della propria area.
import { nav } from './it/nav'
import { shell } from './it/shell'
import { common } from './it/common'
import { map } from './it/map'
import { nodes } from './it/nodes'
import { chat } from './it/chat'
import { coverage } from './it/coverage'
import { prediction } from './it/prediction'
import { sf } from './it/sf'
import { radios } from './it/radios'
import { config } from './it/config'
import { settings } from './it/settings'
import { maps } from './it/maps'
import { updates } from './it/updates'
import { login } from './it/login'
import { network } from './it/network'
import { packets } from './it/packets'
import { notify } from './it/notify'
import { waypoints } from './it/waypoints'
// 1.6: aree dei pacchetti di lavoro (contratto §8.2)
import { search } from './it/search'
import { quick } from './it/quick'
import { onboarding } from './it/onboarding'
import { alertrules } from './it/alertrules'
import { sensors } from './it/sensors'
import { health } from './it/health'
import { layers } from './it/layers'
import { topology } from './it/topology'
import { tak } from './it/tak'
import { nodeflags } from './it/nodeflags'
import { profiles } from './it/profiles'
import { privacy } from './it/privacy'
import { channels } from './it/channels'
import { canned } from './it/canned'
import { tracesched } from './it/tracesched'
import { bot } from './it/bot'
import { retention } from './it/retention'
import { radiodiag } from './it/radiodiag'
import { whatsnew } from './it/whatsnew'
import { guest } from './it/guest'

export const it = {
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
} as const
