<script lang="ts">
  import { MASK, enumLabel, fieldInput } from '../lib/config'
  import { t } from '../lib/i18n/index.svelte'
  import type { ConfigValue, SchemaField } from '../lib/types'
  import Switch from '../lib/ui/Switch.svelte'

  let {
    path,
    field,
    label,
    help = '',
    value,
    disabled = false,
    onchange,
  }: {
    path: string
    field: SchemaField
    label: string
    help?: string
    value: ConfigValue
    disabled?: boolean
    onchange: (v: ConfigValue) => void
  } = $props()

  const kind = $derived(fieldInput(field))
  const uid = $props.id()
</script>

{#if kind === 'checkbox'}
  <div class="f">
    <Switch checked={value === true} {label} {disabled} onchange={(v) => onchange(v)} />
    {#if help}<span class="ui-hint">{help}</span>{/if}
  </div>
{:else}
  <div class="f">
    <label class="ui-lbl" for={uid}>{label}</label>
    {#if kind === 'select'}
      <select id={uid} class="ui-select" {disabled} value={String(value ?? '')} onchange={(e) => onchange(e.currentTarget.value)}>
        {#each field.enum ?? [] as e (e)}
          <option value={e}>{enumLabel(path, e)}</option>
        {/each}
      </select>
    {:else if kind === 'number'}
      <input
        id={uid}
        class="ui-input ui-mono"
        type="number"
        step={field.type === 'float' ? 'any' : '1'}
        {disabled}
        value={value === null || value === undefined ? '' : Number(value)}
        onchange={(e) => {
          const raw = e.currentTarget.value
          if (raw !== '' && Number.isFinite(Number(raw))) onchange(Number(raw))
        }}
      />
    {:else if kind === 'secret'}
      <input
        id={uid}
        class="ui-input ui-mono"
        type="password"
        autocomplete="off"
        {disabled}
        placeholder={t('config.field.secretPh')}
        value={value === MASK || value === undefined ? '' : String(value)}
        oninput={(e) => onchange(e.currentTarget.value === '' ? MASK : e.currentTarget.value)}
      />
    {:else if kind === 'readonly'}
      <code id={uid}>{JSON.stringify(value ?? [])}</code>
    {:else}
      <input id={uid} class="ui-input" type="text" {disabled} value={String(value ?? '')} onchange={(e) => onchange(e.currentTarget.value)} />
    {/if}
    {#if help}<span class="ui-hint">{help}</span>{/if}
  </div>
{/if}

<style>
  .f { display: flex; flex-direction: column; gap: 4px; margin: var(--space-3) 0; }
  code { font: 400 13px/18px var(--font-mono); word-break: break-all; color: var(--ink); }
</style>
