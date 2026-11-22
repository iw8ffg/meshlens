<script lang="ts">
  // Legenda in HTML: su desktop e' una scheda, su telefono un pulsante che si espande.
  import Icon from '../ui/Icon.svelte'
  import SourceMark from '../ui/SourceMark.svelte'
  import { viewport } from '../viewport.svelte'
  import { t } from '../i18n/index.svelte'

  let { collapse = false }: { collapse?: boolean } = $props()
  let open = $state(!viewport.phone)

  // Ricerca o righello aperti: la legenda si chiude per non coprirli
  $effect(() => {
    if (collapse) open = false
  })
</script>

<div class="legend" class:open>
  <button type="button" class="toggle" aria-expanded={open} aria-controls="map-legend-body" onclick={() => (open = !open)}>
    <Icon name="layers" size={18} /><span>{t('map.legend.title')}</span><Icon name={open ? 'chevD' : 'chevU'} size={16} />
  </button>
  {#if open}
    <div id="map-legend-body" class="body">
      <div class="grp">
        <div class="h">{t('nodes.lastContact')}</div>
        <div class="it"><i class="dot" style="background:var(--contact-fresh)"></i>{t('map.legend.fresh')}</div>
        <div class="it"><i class="dot" style="background:var(--contact-recent)"></i>{t('map.legend.recent')}</div>
        <div class="it"><i class="dot" style="background:var(--contact-old)"></i>{t('map.legend.old')}</div>
      </div>
      <div class="grp">
        <div class="h">{t('map.legend.source')}</div>
        <div class="it"><SourceMark source="radio" size={18} />{t('nodes.sourceRadio')}</div>
        <div class="it"><SourceMark source="mqtt" size={18} />MQTT</div>
        <div class="it"><SourceMark source="both" size={18} />{t('common.sourceBoth')}</div>
      </div>
      <div class="grp">
        <div class="h">{t('map.legend.links')}</div>
        <div class="it"><i class="bar" style="background:var(--snr-good)"></i>{t('map.legend.snrGood')}</div>
        <div class="it"><i class="bar" style="background:var(--snr-mid)"></i>{t('map.legend.snrMid')}</div>
        <div class="it"><i class="bar" style="background:var(--snr-bad)"></i>{t('map.legend.snrBad')}</div>
        <div class="it"><i class="bar dashed" style="color:var(--snr-none)"></i>{t('map.legend.traceroute')}</div>
        <div class="it"><i class="bar dotted" style="color:var(--snr-none)"></i>{t('map.legend.gateway')}</div>
      </div>
      <div class="grp">
        <div class="it"><span class="star">★</span>{t('nodes.favorite')}</div>
        <div class="it"><span class="house">⌂</span>{t('nodes.mine')}</div>
        <div class="it"><i class="dot dashed" style="color:var(--src-mqtt)"></i>{t('map.legend.approx')}</div>
      </div>
    </div>
  {/if}
</div>

<style>
  .legend {
    position: absolute;
    left: var(--space-3);
    bottom: var(--space-6);
    z-index: var(--z-map-ui);
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-2);
    font-size: 13px;
    line-height: 18px;
    max-width: 230px;
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--control-h-desktop);
    padding: 0 var(--space-3);
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    border-radius: var(--radius-lg);
  }
  .toggle span {
    flex: 1;
    text-align: left;
  }
  .body {
    padding: 0 var(--space-3) var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    max-height: 60dvh;
    overflow: auto;
  }
  .h {
    color: var(--ink-muted);
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .it {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 20px;
  }
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 1.5px solid var(--marker-outline);
    flex: none;
    margin: 0 3px;
  }
  .dot.dashed {
    background: none;
    border: 2px dashed currentColor;
  }
  .bar {
    width: 18px;
    height: 3px;
    border-radius: 2px;
    flex: none;
  }
  .bar.dashed {
    background: repeating-linear-gradient(90deg, currentColor 0 5px, transparent 5px 8px);
  }
  .bar.dotted {
    background: radial-gradient(circle, currentColor 0 1px, transparent 1.5px) 0 50% / 5px 3px repeat-x;
  }
  .house {
    width: 18px;
    text-align: center;
    color: var(--accent);
    font-size: 16px;
  }
  .star {
    width: 18px;
    text-align: center;
    color: var(--brand-amber);
    font-size: 16px;
  }
  :global(.vp-phone) .legend {
    left: var(--space-3);
    bottom: auto;
    top: var(--space-3);
    max-width: calc(100% - 80px);
  }
  :global(.vp-phone) .legend,
  :global(.vp-phone) .legend .body {
    font-size: 14px;
    line-height: 20px;
  }
  :global(.vp-phone) .toggle {
    min-height: var(--touch-min);
  }
</style>
