<script lang="ts">
  // Diagnosi del collegamento radio (E20): elenco dei controlli e passi concreti per il consiglio
  // principale. Radio salvata (radioId) oppure non ancora aggiunta (kind + address).
  import { ApiError } from '../lib/api'
  import { t } from '../lib/i18n/index.svelte'
  import {
    adviceSteps, adviceTitleKey, checkLabelKey, diagnoseAddress, diagnoseSaved, statusKind, statusLabelKey,
    type Diagnosis,
  } from '../lib/radiodiag'
  import type { RadioKind } from '../lib/types'
  import Badge from '../lib/ui/Badge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  interface Props {
    radioId?: string | null
    kind?: RadioKind | null
    address?: string | null
    onclose: () => void
  }
  let { radioId = null, kind = null, address = null, onclose }: Props = $props()

  let result = $state<Diagnosis | null>(null)
  let running = $state(false)
  let error = $state('')

  async function run() {
    running = true
    error = ''
    result = null
    try {
      if (radioId) result = await diagnoseSaved(radioId)
      else if (kind && address) result = await diagnoseAddress(kind, address)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('radiodiag.failed')
    } finally {
      running = false
    }
  }

  $effect(() => {
    void radioId
    void kind
    void address
    void run()
  })

  const main = $derived.by(() => {
    if (!result?.advice) return null
    const c = result.checks.find((x) => x.advice === result!.advice && (x.status === 'fail' || x.status === 'warn'))
    return { code: result.advice, params: c?.params ?? {} }
  })
</script>

<Modal
  open
  title={t('radiodiag.title')}
  confirmLabel={t('radiodiag.repeat')}
  cancelLabel={t('radiodiag.close')}
  onconfirm={() => { if (!running) void run() }}
  oncancel={onclose}
>
  <div class="diag">
    {#if running}
      <p role="status" class="muted">{t('radiodiag.running')}</p>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if result}
      <ul class="checks">
        {#each result.checks as c, i (i)}
          <li>
            <Badge kind={statusKind(c.status)}>{t(statusLabelKey(c.status))}</Badge>
            <span>{t(checkLabelKey(c.check))}</span>
          </li>
        {/each}
      </ul>
      {#if main}
        <Banner kind="warn" title={t(adviceTitleKey(main.code))} />
        <h4>{t('radiodiag.steps')}</h4>
        <ol class="steps">
          {#each adviceSteps(main.code, main.params) as step (step)}<li>{t(step)}</li>{/each}
        </ol>
      {:else}
        <Banner kind="ok" title={t('radiodiag.allOk')} />
      {/if}
    {/if}
  </div>
</Modal>

<style>
  .diag {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    font: 400 14px/20px var(--font-sans);
    color: var(--ink);
  }
  .checks {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .checks li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  h4 {
    margin: 0;
    font: 600 14px/20px var(--font-sans);
  }
  .steps {
    margin: 0;
    padding-left: var(--space-5, 20px);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
  }
</style>
