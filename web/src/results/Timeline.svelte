<script lang="ts">
  // Where a page's time went. OCR and vision run side by side after the probes, and Jev ends the page.
  import { ms } from '../lib/format';
  import type { PageRoute } from '../lib/types';

  let { timings }: { timings: PageRoute['timings_ms'] } = $props();

  const rows = $derived.by(() => {
    const t = timings;
    const probe = t.probe ?? 0;
    const total = Math.max(t.total ?? 0, probe + Math.max(t.ocr ?? 0, t.vision ?? 0) + (t.jev ?? 0), 1);
    const out: { name: string; start: number; length: number }[] = [];
    if (t.probe != null) out.push({ name: 'probe', start: 0, length: probe });
    if (t.ocr != null) out.push({ name: 'ocr', start: probe, length: t.ocr });
    if (t.vision != null) out.push({ name: 'vision', start: probe, length: t.vision });
    if (t.jev != null) out.push({ name: 'jev', start: total - t.jev, length: t.jev });
    return { total, rows: out.map((r) => ({ ...r, left: (r.start / total) * 100, width: Math.max(0.6, (r.length / total) * 100) })) };
  });
</script>

{#if rows.rows.length}
  <div class="timeline">
    {#each rows.rows as r (r.name)}
      <span class="name mono muted">{r.name}</span>
      <span class="track"><i style:left="{r.left}%" style:width="{r.width}%"></i></span>
      <span class="mono value">{ms(r.length)}</span>
    {/each}
    <span class="name mono">total</span>
    <span class="axis"></span>
    <span class="mono value">{ms(timings.total)}</span>
  </div>
{:else}
  <p class="muted">Decided at intake, without probing.</p>
{/if}

<style>
  .timeline {
    display: grid;
    grid-template-columns: 48px 1fr 56px;
    align-items: center;
    gap: 6px 10px;
    font-size: 12px;
  }

  .track {
    position: relative;
    height: 10px;
    background: repeating-linear-gradient(90deg, var(--rule-soft) 0 1px, transparent 1px 10%);
  }

  .track i {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--ink);
    border-radius: 1.5px;
  }

  .axis {
    height: 1px;
    background: var(--rule);
  }

  .value {
    text-align: right;
  }
</style>
