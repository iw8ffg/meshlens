<script lang="ts">
  import { t } from '../i18n/index.svelte'
  import { countryName } from '../format'
  interface Props {
    /** Codice ISO 3166-1 alpha-2. */
    code: string | null | undefined
    name?: string
  }
  let { code, name }: Props = $props()
  const cc = $derived(code && /^[A-Za-z]{2}$/.test(code) ? code.toLowerCase() : null)
</script>

<!-- SVG 4x3 di flag-icons (MIT), copiati in public/flags solo per le nazioni dell'elenco dei paesi: nessuna emoji. -->
{#if cc}
  <img class="ui-flag" src={`${import.meta.env.BASE_URL}flags/${cc}.svg`} alt={name ?? countryName(cc)} width="18" height="12" loading="lazy" decoding="async" />
{:else}
  <span class="ui-flag ui-flag-unk" role="img" aria-label={t('common.unknownCountry')}>?</span>
{/if}
