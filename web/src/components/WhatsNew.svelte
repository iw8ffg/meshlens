<script lang="ts">
  // Finestra «Novità» dopo un aggiornamento (E18). Nessuna prop (contratto §10.2).
  // Il testo del CHANGELOG si mostra come testo (mai come HTML).
  import { onMount } from 'svelte'
  import { i18n, t } from '../lib/i18n/index.svelte'
  import { parseNotes, pickLang } from '../lib/whatsnew'
  import { closeWhatsNew, initWhatsNew, whatsNew } from '../lib/whatsnew.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  onMount(() => void initWhatsNew())

  const releases = $derived(
    (whatsNew.data?.releases ?? []).map((r) => ({ ...r, blocks: parseNotes(pickLang(r, i18n.lang)) })),
  )
</script>

<Modal
  open={whatsNew.open && releases.length > 0}
  title={t('whatsnew.title')}
  confirmLabel={t('whatsnew.ok')}
  cancelLabel={t('whatsnew.close')}
  onconfirm={() => void closeWhatsNew()}
  oncancel={() => void closeWhatsNew()}
>
  <div class="notes">
    {#each releases as r (r.version)}
      <h3>{r.date ? t('whatsnew.versionDate', { v: r.version, date: r.date }) : t('whatsnew.version', { v: r.version })}</h3>
      {#each r.blocks as b, i (i)}
        {#if b.type === 'h'}
          <h4>{#each b.parts as p, j (j)}{#if p.bold}<b>{p.text}</b>{:else}{p.text}{/if}{/each}</h4>
        {:else if b.type === 'li'}
          <p class="li">{#each b.parts as p, j (j)}{#if p.bold}<b>{p.text}</b>{:else}{p.text}{/if}{/each}</p>
        {:else}
          <p>{#each b.parts as p, j (j)}{#if p.bold}<b>{p.text}</b>{:else}{p.text}{/if}{/each}</p>
        {/if}
      {/each}
    {/each}
  </div>
</Modal>

<style>
  .notes {
    max-height: 60vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font: 400 14px/20px var(--font-sans);
    color: var(--ink);
  }
  h3 {
    margin: var(--space-2) 0 0;
    font: 600 15px/20px var(--font-sans);
  }
  h4 {
    margin: var(--space-1) 0 0;
    font: 600 14px/20px var(--font-sans);
  }
  p {
    margin: 0;
  }
  .li {
    padding-left: var(--space-4);
    text-indent: calc(-1 * var(--space-3));
  }
  .li::before {
    content: '• ';
  }
</style>
