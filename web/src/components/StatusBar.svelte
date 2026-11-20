<script lang="ts">
  import { app } from '../lib/stores.svelte'
  let { visible }: { visible: number } = $props()
  const mqtt = $derived(app.status?.mqtt ?? null)
</script>

<div class="bar">
  <span class="item">
    <span class="dot" class:ok={mqtt?.connected} class:ko={mqtt && !mqtt.connected}></span>
    MQTT {mqtt ? (mqtt.connected ? 'connesso' : 'non connesso') : '…'}
  </span>
  <span>{mqtt ? mqtt.msgs_per_s.toFixed(1).replace('.', ',') : '–'} msg/s</span>
  <span>{visible} nodi visibili</span>
</div>

<style>
  .bar {
    display: flex;
    gap: 14px;
    align-items: center;
    padding: 6px 12px;
    background: #0b1220;
    font-size: 13px;
    border-bottom: 1px solid #1f2937;
  }
  .item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #6b7280;
    display: inline-block;
  }
  .dot.ok {
    background: #2e9e44;
  }
  .dot.ko {
    background: #dc2626;
  }
</style>
