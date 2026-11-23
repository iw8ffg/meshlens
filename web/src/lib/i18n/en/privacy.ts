// Testi inglesi: area «privacy» (WP4, privacy). Il tipo obbliga a tradurre ogni chiave italiana.
import type { privacy as itArea } from '../it/privacy'

export const privacy: Record<keyof typeof itArea, string> = {
  'privacy.exact': 'exact',
  'privacy.notSent': 'not sent',
  'privacy.reason.no_key': 'channel without encryption',
  'privacy.reason.public_key': 'default public key: anyone with the app reads the channel',
  'privacy.reason.mqtt_uplink': 'the channel is forwarded to MQTT',
  'privacy.reason.mqtt_map': 'the radio publishes its position on the MQTT map',
  'privacy.failed': "Fix not available",
  'privacy.title': "Position too precise on radio {name}",
  'privacy.titleCompact': "Position too precise on a public channel",
  'privacy.channel': "Channel {n} ({name})",
  'privacy.current': "current precision: {value}",
  'privacy.fix.choice': "New precision",
  'privacy.fix.button': "Fix",
  'privacy.fix.off': "do not send the position on this channel",
  'privacy.mapReport': "MQTT map",
  'privacy.mapReportHelp': "Reduce the map report precision from the MQTT module in the Meshtastic app or in the Advanced tab.",
  'privacy.open': "Open the fix",
}
