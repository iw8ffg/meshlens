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
  <p class="note">Tutte le altre impostazioni del nodo. I segreti si possono solo sostituire, mai leggere.</p>
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
  .note {
    color: #9ca3af;
    font-size: 12px;
  }
  details {
    border: 1px solid #1f2937;
    border-radius: 6px;
    padding: 4px 8px;
    margin: 6px 0;
  }
  summary {
    cursor: pointer;
    font-size: 14px;
  }
</style>
