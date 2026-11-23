<script lang="ts">
  // Messaggi rapidi accanto al campo del compositore (WP1, E10): scegliere una voce la inserisce nel
  // campo, non invia nulla.
  import { onMount } from 'svelte'
  import { t } from '../../lib/i18n/index.svelte'
  import { loadQuickReplies, quick } from '../../lib/quickreplies.svelte'
  import Button from '../../lib/ui/Button.svelte'

  let { disabled, onpick, onmanage }: { disabled: boolean; onpick: (text: string) => void; onmanage: () => void } = $props()

  const uid = $props.id()
  let open = $state(false)
  let root: HTMLElement | undefined = $state()

  onMount(() => {
    void loadQuickReplies()
  })

  function close(refocus = false) {
    open = false
    if (refocus) root?.querySelector<HTMLElement>('button')?.focus()
  }

  function pick(text: string) {
    close()
    onpick(text)
  }

  const items = () => [...(root?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]

  // all'apertura il focus passa alla prima voce (o al pulsante "aggiungi" se l'elenco e' vuoto)
  $effect(() => {
    if (!open) return
    queueMicrotask(() => (items()[0] ?? root?.querySelector<HTMLElement>('.menu button'))?.focus())
  })

  function onkey(e: KeyboardEvent) {
    if (!open) return
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      close(true)
      return
    }
    if (e.key === 'Tab') {
      open = false // il menu non intrappola il focus: Tab lo chiude e prosegue
      return
    }
    const list = items()
    if (!list.length) return
    const cur = list.indexOf(document.activeElement as HTMLElement)
    let next = -1
    if (e.key === 'ArrowDown') next = (cur + 1) % list.length
    else if (e.key === 'ArrowUp') next = cur <= 0 ? list.length - 1 : cur - 1
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = list.length - 1
    if (next >= 0) {
      e.preventDefault()
      list[next].focus()
    }
  }
</script>

<svelte:window onpointerdown={(e) => { if (open && root && !root.contains(e.target as Node)) open = false }} />

<div class="qr" bind:this={root} onkeydown={onkey} role="presentation">
  <Button iconOnly icon="reply" label={t('chat.quick.open')} {disabled} aria-haspopup="menu" aria-expanded={open} aria-controls="{uid}-menu" onclick={() => (open = !open)} />
  {#if open}
    <div class="menu" id="{uid}-menu" role="menu" aria-label={t('chat.quick.menu')}>
      {#if quick.list.length === 0}
        <p class="empty">{t('chat.quick.empty')}</p>
        <Button kind="primary" onclick={() => { close(); onmanage() }}>{t('chat.quick.add')}</Button>
      {:else}
        {#each quick.list as r (r)}
          <button type="button" role="menuitem" class="it" onclick={() => pick(r)}>{r}</button>
        {/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .qr { position: relative; flex: none; }
  .menu {
    position: absolute;
    bottom: calc(100% + var(--space-2));
    left: 0;
    z-index: var(--z-panel);
    width: min(320px, calc(100vw - 2 * var(--space-4)));
    max-height: 50vh;
    overflow: auto;
    background: var(--surface-raised);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-2);
    padding: var(--space-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .it {
    min-height: var(--touch-min);
    text-align: left;
    background: none;
    border: 0;
    border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3);
    color: var(--ink);
    font: 400 14px/20px var(--font-sans);
    cursor: pointer;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: anywhere;
  }
  .it:hover { background: var(--accent-soft); }
  .it:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .empty { margin: 0; color: var(--ink-muted); font-size: 14px; }
</style>
