<script lang="ts">
  import { tick } from 'svelte'
  import Icon from '../../lib/ui/Icon.svelte'
  import { REACTIONS } from '../../lib/reactions'
  import { t } from '../../lib/i18n/index.svelte'
  import type { Message } from '../../lib/types'

  interface Props {
    msg: Message
    onreply: (m: Message) => void
    onreact: (m: Message, emoji: string) => void
  }
  let { msg, onreply, onreact }: Props = $props()

  let open = $state(false)
  let btn = $state<HTMLButtonElement | null>(null)
  let menu = $state<HTMLElement | null>(null)

  async function toggle() {
    open = !open
    if (open) {
      await tick()
      menu?.querySelector<HTMLElement>('button')?.focus()
    }
  }

  function close(refocus = false) {
    open = false
    if (refocus) btn?.focus()
  }

  function pickReply() {
    close(true)
    onreply(msg)
  }

  function pickReaction(emoji: string) {
    close(true)
    onreact(msg, emoji)
  }

  function onwindowclick(e: MouseEvent) {
    if (!open) return
    const target = e.target as Node
    if (!menu?.contains(target) && !btn?.contains(target)) open = false
  }

  function onmenukey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      close(true)
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Home' || e.key === 'End') {
      const items = [...(menu?.querySelectorAll<HTMLElement>('button') ?? [])]
      if (!items.length) return
      e.preventDefault()
      const i = items.indexOf(document.activeElement as HTMLElement)
      const fwd = e.key === 'ArrowDown' || e.key === 'ArrowRight'
      const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (fwd ? 1 : -1) + items.length) % items.length
      items[next].focus()
    }
  }
</script>

<svelte:window onclick={onwindowclick} />

{#if msg.packet_id}
  <span class="act">
    <button
      type="button"
      class="trg"
      bind:this={btn}
      aria-label={t('chat.messageActions')}
      title={t('chat.messageActions')}
      aria-haspopup="menu"
      aria-expanded={open}
      onclick={toggle}
    >
      <Icon name="smile" size={16} />
    </button>
    {#if open}
      <div class="menu" role="menu" tabindex="-1" bind:this={menu} onkeydown={onmenukey}>
        <button type="button" role="menuitem" class="item" onclick={pickReply}>
          <Icon name="reply" size={16} />{t('chat.reply')}
        </button>
        <div class="emojis">
          {#each REACTIONS as e (e)}
            <button type="button" role="menuitem" class="em" aria-label={t('chat.reactWith', { emoji: e })} title={t('chat.reactWith', { emoji: e })} onclick={() => pickReaction(e)}>{e}</button>
          {/each}
        </div>
      </div>
    {/if}
  </span>
{/if}

<style>
  .act {
    position: relative;
    display: inline-flex;
  }
  .trg {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    background: none;
    border: 0;
    border-radius: var(--radius-md);
    color: inherit;
    cursor: pointer;
  }
  .trg:hover {
    background: var(--surface-sunken);
    color: var(--ink);
  }
  .trg:focus-visible,
  .item:focus-visible,
  .em:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .menu {
    position: absolute;
    bottom: 100%;
    right: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-1);
    background: var(--surface-raised);
    color: var(--ink);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-md);
    min-width: 220px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 36px;
    padding: 0 var(--space-2);
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
    color: inherit;
    font: 500 14px/20px var(--font-sans);
    text-align: left;
    cursor: pointer;
  }
  .emojis {
    display: flex;
    gap: var(--space-1);
  }
  .em {
    min-width: 36px;
    min-height: 36px;
    padding: 0;
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
    font-size: 20px;
    line-height: 1;
    cursor: pointer;
  }
  .item:hover,
  .em:hover {
    background: var(--surface-sunken);
  }
  :global(.vp-phone) .trg {
    min-width: var(--touch-min);
    min-height: var(--touch-min);
  }
  :global(.vp-phone) .item,
  :global(.vp-phone) .em {
    min-height: var(--touch-min);
  }
  :global(.vp-phone) .em {
    min-width: 44px;
  }
  :global(.vp-phone) .menu {
    min-width: min(300px, 80vw);
  }
</style>
