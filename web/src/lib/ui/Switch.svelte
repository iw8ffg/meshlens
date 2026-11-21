<script lang="ts">
  interface Props {
    checked?: boolean
    label: string
    disabled?: boolean
    onchange?: (v: boolean) => void
  }
  let { checked = $bindable(false), label, disabled = false, onchange }: Props = $props()

  function toggle() {
    checked = !checked
    onchange?.(checked)
  }
</script>

<button type="button" class="ui-switch" role="switch" aria-checked={checked} {disabled} onclick={toggle}>
  <span class="trk"></span><span>{label}</span>
</button>
