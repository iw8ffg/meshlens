<script lang="ts">
  // WP4 (E12): avviso e correzione guidata della precisione della posizione sui canali
  // pubblici o inoltrati a MQTT. Correzione = anteprima del server, applicata dal pannello.
  import { onDestroy, onMount } from 'svelte'
  import { ApiError } from '../lib/api'
  import { t } from '../lib/i18n/index.svelte'
  import { FIX_CHOICES, getPrivacy, precisionMeters, precisionText, previewPrivacyFix, radiosAtRisk, reasonKey } from '../lib/privacy'
  import { openConfig } from '../lib/stores.svelte'
  import { onWsResync } from '../lib/wsext'
  import type { ConfigPreview, PrivacyRadio, PrivacyRisk } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'

  let {
    nodeId,
    compact = false,
    onfix,
  }: { nodeId: string | null; compact?: boolean; onfix?: (p: ConfigPreview) => void } = $props()

  let radios = $state<PrivacyRadio[]>([])
  let bits = $state<Record<string, number>>({})
  let busy = $state<string | null>(null)
  let error = $state('')

  const shown = $derived(radiosAtRisk(radios.filter((r) => nodeId === null || r.node_id === nodeId)))

  async function load() {
    try {
      radios = (await getPrivacy()).radios
    } catch {
      radios = []
    }
  }
  onMount(() => void load())
  const off = onWsResync(() => void load())
  onDestroy(off)

  const key = (r: PrivacyRadio, k: PrivacyRisk) => `${r.radio_id}:${k.channel_index ?? 'map'}`
  const choiceText = (b: number) => (b === 0 ? t('privacy.fix.off') : precisionText(b, precisionMeters(b)))

  async function fix(r: PrivacyRadio, k: PrivacyRisk) {
    if (!r.node_id || k.channel_index === undefined) return
    const id = key(r, k)
    busy = id
    error = ''
    try {
      const p = await previewPrivacyFix(r.node_id, bits[id] ?? 14, [k.channel_index])
      onfix?.(p)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('privacy.failed')
    } finally {
      busy = null
    }
  }
</script>

{#each shown as r (r.radio_id)}
  <Banner kind="warn" title={compact ? t('privacy.titleCompact') : t('privacy.title', { name: r.name ?? r.radio_id })}>
    <ul class="risks">
      {#each r.risks as k (key(r, k))}
        <li>
          {#if k.kind === 'channel'}
            <b>{t('privacy.channel', { n: k.channel_index ?? 0, name: k.channel_name ?? '' })}</b>
            <span>{t('privacy.current', { value: precisionText(k.precision_bits, k.precision_m) })}</span>
            <span class="why">{k.reasons.map((x) => t(reasonKey(x))).join(' · ')}</span>
            {#if !compact && onfix}
              <span class="fix">
                <select class="ui-select" aria-label={t('privacy.fix.choice')} value={String(bits[key(r, k)] ?? 14)} onchange={(e) => (bits[key(r, k)] = Number(e.currentTarget.value))}>
                  {#each FIX_CHOICES as b (b)}<option value={String(b)}>{choiceText(b)}</option>{/each}
                </select>
                <Button disabled={busy !== null} onclick={() => fix(r, k)}>{t('privacy.fix.button')}</Button>
              </span>
            {/if}
          {:else}
            <b>{t('privacy.mapReport')}</b>
            <span>{t('privacy.current', { value: precisionText(k.precision_bits, k.precision_m) })}</span>
            <span class="why">{t('privacy.mapReportHelp')}</span>
          {/if}
        </li>
      {/each}
    </ul>
    {#snippet action()}
      {#if compact}
        <Button onclick={() => openConfig(r.node_id ?? '', r.radio_id, 'channels')}>{t('privacy.open')}</Button>
      {/if}
    {/snippet}
  </Banner>
{/each}
{#if error}<Banner kind="danger" title={error} />{/if}

<style>
  .risks {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-3);
    font-size: 14px;
  }
  .why {
    color: var(--ink-muted);
    font-size: 13px;
  }
  .fix {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    flex-wrap: wrap;
  }
  :global(.vp-phone) .why {
    font-size: 14px;
  }
</style>
