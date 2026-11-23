// Testi inglesi: area «privacy» (WP4, privacy). Il tipo obbliga a tradurre ogni chiave italiana.
import type { privacy as itArea } from '../it/privacy'

export const privacy: Record<keyof typeof itArea, string> = {
  'privacy.exact': 'exact',
  'privacy.notSent': 'not sent',
  'privacy.reason.no_key': 'channel without encryption',
  'privacy.reason.public_key': 'default public key: anyone with the app reads the channel',
  'privacy.reason.mqtt_uplink': 'the channel is forwarded to MQTT',
  'privacy.reason.mqtt_map': 'the radio publishes its position on the MQTT map',
}
