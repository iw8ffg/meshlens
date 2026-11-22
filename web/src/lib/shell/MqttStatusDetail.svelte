<script lang="ts">
  import { onMount } from 'svelte'
  import { brokerRows, mqttSummary } from '../mqttstatus'
  import type { MqttStatus } from '../types'
  import { t } from '../i18n/index.svelte'

  let { status, onsettings }: { status: MqttStatus | null; onsettings?: () => void } = $props()

  // l'orologio avanza da solo: i tempi relativi restano esatti anche tra due messaggi di stato
  let now = $state(Date.now() / 1000)
  onMount(() => {
    const t = setInterval(() => (now = Date.now() / 1000), 5000)
    return () => clearInterval(t)
  })
  const sum = $derived(mqttSummary(status, now))
  const rows = $derived(brokerRows(status, now))
</script>

<div class="md">
  <div class="head"><span class="dot {sum.tone}"></span><strong>{sum.title}</strong></div>
  {#if sum.rows.length}
    <dl>
      {#each sum.rows as r (r.label)}
        <dt>{r.label}</dt>
        <dd>{r.value}</dd>
      {/each}
    </dl>
  {/if}
  {#if rows.length > 1}
    <ul class="brokers">
      {#each rows as b (b.id)}
        <li><span class="dot {b.tone}"></span><span class="bn">{b.name}</span><span class="bd">{b.detail}</span></li>
      {/each}
    </ul>
  {/if}
  {#if onsettings}
    <button type="button" class="link" onclick={onsettings}>{t('shell.mqttSettings')}</button>
  {/if}
</div>

<style>
  .md { white-space: normal; font: 400 14px/20px var(--font-sans); color: var(--ink); }
  .head { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ink-muted); flex: none; }
  .dot.ok { background: var(--ok); }
  .dot.warn { background: var(--warn); }
  .dot.ko { background: var(--danger); }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 2px var(--space-3); margin: 0 0 var(--space-2); }
  dt { color: var(--ink-muted); }
  dd { margin: 0; text-align: right; overflow-wrap: anywhere; }
  .brokers { list-style: none; margin: 0 0 var(--space-2); padding: 0; display: grid; gap: var(--space-1); }
  .brokers li { display: grid; grid-template-columns: auto 1fr; column-gap: var(--space-2); align-items: center; }
  .bn { font-weight: 600; overflow-wrap: anywhere; }
  .bd { grid-column: 2; color: var(--ink-muted); overflow-wrap: anywhere; }
  .link { min-height: var(--touch-min); padding: 0; border: 0; background: none; color: var(--accent-ink); font: 600 14px/20px var(--font-sans); cursor: pointer; text-align: left; }
  .link:hover { text-decoration: underline; }
</style>
