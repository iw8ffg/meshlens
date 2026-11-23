// Testi inglesi: area «sensors» (WP2, Detection Sensor e Paxcounter). Il tipo obbliga a tradurre ogni chiave italiana.
import type { sensors as itArea } from '../it/sensors'

export const sensors: Record<keyof typeof itArea, string> = {
  'sensors.title': 'Sensor events',
  'sensors.detected': 'Detected',
  'sensors.cleared': 'Cleared',
  'sensors.hint.mqtt': 'The Detection Sensor does not arrive from public brokers',
  'sensors.pax.title': 'Paxcounter',
  'sensors.pax.wifi': 'Wi-Fi',
  'sensors.pax.ble': 'Bluetooth',
  'sensors.metric.paxcounter.wifi': 'Wi-Fi devices',
  'sensors.metric.paxcounter.ble': 'Bluetooth devices',
  'sensors.metric.paxcounter.uptime': 'Paxcounter uptime',
  'sensors.source.rf': 'Radio',
  'sensors.source.mqtt': 'MQTT',
  'sensors.loadFailed': 'Sensor events unavailable',
  'sensors.day.today': 'Today',
  'sensors.day.yesterday': 'Yesterday',
  'sensors.pax.aria': 'Trend of Wi-Fi and Bluetooth devices counted by the Paxcounter',
}
