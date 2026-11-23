// Testi italiani: area «sensori» (WP2, Detection Sensor e Paxcounter). Chiavi `sensors.*`.
export const sensors = {
  'sensors.title': 'Eventi del sensore',
  'sensors.detected': 'Rilevato',
  'sensors.cleared': 'Cessato',
  'sensors.hint.mqtt': 'Il Detection Sensor non arriva dai broker pubblici',
  'sensors.pax.title': 'Paxcounter',
  'sensors.pax.wifi': 'Wi-Fi',
  'sensors.pax.ble': 'Bluetooth',
  'sensors.metric.paxcounter.wifi': 'Dispositivi Wi-Fi',
  'sensors.metric.paxcounter.ble': 'Dispositivi Bluetooth',
  'sensors.metric.paxcounter.uptime': 'Uptime del Paxcounter',
  'sensors.source.rf': 'Radio',
  'sensors.source.mqtt': 'MQTT',
  'sensors.loadFailed': 'Eventi del sensore non disponibili',
  'sensors.day.today': 'Oggi',
  'sensors.day.yesterday': 'Ieri',
  'sensors.pax.aria': 'Andamento dei dispositivi Wi-Fi e Bluetooth contati dal Paxcounter',
} as const
