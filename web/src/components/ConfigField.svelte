<script lang="ts">
  import { MASK, enumLabel, fieldInput } from '../lib/config'
  import type { ConfigValue, SchemaField } from '../lib/types'

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
</script>

<label class="f" class:row={kind === 'checkbox'}>
  <span class="lbl">{label}</span>
  {#if kind === 'select'}
    <select {disabled} value={String(value ?? '')} onchange={(e) => onchange(e.currentTarget.value)}>
      {#each field.enum ?? [] as e (e)}
        <option value={e}>{enumLabel(path, e)}</option>
      {/each}
    </select>
  {:else if kind === 'checkbox'}
    <input type="checkbox" {disabled} checked={value === true} onchange={(e) => onchange(e.currentTarget.checked)} />
  {:else if kind === 'number'}
    <input
      type="number"
      {disabled}
      value={value === null || value === undefined ? '' : Number(value)}
      onchange={(e) => {
        const t = e.currentTarget.value
        if (t !== '' && Number.isFinite(Number(t))) onchange(Number(t))
      }}
    />
  {:else if kind === 'secret'}
    <input
      type="password"
      autocomplete="off"
      {disabled}
      placeholder="Invariato (segreto: si può solo sostituire)"
      value={value === MASK || value === undefined ? '' : String(value)}
      oninput={(e) => onchange(e.currentTarget.value === '' ? MASK : e.currentTarget.value)}
    />
  {:else if kind === 'readonly'}
    <code>{JSON.stringify(value ?? [])}</code>
  {:else}
    <input type="text" {disabled} value={String(value ?? '')} onchange={(e) => onchange(e.currentTarget.value)} />
  {/if}
  {#if help}<span class="help">{help}</span>{/if}
</label>

<style>
  .f {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin: 8px 0;
  }
  .f.row {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .lbl {
    font-size: 14px;
  }
  .help {
    color: #9ca3af;
    font-size: 12px;
    flex-basis: 100%;
  }
  input:not([type='checkbox']),
  select {
    font: inherit;
    padding: 5px 8px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
  }
  code {
    font-size: 12px;
    word-break: break-all;
  }
</style>
