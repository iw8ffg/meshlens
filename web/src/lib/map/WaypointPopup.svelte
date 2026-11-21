<script lang="ts">
  // Contenuto del popup di un waypoint. Testi come nodi di testo Svelte (mai HTML): nome e descrizione arrivano dalla rete.
  // La conferma di «Elimina per tutti» e' del chiamante: un Modal dentro il popup (che e' trasformato) non sarebbe a tutto schermo.
  import { onDestroy } from 'svelte'
  import Icon from '../ui/Icon.svelte'
  import { copyText } from '../clipboard'
  import { expiryLabel, WP_ICONS } from '../waypoints'
  import { T } from '../strings/waypoint'
  import type { Waypoint } from '../types'

  interface Props {
    wp: Waypoint
    now: number
    ondelete: () => void
  }
  let { wp, now, ondelete }: Props = $props()

  const author = $derived(wp.from_name || wp.from)
  let copied = $state(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  onDestroy(() => {
    if (timer) clearTimeout(timer)
  })

  async function copy() {
    if (!(await copyText(`${wp.lat.toFixed(5)}, ${wp.lon.toFixed(5)}`))) return
    copied = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      copied = false
      timer = null
    }, 2000)
  }
</script>

<div class="wp">
  <div class="head">
    <span class="ic" aria-hidden="true">{wp.icon || WP_ICONS[0]}</span>
    <b class="title">{wp.name}</b>
  </div>
  {#if wp.description}<p class="desc">{wp.description}</p>{/if}
  <div class="sub">{T.author(author)}</div>
  <div class="sub">{expiryLabel(wp.expire, now)}</div>
  <div class="acts">
    <button type="button" class="act" onclick={copy}>
      <Icon name="copy" size={16} />
      <span>{copied ? T.copied : T.copyCoords}</span>
    </button>
    {#if wp.mine}
      <button type="button" class="act danger" onclick={ondelete}>
        <Icon name="trash" size={16} />
        <span>{T.deleteForAll}</span>
      </button>
    {/if}
  </div>
</div>

<style>
  .wp {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 200px;
    max-width: 260px;
    font-size: 14px;
    line-height: 20px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding-right: var(--space-6);
  }
  .ic {
    font-size: 20px;
  }
  .title {
    overflow-wrap: anywhere;
  }
  .desc {
    margin: 0;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  .sub {
    color: var(--ink-muted);
  }
  .acts {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-top: var(--space-2);
  }
  .act {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--control-h-desktop);
    padding: 0 var(--space-2);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    background: var(--surface-sunken);
    color: var(--ink);
    font: inherit;
    cursor: pointer;
  }
  .act:hover {
    border-color: var(--ink-muted);
  }
  .act.danger {
    color: var(--danger);
  }
  .act:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  :global(.vp-phone) .act {
    min-height: var(--touch-min);
  }
</style>
