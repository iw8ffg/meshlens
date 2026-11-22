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
} as const
