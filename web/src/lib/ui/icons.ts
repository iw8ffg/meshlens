// Icone Lucide (ISC) importate una per una: niente barrel import, il bundle contiene solo queste.
import type { Component } from 'svelte'
import IMap from '@lucide/svelte/icons/map'
import IList from '@lucide/svelte/icons/list'
import INetwork from '@lucide/svelte/icons/network'
import ITarget from '@lucide/svelte/icons/target'
import IMessagesSquare from '@lucide/svelte/icons/messages-square'
import IRadio from '@lucide/svelte/icons/radio'
import ISlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal'
import IEllipsis from '@lucide/svelte/icons/ellipsis'
import ISearch from '@lucide/svelte/icons/search'
import IStar from '@lucide/svelte/icons/star'
import IBattery from '@lucide/svelte/icons/battery'
import IPlug from '@lucide/svelte/icons/plug'
import ISignal from '@lucide/svelte/icons/signal'
import ITriangleAlert from '@lucide/svelte/icons/triangle-alert'
import IBell from '@lucide/svelte/icons/bell'
import ICheck from '@lucide/svelte/icons/check'
import ICheckCheck from '@lucide/svelte/icons/check-check'
import IX from '@lucide/svelte/icons/x'
import IClock from '@lucide/svelte/icons/clock'
import IDownload from '@lucide/svelte/icons/download'
import IRefreshCw from '@lucide/svelte/icons/refresh-cw'
import ITrash2 from '@lucide/svelte/icons/trash-2'
import IPlus from '@lucide/svelte/icons/plus'
import IMinus from '@lucide/svelte/icons/minus'
import IChevronRight from '@lucide/svelte/icons/chevron-right'
import IChevronLeft from '@lucide/svelte/icons/chevron-left'
import IChevronDown from '@lucide/svelte/icons/chevron-down'
import IChevronUp from '@lucide/svelte/icons/chevron-up'
import ILock from '@lucide/svelte/icons/lock'
import IRoute from '@lucide/svelte/icons/route'
import ISend from '@lucide/svelte/icons/send'
import IUsb from '@lucide/svelte/icons/usb'
import IBluetooth from '@lucide/svelte/icons/bluetooth'
import ILayers from '@lucide/svelte/icons/layers'
import IFilter from '@lucide/svelte/icons/filter'
import ICopy from '@lucide/svelte/icons/copy'
import IEye from '@lucide/svelte/icons/eye'
import IKey from '@lucide/svelte/icons/key'
import IPower from '@lucide/svelte/icons/power'
import IInfo from '@lucide/svelte/icons/info'
import ICloudOff from '@lucide/svelte/icons/cloud-off'
import IMapPin from '@lucide/svelte/icons/map-pin'
import IArrowUpDown from '@lucide/svelte/icons/arrow-up-down'
import IUser from '@lucide/svelte/icons/user'
import IGlobe from '@lucide/svelte/icons/globe'
import IFlag from '@lucide/svelte/icons/flag'
import ILoader from '@lucide/svelte/icons/loader'
import IPencil from '@lucide/svelte/icons/pencil'
import IArrowLeft from '@lucide/svelte/icons/arrow-left'

export const ICONS = {
  map: IMap,
  nodes: IList,
  network: INetwork,
  coverage: ITarget,
  chat: IMessagesSquare,
  radio: IRadio,
  settings: ISlidersHorizontal,
  more: IEllipsis,
  search: ISearch,
  star: IStar,
  battery: IBattery,
  plug: IPlug,
  bars: ISignal,
  alert: ITriangleAlert,
  bell: IBell,
  check: ICheck,
  check2: ICheckCheck,
  x: IX,
  clock: IClock,
  download: IDownload,
  refresh: IRefreshCw,
  trash: ITrash2,
  plus: IPlus,
  minus: IMinus,
  chevR: IChevronRight,
  chevL: IChevronLeft,
  chevD: IChevronDown,
  chevU: IChevronUp,
  lock: ILock,
  route: IRoute,
  send: ISend,
  usb: IUsb,
  bt: IBluetooth,
  layers: ILayers,
  filter: IFilter,
  copy: ICopy,
  eye: IEye,
  key: IKey,
  power: IPower,
  info: IInfo,
  cloudoff: ICloudOff,
  pin: IMapPin,
  sort: IArrowUpDown,
  user: IUser,
  globe: IGlobe,
  flag: IFlag,
  spinner: ILoader,
  edit: IPencil,
  back: IArrowLeft,
} as const satisfies Record<string, Component<any>>

export type IconName = keyof typeof ICONS
