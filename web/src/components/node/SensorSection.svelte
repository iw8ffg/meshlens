<script lang="ts">
  // Eventi del Detection Sensor di un nodo, raggruppati per giorno. Nessun markup senza eventi.
  import { onDestroy, onMount } from 'svelte'
  import { locale, t } from '../../lib/i18n/index.svelte'
  import { eventLabel, groupByDay, mergeLive, sensorEvents } from '../../lib/sensors'
  import type { Node, SensorEvent } from '../../lib/types'
  import { onWsEvent, onWsResync } from '../../lib/wsext'
  import Badge from '../../lib/ui/Badge.svelte'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()

  let events = $state<SensorEvent[]>([])
  let loading = $state(false)
  let failed = $state(false)
  let now = $state(Date.now() / 1000)

  const groups = $derived(groupByDay(events, now))

  function load() {
    const id = node.id
    loading = true
    failed = false
    sensorEvents(id)
      .then((list) => {
        if (id === node.id) events = list
      })
      .catch(() => {
        if (id === node.id) failed = true
      })
      .finally(() => {
        if (id === node.id) loading = false
      })
  }

  // ricarica al cambio di nodo
  $effect(() => {
    void node.id
    events = []
    load()
  })

  let offEvent: (() => void) | null = null
  let offResync: (() => void) | null = null
  onMount(() => {
    offEvent = onWsEvent('sensor_event', (msg) => {
      const e = msg.event as SensorEvent | undefined
      if (e && e.node_id === node.id) {
        events = mergeLive(events, e)
        now = Date.now() / 1000
      }
    })
    offResync = onWsResync(load)
  })
  onDestroy(() => {
    offEvent?.()
    offResync?.()
  })

  function dayLabel(start: number): string {
    const today = new Date(now * 1000)
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() / 1000
    if (start === todayStart) return t('sensors.day.today')
    const y = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1).getTime() / 1000
    if (start === y) return t('sensors.day.yesterday')
    return new Date(start * 1000).toLocaleDateString(locale(), { day: 'numeric', month: 'long' })
  }
  const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
</script>

{#if events.length > 0 || loading || failed}
  <section class="sens">
    <h3>{t('sensors.title')}</h3>
    {#if failed && events.length === 0}
      <p class="ui-hint">{t('sensors.loadFailed')}</p>
    {:else if events.length > 0}
      {#each groups as g (g.dayStart)}
        <h4>{dayLabel(g.dayStart)}</h4>
        <ul>
          {#each g.events as e (e.id)}
            <li>
              <span class="time">{hhmm(e.time)}</span>
              <span class="txt">{eventLabel(e)}</span>
              {#if e.value !== null}
                <Badge kind={e.value >= 1 ? 'warn' : 'ok'}>{e.value >= 1 ? t('sensors.detected') : t('sensors.cleared')}</Badge>
              {/if}
              <span class="ui-hint">{t(e.source === 'mqtt' ? 'sensors.source.mqtt' : 'sensors.source.rf')}</span>
            </li>
          {/each}
        </ul>
      {/each}
      <p class="ui-hint">{t('sensors.hint.mqtt')}</p>
    {/if}
  </section>
{/if}

<style>
  .sens { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-4); color: var(--ink); }
  h3 { font: 600 14px/20px var(--font-sans); margin: 0; }
  h4 { font: 600 13px/18px var(--font-sans); margin: var(--space-2) 0 0; color: var(--ink-muted); }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  li { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; font: 400 13px/20px var(--font-sans); }
  .time { color: var(--ink-muted); font-variant-numeric: tabular-nums; }
  .txt { overflow-wrap: anywhere; }
  p { margin: 0; }
  :global(.vp-phone) li, :global(.vp-phone) h4 { font-size: 14px; line-height: 20px; }
</style>
