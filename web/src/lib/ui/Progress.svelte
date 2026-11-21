<script lang="ts">
  interface Props {
    /** Percentuale 0-100. */
    value: number
    kind?: 'accent' | 'ok' | 'warn' | 'danger'
    /** Testo accanto alla barra («38%», «3/25»); di default la percentuale. */
    text?: string
    label?: string
  }
  let { value, kind = 'accent', text, label }: Props = $props()
  const pct = $derived(Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0)))
</script>

<div class="ui-progress-wrap">
  <div class="ui-progress {kind === 'accent' ? '' : kind}" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin="0" aria-valuemax="100" aria-label={label}>
    <i style="width: {pct}%"></i>
  </div>
  <span class="ui-mono">{text ?? `${Math.round(pct)}%`}</span>
</div>
