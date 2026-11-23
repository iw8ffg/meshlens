// Primo avvio guidato e azioni negli stati vuoti (WP1: E1). Logica pura, senza DOM.
import type { Node, Radio } from './types'
import type { Tab } from './shell/nav'

export type StepId = 'source' | 'nodes' | 'maps'
export interface StepState {
  id: StepId
  done: boolean
}

/**
 * Stato dei tre passi della checklist: una sorgente dati (broker MQTT abilitato o una radio
 * configurata), almeno un nodo segnato come proprio, almeno una mappa offline (`mapCount` nullo =
 * sconosciuto, quindi non fatto).
 */
export function onboardingSteps(i: {
  brokers: { enabled: boolean }[]
  radios: Pick<Radio, 'state'>[]
  nodes: Pick<Node, 'is_mine'>[]
  mapCount: number | null
}): StepState[] {
  return [
    { id: 'source', done: i.brokers.some((b) => b.enabled) || i.radios.length > 0 },
    { id: 'nodes', done: i.nodes.some((n) => n.is_mine === true) },
    { id: 'maps', done: i.mapCount !== null && i.mapCount > 0 },
  ]
}

/** La guida si apre da sola solo con `onboarding_done === false` esplicito (errore o dato assente = niente) e se non e' stata chiusa in questa sessione. */
export function shouldAutoOpen(onboardingDone: boolean | undefined, closedThisSession: boolean): boolean {
  return onboardingDone === false && !closedThisSession
}

export type ActionKind = 'nodes' | 'network' | 'radios' | 'chat'
export interface ActionSpec {
  labelKey: 'onboarding.goRadio' | 'onboarding.goMqtt' | 'onboarding.openGuide'
  /** Scheda da aprire; `null` = apre la guida di avvio. */
  tab: Tab | null
}

const GO_RADIO: ActionSpec = { labelKey: 'onboarding.goRadio', tab: 'radio' }
const GO_MQTT: ActionSpec = { labelKey: 'onboarding.goMqtt', tab: 'settings' }
const GUIDE: ActionSpec = { labelKey: 'onboarding.openGuide', tab: null }

/** Pulsanti d'azione di uno stato vuoto. Una lista vuota per i filtri non va toccata: qui solo i casi «non c'e' ancora niente». */
export function emptyActions(
  kind: ActionKind,
  i: { nodeCount: number; radioCount: number; brokerCount: number; connectedRadios: number; convCount: number },
): ActionSpec[] {
  switch (kind) {
    case 'nodes':
    case 'network':
      return i.nodeCount === 0 ? [GO_RADIO, GO_MQTT, GUIDE] : []
    case 'radios':
      return [GUIDE, GO_MQTT]
    case 'chat':
      return i.convCount === 0 && i.connectedRadios === 0 && i.brokerCount === 0 ? [GO_RADIO, GO_MQTT] : []
  }
}
