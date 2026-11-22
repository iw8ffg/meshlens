// Testi inglesi: area «common». Il tipo obbliga a tradurre ogni chiave italiana.
import type { common as itArea } from '../it/common'

export const common: Record<keyof typeof itArea, string> = {
  'common.never': 'never',
  'common.justNow': 'just now',
  'common.nowShort': 'now',
  'common.minAgo': '{n} min ago',
  'common.hourAgo': '{n} h ago',
  'common.dayAgo': '{n} d ago',
  'common.messages.one': '{n} message',
  'common.messages.other': '{n} messages',
  'common.retry': 'Retry',
  'common.close': 'Close',
  'common.confirm': 'Confirm',
  'common.cancel': 'Cancel',
  'common.riskAck': 'I understand and want to proceed',
  'common.unknownCountry': 'Unknown country',
  'common.sourceBoth': 'Radio and MQTT',
  'common.sheetResize': 'Drag to resize the panel',
  'common.sheetExpand': 'Expand the panel',
  'common.sheetClose': 'Close the panel',
  'common.sheetShrink': 'Shrink the panel',
}
