<script lang="ts">
  import Card from '../../lib/ui/Card.svelte'
</script>

<Card>
  <section class="sec">
    <h3>Diagnostica</h3>
    <p class="ui-hint">
      Il pacchetto contiene la parte finale del log, la versione, le impostazioni senza password né chiavi, le dimensioni del database e lo stato di MQTT e delle radio. Non viene inviato a nessuno: lo salvi tu e lo alleghi a una segnalazione.
    </p>
    <div class="row">
      <a class="ui-btn" href="/api/diagnostics/bundle" download>Scarica pacchetto diagnostico</a>
    </div>
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  a.ui-btn { text-decoration: none; }
</style>
