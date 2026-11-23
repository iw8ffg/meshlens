<script lang="ts">
  // Sezione ATAK della scheda del nodo (E16): ultimo PLI ricevuto. Sola lettura, nessuna azione.
  import { onMount } from 'svelte'
  import type { Node } from '../../lib/types'
  import { t } from '../../lib/i18n/index.svelte'
  import { signed, timeAgo } from '../../lib/format'
  import { isIgnored } from '../../lib/filters'
  import { loadTak, startTakLive, tak } from '../../lib/map/takData.svelte'
  import { takRoleKey, takTeamKey } from '../../lib/map/takData'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()

  // orologio che avanza: il tempo relativo dell'ultimo PLI non resta fermo
  let now = $state(Math.floor(Date.now() / 1000))

  onMount(() => {
    if (!tak.loaded) void loadTak()
    const iv = setInterval(() => (now = Math.floor(Date.now() / 1000)), 15_000)
    const off = startTakLive()
    return () => {
      clearInterval(iv)
      off()
    }
  })

  const c = $derived(isIgnored(node) ? undefined : tak.contacts.get(node.id))
  const teamKey = $derived(c ? takTeamKey(c.team) : null)
  const roleKey = $derived(c ? takRoleKey(c.role) : null)
</script>

{#if c}
  <section class="tak">
    <h3>{t('tak.nodeinfo.title')}</h3>
    <dl>
      <dt>{t('tak.row.callsign')}</dt>
      <dd>
        {#if c.callsign}{c.callsign}{:else}{t('tak.noCallsign')}
          {#if c.compressed}<span class="ui-muted hint">{t('tak.compressed.hint')}</span>{/if}{/if}
      </dd>
      {#if c.team}<dt>{t('tak.row.team')}</dt><dd>{teamKey ? t(teamKey) : c.team}</dd>{/if}
      {#if c.role}<dt>{t('tak.row.role')}</dt><dd>{roleKey ? t(roleKey) : c.role}</dd>{/if}
      {#if c.battery !== null}<dt>{t('tak.row.battery')}</dt><dd>{c.battery} %</dd>{/if}
      <dt>{t('tak.row.lastPli')}</dt>
      <dd>{timeAgo(c.time, now)}</dd>
      {#if c.lat !== null && c.lon !== null}
        <dt>{t('tak.row.position')}</dt>
        <dd class="ui-mono">{signed(c.lat, 5)}, {signed(c.lon, 5)}</dd>
      {/if}
      {#if c.altitude !== null}<dt>{t('tak.row.altitude')}</dt><dd>{c.altitude} m</dd>{/if}
      {#if c.speed !== null}<dt>{t('tak.row.speed')}</dt><dd>{c.speed} m/s</dd>{/if}
      {#if c.course !== null}<dt>{t('tak.row.course')}</dt><dd>{c.course}°</dd>{/if}
      <dt>{t('tak.row.source')}</dt>
      <dd>{t(c.source === 'rf' ? 'tak.source.rf' : 'tak.source.mqtt')}</dd>
    </dl>
  </section>
{/if}

<style>
  .tak {
    margin-top: var(--space-3);
  }
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: var(--space-3) 0 var(--space-2);
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--space-1) var(--space-3);
    margin: 0;
    font-size: 14px;
    line-height: 20px;
  }
  dt {
    color: var(--ink-muted);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .hint {
    display: block;
  }
</style>
