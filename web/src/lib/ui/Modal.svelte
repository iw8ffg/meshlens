<script lang="ts">
  import { t } from '../i18n/index.svelte'
  import type { Snippet } from 'svelte'
  import Button from './Button.svelte'
  import Check from './Check.svelte'

  interface Props {
    open: boolean
    title: string
    /** Variante a rischio: bordo danger, role="alertdialog", conferma bloccata finché non spunti la casella. */
    risk?: boolean
    /** Testo della casella di conferma (solo `risk`). */
    riskLabel?: string
    confirmLabel?: string
    cancelLabel?: string
    /** Pulsante di conferma in stile danger (di default lo è se `risk`). */
    danger?: boolean
    onconfirm?: () => void
    oncancel?: () => void
    children: Snippet
  }
  let {
    open,
    title,
    risk = false,
    riskLabel,
    confirmLabel,
    cancelLabel,
    danger,
    onconfirm,
    oncancel,
    children,
  }: Props = $props()

  // testi predefiniti nella lingua corrente (un default dei props non seguirebbe il cambio lingua)
  const riskText = $derived(riskLabel ?? t('common.riskAck'))
  const confirmText = $derived(confirmLabel ?? t('common.confirm'))
  const cancelText = $derived(cancelLabel ?? t('common.cancel'))
  const uid = $props.id()
  let ack = $state(false)
  const canConfirm = $derived(!risk || ack)

  // Alla chiusura la casella si azzera: scrive `ack` senza leggerlo.
  $effect(() => {
    if (!open) ack = false
  })

  const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

  /** Focus iniziale su Annulla, trappola di Tab, Esc annulla, ripristino del focus alla chiusura. */
  function dialog(node: HTMLElement) {
    const prev = document.activeElement as HTMLElement | null
    ;(node.querySelector<HTMLElement>('[data-autofocus]') ?? node).focus()
    const onkey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        oncancel?.()
        return
      }
      if (e.key !== 'Tab') return
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (!items.length) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === node)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    node.addEventListener('keydown', onkey)
    return {
      destroy() {
        node.removeEventListener('keydown', onkey)
        prev?.focus?.()
      },
    }
  }

  function confirm() {
    if (canConfirm) onconfirm?.()
  }
</script>

{#if open}
  <div class="ui-modalbg" role="presentation" onpointerdown={(e) => { if (e.target === e.currentTarget && !risk) oncancel?.() }}>
    <div
      class="ui-modal"
      class:risk
      role={risk ? 'alertdialog' : 'dialog'}
      aria-modal="true"
      aria-labelledby="{uid}-t"
      tabindex="-1"
      use:dialog
    >
      <h2 id="{uid}-t">{title}</h2>
      <div>{@render children()}</div>
      {#if risk}<Check risk bind:checked={ack} label={riskText} />{/if}
      <div class="acts">
        <Button onclick={() => oncancel?.()} data-autofocus={risk || undefined}>{cancelText}</Button>
        <Button kind={danger ?? risk ? 'danger' : 'primary'} disabled={!canConfirm} onclick={confirm}>{confirmText}</Button>
      </div>
    </div>
  </div>
{/if}
