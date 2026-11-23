// Testi inglesi: area «onboarding» (WP1, avvio guidato). Il tipo obbliga a tradurre ogni chiave italiana.
import type { onboarding as itArea } from '../it/onboarding'

export const onboarding: Record<keyof typeof itArea, string> = {
  'onboarding.title': 'Getting started with MeshLens',
  'onboarding.intro': 'Three steps to see your network: a data source, your nodes and offline maps. You can skip them and reopen this guide any time from Ctrl+K.',
  'onboarding.step.source.title': 'A data source',
  'onboarding.step.source.body': 'Connect a Meshtastic radio to this computer, or turn on an MQTT broker to receive the network without a radio.',
  'onboarding.step.nodes.title': 'Your nodes',
  'onboarding.step.nodes.body': 'Open the node list, tap a node and mark it as yours: alerts and statistics will use it.',
  'onboarding.step.maps.title': 'Offline maps',
  'onboarding.step.maps.body': 'Download the maps of your area: they stay available without internet.',
  'onboarding.done': 'Done',
  'onboarding.todo': 'To do',
  'onboarding.goRadio': 'Connect a radio',
  'onboarding.goMqtt': 'Set up MQTT',
  'onboarding.goNodes': 'See the nodes',
  'onboarding.goMaps': 'Offline maps',
  'onboarding.openGuide': 'Getting started guide',
  'onboarding.allDone': 'All set',
  'onboarding.finish': 'Done',
  'onboarding.close': 'Close',
  'onboarding.dismiss': 'Don\'t show again',
  'onboarding.saveError': 'Could not save your choice',
}
