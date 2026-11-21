<script lang="ts">
  import { advancedSections, getPath, setPath } from '../lib/config'
  import type { ConfigDict, ConfigSchema, ConfigValue } from '../lib/types'
  import ConfigField from './ConfigField.svelte'

  let {
    schema,
    edited,
    disabled = false,
  }: {
    schema: ConfigSchema
    edited: ConfigDict
    disabled?: boolean
  } = $props()

  const sections = $derived(advancedSections(schema))
  const set = (path: string, v: ConfigValue) => setPath(edited, path, v)
</script>

<div>
  <p class="note ui-hint">Tutte le altre impostazioni del nodo. I segreti si possono solo sostituire, mai leggere.</p>
  {#each sections as s (s.key)}
    <details>
      <summary>{s.label}</summary>
      {#each s.fields as f (f.path)}
        <ConfigField
          path={f.path}
          field={f.field}
          label={f.name}
          value={getPath(edited, f.path)}
          {disabled}
          onchange={(v) => set(f.path, v)}
        />
      {/each}
    </details>
  {/each}
</div>

<style>
  .note { margin: 0 0 var(--space-2); }
  details { border: 1px solid var(--line); border-radius: var(--radius-md); padding: 0 var(--space-3); margin: var(--space-2) 0; background: var(--surface-raised); color: var(--ink); }
  summary { cursor: pointer; min-height: var(--touch-min); display: flex; align-items: center; font: 500 14px/20px var(--font-sans); }
  summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
