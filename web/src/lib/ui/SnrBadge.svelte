<script lang="ts">
  import { signed } from '../format'
  import { snrClass, snrGlyph } from './logic'

  let { value }: { value: number | null | undefined } = $props()
  const cls = $derived(snrClass(value))
</script>

<span class="ui-snr {cls}" title="SNR"><span aria-hidden="true">{snrGlyph(cls)}</span>{value === null || value === undefined ? '–' : `${signed(value, 1)} dB`}</span>
