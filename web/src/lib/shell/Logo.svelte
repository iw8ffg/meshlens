<script lang="ts">
  // Marchio MeshLens (docs/img/logo.svg) con i colori di marchio dei token: segue il tema.
  let { size = 28 }: { size?: number } = $props()
</script>

<svg viewBox="0 0 256 256" width={size} height={size} aria-hidden="true" focusable="false">
  <g stroke="var(--brand-teal)" stroke-width="5" stroke-linecap="round" fill="none">
    <path d="M48 70 L110 44 L176 70 L208 128 M48 70 L66 138 L110 44 M66 138 L128 168 L176 70 M128 168 L208 128 M66 138 L48 200" />
  </g>
  <g fill="var(--brand-sky)">
    <circle cx="48" cy="70" r="10" /><circle cx="110" cy="44" r="10" /><circle cx="176" cy="70" r="10" />
    <circle cx="66" cy="138" r="10" /><circle cx="208" cy="128" r="10" /><circle cx="48" cy="200" r="10" />
  </g>
  <circle cx="128" cy="124" r="52" fill="var(--brand-teal)" fill-opacity="0.18" stroke="var(--brand-teal)" stroke-width="12" />
  <path d="M166 162 L222 218" stroke="var(--brand-teal)" stroke-width="18" stroke-linecap="round" />
  <circle cx="128" cy="168" r="11" fill="var(--brand-amber)" />
</svg>
