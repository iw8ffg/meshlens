<script lang="ts" generics="T extends string">
  interface Props {
    items: { value: T; label: string }[]
    value: T
    fill?: boolean
    label?: string
    onchange?: (v: T) => void
  }
  let { items, value = $bindable(), fill = false, label, onchange }: Props = $props()

  function pick(v: T) {
    if (v === value) return
    value = v
    onchange?.(v)
  }
  function onkey(e: KeyboardEvent) {
    const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!dir) return
    e.preventDefault()
    const i = items.findIndex((x) => x.value === value)
    const next = items[(i + dir + items.length) % items.length]
    pick(next.value)
    ;(e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-v="${next.value}"]`)?.focus()
  }
</script>

<div class="ui-seg" class:fill role="radiogroup" aria-label={label} tabindex="-1" onkeydown={onkey}>
  {#each items as it (it.value)}
    <button type="button" role="radio" aria-checked={it.value === value} data-v={it.value} tabindex={it.value === value ? 0 : -1} onclick={() => pick(it.value)}>{it.label}</button>
  {/each}
</div>
