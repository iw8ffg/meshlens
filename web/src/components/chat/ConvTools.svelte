<script lang="ts">
  // Strumenti della conversazione aperta (WP1, E4): cerca nei messaggi ed esporta in TXT/CSV/JSON.
  // I file si costruiscono nel browser (separatore e virgola decimale seguono la lingua): il server manda solo i dati.
  import { getJSON } from '../../lib/api'
  import { downloadText } from '../../lib/download'
  import { conversationCsv, conversationFileName, conversationJson, conversationTxt, exportPath } from '../../lib/export'
  import type { ConvExport, ConvExportFormat } from '../../lib/export'
  import { t } from '../../lib/i18n/index.svelte'
  import type { MsgKey } from '../../lib/i18n/index.svelte'
  import { exportMime, periodRange } from '../../lib/msgsearch'
  import type { PeriodKind } from '../../lib/msgsearch'
  import type { MessageSearchHit } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Segmented from '../../lib/ui/Segmented.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import { dialogTrap } from './dialog'
  import MessageSearch from './MessageSearch.svelte'

  let { conv, label, onhit }: { conv: string; label: string; onhit: (hit: MessageSearchHit) => void } = $props()

  const uid = $props.id()
  const PERIODS: PeriodKind[] = ['all', 'day', 'week', 'month']
  const FORMATS: { value: ConvExportFormat; label: string }[] = [
    { value: 'txt', label: 'TXT' },
    { value: 'csv', label: 'CSV' },
    { value: 'json', label: 'JSON' },
  ]

  let searchOpen = $state(false)
  let exportOpen = $state(false)
  let format = $state<ConvExportFormat>('csv')
  let period = $state<PeriodKind>('all')
  let busy = $state(false)
  let error = $state('')
  let notice = $state('')

  function openExport() {
    error = ''
    notice = ''
    exportOpen = true
  }

  async function download() {
    busy = true
    error = ''
    notice = ''
    try {
      const r = periodRange(period, Math.floor(Date.now() / 1000))
      const d = await getJSON<ConvExport>(exportPath(conv, r.since, r.until))
      const now = new Date()
      const text = format === 'txt' ? conversationTxt(d, label, now) : format === 'csv' ? conversationCsv(d) : conversationJson(d, now)
      downloadText(conversationFileName(label, format, now), exportMime(format), text)
      if (d.truncated) notice = t('chat.export.truncated', { n: d.messages.length, total: d.total })
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : t('chat.export.error')
    } finally {
      busy = false
    }
  }
</script>

<Button kind="ghost" iconOnly icon="search" label={t('chat.search.open')} title={t('chat.search.open')} onclick={() => (searchOpen = true)} />
<Button kind="ghost" iconOnly icon="download" label={t('chat.export.open')} title={t('chat.export.open')} onclick={openExport} />

{#if searchOpen}
  <MessageSearch {conv} {onhit} onclose={() => (searchOpen = false)} />
{/if}

{#if exportOpen}
  <div class="ui-modalbg" role="presentation" onpointerdown={(e) => { if (e.target === e.currentTarget) exportOpen = false }}>
    <div class="ui-modal" role="dialog" aria-modal="true" aria-labelledby="{uid}-t" tabindex="-1" use:dialogTrap={() => (exportOpen = false)}>
      <h2 id="{uid}-t">{t('chat.export.dialogTitle')}</h2>
      <Field label={t('chat.export.format')}>
        {#snippet children()}
          <Segmented items={FORMATS} bind:value={format} label={t('chat.export.format')} />
        {/snippet}
      </Field>
      <Field label={t('chat.export.period')} for="{uid}-p">
        {#snippet children({ describedby })}
          <Select id="{uid}-p" bind:value={period} aria-describedby={describedby}>
            {#each PERIODS as p (p)}<option value={p}>{t(`search.messages.period.${p}` as MsgKey)}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      {#if error}<Banner kind="danger" title={t('chat.export.error')}>{error}</Banner>{/if}
      {#if notice}<Banner kind="warn" title={notice} />{/if}
      <div class="acts">
        <Button data-autofocus onclick={() => (exportOpen = false)}>{t('common.close')}</Button>
        <Button kind="primary" icon="download" disabled={busy} onclick={download}>{busy ? t('shell.loading') : t('chat.export.download')}</Button>
      </div>
    </div>
  </div>
{/if}
