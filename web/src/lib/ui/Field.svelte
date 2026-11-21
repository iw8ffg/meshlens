<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    label: string
    hint?: string
    error?: string
    /** Id del controllo: l'etichetta lo referenzia con `for`. */
    for?: string
    children: Snippet<[{ describedby: string | undefined; invalid: boolean }]>
  }
  let { label, hint, error, for: forId, children }: Props = $props()
  const uid = $props.id()
  const msgId = $derived(error || hint ? `${uid}-msg` : undefined)
</script>

<div class="ui-field">
  <label class="ui-lbl" for={forId}>{label}</label>
  {@render children({ describedby: msgId, invalid: !!error })}
  {#if error}
    <div class="ui-hint err" id={msgId}>{error}</div>
  {:else if hint}
    <div class="ui-hint" id={msgId}>{hint}</div>
  {/if}
</div>
