// Testi inglesi: area «whatsnew» (WP5, novità della versione). Il tipo obbliga a tradurre ogni chiave italiana.
import type { whatsnew as itArea } from '../it/whatsnew'

export const whatsnew: Record<keyof typeof itArea, string> = {
  'whatsnew.title': 'What’s new in MeshLens',
  'whatsnew.version': 'Version {v}',
  'whatsnew.versionDate': 'Version {v} of {date}',
  'whatsnew.ok': 'Got it',
  'whatsnew.close': 'Close',
  'whatsnew.open': 'What’s new in this version',
  'whatsnew.failed': 'Release notes not available',
}
