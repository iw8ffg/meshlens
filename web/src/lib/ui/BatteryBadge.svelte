<script lang="ts">
  import { num } from '../format'
  import Icon from './Icon.svelte'
  import { batteryClass } from './logic'

  interface Props {
    /** Percentuale 0-100. */
    pct: number
    /** Nodo alimentato: spina e «USB» al posto della percentuale. */
    usb?: boolean
  }
  let { pct, usb = false }: Props = $props()
  const cls = $derived(batteryClass(pct, usb))
</script>

<span class="ui-batt {cls}">
  <Icon name={usb ? 'plug' : 'battery'} size={16} />{usb ? 'USB' : `${num(pct)}%`}
</span>
