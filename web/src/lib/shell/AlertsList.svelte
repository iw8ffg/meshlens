<script lang="ts">
  import Icon from '../ui/Icon.svelte'
  import { ago } from '../format'
  import { alertIcon, alertLabel, alertTone } from '../alerts'
  import type { Alert } from '../types'

  interface Props {
    alerts: Alert[]
    onpick: (nodeId: string) => void
  }
  let { alerts, onpick }: Props = $props()
</script>

<ul class="alerts-list">
  {#each alerts as a (a.key)}
    {@const tone = alertTone(a.kind)}
    <li>
      <button type="button" class="row" onclick={() => onpick(a.node_id)}>
        <span class="ico {tone}"><Icon name={alertIcon(a.kind)} size={18} /></span>
        <span class="txt">
          <span class="main">{alertLabel(a)} — {a.node_name}</span>
          <span class="since">da {ago((Date.now() / 1000 - a.since) / 60)}</span>
        </span>
      </button>
    </li>
  {/each}
</ul>

<style>
  .alerts-list { list-style: none; margin: 0; padding: 0; }
  .row { display: flex; align-items: flex-start; gap: var(--space-2); width: 100%; min-height: var(--touch-min); box-sizing: border-box; text-align: left; padding: var(--space-2) var(--space-3); background: none; border: 0; border-radius: var(--radius-md); color: var(--ink); font: 400 14px/20px var(--font-sans); cursor: pointer; }
  .row:hover { background: var(--accent-soft); }
  .ico { display: inline-flex; flex: none; margin-top: 1px; color: var(--warn); }
  .ico.ok { color: var(--ok); }
  .txt { display: flex; flex-direction: column; min-width: 0; }
  .main { overflow-wrap: anywhere; }
  .since { color: var(--ink-muted); font: 400 14px/20px var(--font-sans); }
</style>
