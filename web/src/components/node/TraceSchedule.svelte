<script lang="ts">
  // Traceroute periodico verso questo nodo (E14). Props fissate dal contratto §10.2.
  // Il server applica i limiti: minimo 1 ora per nodo, al piu' un traceroute per giro.
  import { onDestroy, onMount } from 'svelte'
  import { ApiError } from '../../lib/api'
  import { automation, setTargets, startAutomation } from '../../lib/automation.svelte'
  import { formatDate } from '../../lib/format'
  import { t } from '../../lib/i18n/index.svelte'
  import { app } from '../../lib/stores.svelte'
  import {
    INTERVAL_OPTIONS, intervalLabel, listTargets, nextRunAt, removeTarget, saveTarget, statusKey,
  } from '../../lib/tracesched'
  import type { Node } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import Switch from '../../lib/ui/Switch.svelte'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()

  let stop: (() => void) | null = null
  onMount(() => (stop = startAutomation()))
  onDestroy(() => stop?.())

  const target = $derived(automation.targets.find((x) => x.node_id === node.id) ?? null)
  let on = $state(false)
  let interval = $state('180')
  let radioId = $state('')
  let busy = $state(false)
  let error = $state('')

  // il modulo segue il bersaglio salvato (anche se cambia da un'altra scheda o dal server)
  $effect(() => {
    const tg = target
    on = tg !== null && tg.enabled
    interval = String(tg?.interval_min ?? 180)
    radioId = tg?.radio_id ?? ''
  })
  $effect(() => {
    void node.id
    error = ''
  })

  const intervals = $derived.by(() => {
    const cur = Number(interval)
    const list: number[] = [...INTERVAL_OPTIONS]
    if (!list.includes(cur) && Number.isFinite(cur)) list.push(cur)
    return list.sort((a, b) => a - b)
  })
  const radios = $derived(app.radios)
  const next = $derived(target ? nextRunAt(target) : null)

  async function refreshTargets() {
    try {
      setTargets((await listTargets()).targets)
    } catch {
      /* l'evento WebSocket arriva comunque */
    }
  }

  async function save(enabled: boolean) {
    busy = true
    error = ''
    const id = node.id
    try {
      if (enabled) {
        await saveTarget(id, { enabled: true, interval_min: Number(interval), radio_id: radioId || null })
      } else if (target) {
        await removeTarget(id)
      }
      await refreshTargets()
    } catch (e) {
      if (id === node.id) error = e instanceof ApiError ? e.message : t('tracesched.saveFailed')
      await refreshTargets()
      on = target !== null && target.enabled
    } finally {
      busy = false
    }
  }

  function changed() {
    if (on) void save(true)
  }
</script>

{#if !node.is_mine}
  <section class="sched">
    <Switch bind:checked={on} disabled={busy} label={t('tracesched.toggle')} onchange={(v) => void save(v)} />
    {#if on || target}
      {#if !automation.autoEnabled}
        <Banner kind="info" title={t('tracesched.disabledBanner')} />
      {/if}
      <div class="row">
        <Field label={t('tracesched.interval')} hint={t('tracesched.intervalHint')} for="ts-interval-{node.id}">
          {#snippet children()}
            <Select id="ts-interval-{node.id}" bind:value={interval} disabled={busy} onchange={changed}>
              {#each intervals as n (n)}<option value={String(n)}>{intervalLabel(n)}</option>{/each}
            </Select>
          {/snippet}
        </Field>
        <Field label={t('tracesched.radio')} for="ts-radio-{node.id}">
          {#snippet children()}
            <Select id="ts-radio-{node.id}" bind:value={radioId} disabled={busy} onchange={changed}>
              <option value="">{t('tracesched.radioAuto')}</option>
              {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
            </Select>
          {/snippet}
        </Field>
      </div>
      {#if target}
        <dl class="state">
          <div><dt>{t('tracesched.lastRun')}</dt><dd>{target.last_run ? formatDate(target.last_run) : t('tracesched.never')}</dd></div>
          <div><dt>{t('tracesched.lastStatus')}</dt><dd>{t(statusKey(target.last_status))}</dd></div>
          <div><dt>{t('tracesched.nextRun')}</dt><dd>{next ? formatDate(next) : t('tracesched.status.pending')}</dd></div>
        </dl>
        {#if target.fail_count > 0}<p class="muted">{t('tracesched.failures', { n: target.fail_count })}</p>{/if}
      {/if}
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
  </section>
{/if}

<style>
  .sched {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: var(--space-3) 0;
  }
  .row {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .row :global(.ui-field) {
    flex: 1 1 180px;
  }
  .state {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: var(--space-1) var(--space-3);
    font: 400 13px/18px var(--font-sans);
  }
  .state div {
    display: flex;
    flex-direction: column;
  }
  dt {
    color: var(--ink-muted);
  }
  dd {
    margin: 0;
    color: var(--ink);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
    font: 400 13px/18px var(--font-sans);
  }
  :global(.vp-phone) .state,
  :global(.vp-phone) .muted {
    font-size: 14px;
    line-height: 20px;
  }
</style>
