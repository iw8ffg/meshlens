<script lang="ts">
  // Pannello degli strati della mappa (E5, E16): un interruttore per strato con la sua spiegazione.
  import Switch from '../ui/Switch.svelte'
  import { t, tn } from '../i18n/index.svelte'
  import type { MsgKey } from '../i18n/index.svelte'
  import { LAYER_KEYS } from './layerstate'
  import type { LayerKey, LayerState } from './layerstate'

  interface Props {
    layers: LayerState
    /** false: la riga «etichette» e' disabilitata con spiegazione. */
    glyphs: boolean
    /** app.filter.links: senza collegamenti le etichette non hanno effetto. */
    linksOn: boolean
    /** null = non ancora caricato. */
    tak: { count: number; compressed: number; unsupportedV2: number } | null
    onchange: (key: LayerKey, on: boolean) => void
  }
  let { layers, glyphs, linksOn, tak, onchange }: Props = $props()

  const label = (k: LayerKey): string => t(`layers.${k}` as MsgKey)
  const hint = (k: LayerKey): string => t(`layers.${k}.hint` as MsgKey)
  const disabled = (k: LayerKey): boolean => k === 'linkLabels' && !glyphs
</script>

<div class="panel" role="group" aria-label={t('layers.aria')}>
  <div class="h">{t('layers.title')}</div>
  {#each LAYER_KEYS as k (k)}
    <div class="row" role="group" aria-describedby={`layer-hint-${k}`}>
      <Switch checked={layers[k]} label={label(k)} disabled={disabled(k)} onchange={(v) => onchange(k, v)} />
      <p class="hint" id={`layer-hint-${k}`}>{hint(k)}</p>
      {#if k === 'linkLabels'}
        {#if disabled(k)}
          <p class="hint warn">{t('layers.linkLabels.noGlyphs')}</p>
        {:else if layers.linkLabels && !linksOn}
          <p class="hint warn">{t('layers.linkLabels.needLinks')}</p>
        {/if}
      {/if}
      {#if k === 'tak' && layers.tak}
        <p class="hint">{t('tak.help')}</p>
        {#if tak}
          <p class="hint">{tn('tak.count', tak.count)}</p>
          {#if tak.compressed > 0}<p class="hint">{tn('tak.compressedCount', tak.compressed)}</p>{/if}
          {#if tak.unsupportedV2 > 0}<p class="hint">{tn('tak.v2Count', tak.unsupportedV2)}</p>{/if}
        {/if}
      {/if}
    </div>
  {/each}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .h {
    color: var(--ink-muted);
    font-size: 12px;
    font-weight: 600;
  }
  .hint {
    margin: 0 0 var(--space-1);
    color: var(--ink-muted);
    font-size: 13px;
    line-height: 18px;
  }
  .warn {
    color: var(--ink);
  }
  :global(.vp-phone) .hint {
    font-size: 14px;
    line-height: 20px;
  }
</style>
