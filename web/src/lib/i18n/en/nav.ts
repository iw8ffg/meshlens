// Testi inglesi: area «nav». Il tipo obbliga a tradurre ogni chiave italiana.
import type { nav as itArea } from '../it/nav'

export const nav: Record<keyof typeof itArea, string> = {
  'nav.map': 'Map',
  'nav.nodes': 'Nodes',
  'nav.network': 'Network',
  'nav.coverage': 'Coverage',
  'nav.chat': 'Messages',
  'nav.radio': 'Radio',
  'nav.settings': 'Settings',
  'nav.more': 'More',
  'nav.sections': 'Sections',
}
