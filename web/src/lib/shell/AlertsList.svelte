<script lang="ts">
  import Icon from '../ui/Icon.svelte'
  import AlertDismiss from './AlertDismiss.svelte'
  import AcceptKey from './AcceptKey.svelte'
  import { ago } from '../format'
  import { alertIcon, alertLabel, alertTone } from '../alerts'
  import type { Alert } from '../types'

  interface Props {
    alerts: Alert[]
    now: number
    onpick: (nodeId: string) => void
  }
  let { alerts, now, onpick }: Props = $props()
</script>

<ul class="alerts-list">
  {#each alerts as a (a.key)}
    {@const tone = alertTone(a.kind)}
    {@const text = a.kind === 'key_changed' ? alertLabel(a) : `${alertLabel(a)} — ${a.node_name}`}
    <li>
      <div class="item">
        <button type="button" class="row" onclick={() => onpick(a.node_id)}>
          <span class="ico {tone}"><Icon name={alertIcon(a.kind)} size={18} /></span>
          <span class="txt">
            <span class="main">{text}</span>
            <span class="since">{ago((now - a.since) / 60)}</span>
          </span>
        </button>
        <AlertDismiss alertKey={a.key} {text} />
      </div>
      {#if a.kind === 'key_changed'}<div class="accept"><AcceptKey nodeId={a.node_id} /></div>{/if}
    </li>
  {/each}
</ul>

<style>
  .alerts-list { list-style: none; margin: 0; padding: 0; }
  .item { display: flex; align-items: flex-start; }
  .accept { padding: 0 var(--space-3) var(--space-2); }
  .row { flex: 1; min-width: 0; display: flex; align-items: flex-start; gap: var(--space-2); min-height: var(--touch-min); box-sizing: border-box; text-align: left; padding: var(--space-2) var(--space-3); background: none; border: 0; border-radius: var(--radius-md); color: var(--ink); font: 400 14px/20px var(--font-sans); cursor: pointer; }
  .row:hover { background: var(--accent-soft); }
  .row:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .ico { display: inline-flex; flex: none; margin-top: 1px; color: var(--warn); }
  .ico.ok { color: var(--ok); }
  .txt { display: flex; flex-direction: column; min-width: 0; }
  .main { overflow-wrap: anywhere; }
  .since { color: var(--ink-muted); font: 400 14px/20px var(--font-sans); }
</style>
