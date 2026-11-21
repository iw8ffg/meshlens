<script lang="ts">
  // Nuovo waypoint: si invia solo da una radio collegata (via MQTT non si pubblicano waypoint).
  import { untrack } from 'svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Select from '../lib/ui/Select.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import { app } from '../lib/stores.svelte'
  import { sendWaypoint } from '../lib/api'
  import { validateWaypoint, WP_ICONS } from '../lib/waypoints'
  import { T } from '../lib/strings/waypoint'

  interface Props {
    lat: number
    lon: number
    onclose: () => void
  }
  let { lat, lon, onclose }: Props = $props()

  type Expiry = 'never' | '1' | '24' | '168'
  const EXPIRY_H: Record<Expiry, number | null> = { never: null, '1': 1, '24': 24, '168': 168 }
  const expiryItems: { value: Expiry; label: string }[] = [
    { value: 'never', label: T.expiryNever },
    { value: '1', label: T.expiry1h },
    { value: '24', label: T.expiry24h },
    { value: '168', label: T.expiry7d },
  ]

  const uid = $props.id()
  let name = $state('')
  let description = $state('')
  let icon = $state<string>(WP_ICONS[0])
  let expiry = $state<Expiry>('never')
  let latText = $state(untrack(() => lat.toFixed(5)))
  let lonText = $state(untrack(() => lon.toFixed(5)))
  let radioId = $state('')
  let channel = $state('0')
  let error = $state('')
  let busy = $state(false)

  const radios = $derived(app.radios.filter((r) => r.state === 'connected'))
  // la radio scelta resta valida se si scollega: si ricade sulla prima collegata
  const radio = $derived(radios.find((r) => r.id === radioId) ?? radios[0])
  const channels = $derived((radio?.channels ?? []).filter((c) => c.role !== 'DISABLED'))
  const channelValue = $derived(channels.some((c) => String(c.index) === channel) ? channel : String(channels[0]?.index ?? 0))

  async function submit() {
    if (busy) return
    if (!radio) {
      error = T.needRadio
      return
    }
    const la = Number(latText.replace(',', '.'))
    const lo = Number(lonText.replace(',', '.'))
    const expireH = EXPIRY_H[expiry]
    const err = validateWaypoint({ name, description, lat: latText.trim() === '' ? NaN : la, lon: lonText.trim() === '' ? NaN : lo, expireH })
    if (err) {
      error = err
      return
    }
    error = ''
    busy = true
    try {
      await sendWaypoint(radio.id, { name: name.trim(), description, icon, lat: la, lon: lo, expire_h: expireH, channel_index: Number(channelValue) })
      onclose()
    } catch (e) {
      error = T.sendFailed(e instanceof Error ? e.message : 'errore')
    } finally {
      busy = false
    }
  }
</script>

<Modal open title={T.formTitle} confirmLabel={T.send} cancelLabel={T.cancel} onconfirm={submit} oncancel={onclose}>
  <form class="wf" onsubmit={(e) => { e.preventDefault(); void submit() }}>
    {#if radios.length === 0}
      <Banner kind="warn" title={T.needRadio} />
    {/if}
    <Field label={T.name} hint={T.nameHint} for="{uid}-name">
      {#snippet children({ describedby })}
        <input id="{uid}-name" class="ui-input" bind:value={name} autocomplete="off" aria-describedby={describedby} />
      {/snippet}
    </Field>
    <Field label={T.description} hint={T.descriptionHint} for="{uid}-desc">
      {#snippet children({ describedby })}
        <input id="{uid}-desc" class="ui-input" bind:value={description} autocomplete="off" aria-describedby={describedby} />
      {/snippet}
    </Field>
    <div class="ui-field">
      <span class="ui-lbl" id="{uid}-icons">{T.icon}</span>
      <div class="icons" role="group" aria-labelledby="{uid}-icons">
        {#each WP_ICONS as ic (ic)}
          <button type="button" class="ic" aria-pressed={icon === ic} aria-label={T.iconAria(ic)} onclick={() => (icon = ic)}>{ic}</button>
        {/each}
      </div>
    </div>
    <div class="ui-field">
      <span class="ui-lbl">{T.expiry}</span>
      <Segmented items={expiryItems} bind:value={expiry} label={T.expiry} />
    </div>
    <div class="two">
      <Field label={T.lat} for="{uid}-lat">
        {#snippet children()}<input id="{uid}-lat" class="ui-input mono" inputmode="decimal" bind:value={latText} />{/snippet}
      </Field>
      <Field label={T.lon} for="{uid}-lon">
        {#snippet children()}<input id="{uid}-lon" class="ui-input mono" inputmode="decimal" bind:value={lonText} />{/snippet}
      </Field>
    </div>
    {#if radios.length > 0}
      <div class="two">
        <Field label={T.radio} for="{uid}-radio">
          {#snippet children()}
            <Select id="{uid}-radio" value={radio?.id} onchange={(e) => (radioId = e.currentTarget.value)}>
              {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
            </Select>
          {/snippet}
        </Field>
        <Field label={T.channel} for="{uid}-ch">
          {#snippet children()}
            <Select id="{uid}-ch" value={channelValue} onchange={(e) => (channel = e.currentTarget.value)}>
              {#each channels as c (c.index)}<option value={String(c.index)}>{T.channelOption(c.index, c.name)}</option>{/each}
            </Select>
          {/snippet}
        </Field>
      </div>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
  </form>
</Modal>

<style>
  .wf {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: min(420px, 80vw);
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
  .icons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .ic {
    width: var(--touch-min);
    height: var(--touch-min);
    font-size: 22px;
    line-height: 1;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-md);
    background: var(--surface-sunken);
    cursor: pointer;
  }
  .ic[aria-pressed='true'] {
    border-color: var(--accent);
    background: var(--accent-soft);
    outline: 2px solid var(--accent);
  }
  .ic:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
</style>
