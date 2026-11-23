// Testi inglesi: area «nodeflags» (WP4, nodi ignorati e flag delle radio). Il tipo obbliga a tradurre ogni chiave italiana.
import type { nodeflags as itArea } from '../it/nodeflags'

export const nodeflags: Record<keyof typeof itArea, string> = {
  'nodeflags.ignore': 'Ignore node',
  'nodeflags.unignore': 'Stop ignoring',
  'nodeflags.confirmTitle': 'Ignore {name}?',
  'nodeflags.unconfirmTitle': 'Stop ignoring {name}?',
  'nodeflags.confirmText':
    'The node will be hidden from MeshLens map, lists and statistics, together with its messages and alerts. No data is deleted: restore it from Settings → Ignored nodes.',
  'nodeflags.unconfirmText': 'The node, its messages and its alerts will be visible again in MeshLens.',
  'nodeflags.alsoRadios': 'Also ignore on connected radios (the radio will drop its packets)',
  'nodeflags.alsoRadiosOff': 'Also remove the ignore flag on connected radios',
  'nodeflags.onRadio': 'On radio {name}',
  'nodeflags.favoriteOnRadio': 'Favorite on the radio',
  'nodeflags.ignoredOnRadio': 'Ignored on the radio',
  'nodeflags.help': 'Radio favorites and ignored nodes apply only to radios connected to this PC.',
  'nodeflags.radioFailed': 'The star was not copied to the radio: it stays in MeshLens',
  'nodeflags.radiosFailed': 'Radios not updated: {list}',
  'nodeflags.failed': 'Operation failed',
  'nodeflags.settings.title': 'Favorites and ignored nodes',
  'nodeflags.settings.toRadio': 'Also copy the star to connected radios',
  'nodeflags.settings.toRadioHelp':
    'When you mark a node as favorite, it is also marked favorite in the node list of the radios connected to this PC (the radio keeps it even after clearing its list).',
  'nodeflags.settings.ignoredTitle': 'Ignored nodes',
  'nodeflags.settings.ignoredHelp': 'Hidden from map, lists, messages and alerts. Restore them to bring them back: all their data is still here.',
  'nodeflags.settings.restore': 'Restore',
  'nodeflags.settings.empty': 'No ignored nodes',
  'nodeflags.settings.emptyHint': 'Use “Ignore node” in a node card to hide it.',
  'nodeflags.settings.loadFailed': 'Settings not available',
  'nodeflags.settings.saveFailed': 'Saving failed',
}
