<script lang="ts">
  // Page ranges coloured by lane: the manifest's segments once the document is done, each page's lane until then.
  import { LANE_NAMES } from '../lib/copy';
  import type { DocView } from '../lib/reducer';
  import type { Lane } from '../lib/types';

  let { doc, tall = false }: { doc: DocView; tall?: boolean } = $props();

  type Run = { start: number; end: number; lane: Lane | null };
  const runs = $derived.by((): Run[] => {
    if (doc.done && doc.segments.length) return doc.segments;
    return doc.pages.map((p) => ({ start: p.index, end: p.index, lane: p.route?.lane ?? null }));
  });
  const span = (r: Run) => (r.start === r.end ? `p${r.start + 1}` : `p${r.start + 1}-${r.end + 1}`);
  const label = (r: Run) =>
    `${r.start === r.end ? `Page ${r.start + 1}` : `Pages ${r.start + 1} to ${r.end + 1}`}: ${r.lane ? `${r.lane}, ${LANE_NAMES[r.lane]}` : 'routing'}`;
</script>

<div class="segments" class:tall role="img" aria-label={runs.map(label).join('; ')}>
  <div class="bar">
    {#each runs as r (r.start)}
      <span
        class="run"
        class:pending={!r.lane}
        style:flex-grow={r.end - r.start + 1}
        style:--lane={r.lane ? `var(--lane-${r.lane})` : 'transparent'}
        title={label(r)}
      ></span>
    {/each}
  </div>
  {#if tall}
    <div class="labels mono">
      {#each runs as r (r.start)}
        <span style:flex-grow={r.end - r.start + 1}>{r.lane ?? '..'} <span class="muted">{span(r)}</span></span>
      {/each}
    </div>
  {/if}
</div>

<style>
  .segments {
    min-width: 0;
    display: grid;
    gap: 6px;
  }

  .bar,
  .labels {
    display: flex;
    gap: 2px;
  }

  .bar {
    height: 6px;
  }

  .tall .bar {
    height: 18px;
  }

  .run,
  .labels > span {
    flex-basis: 0;
    min-width: 4px;
  }

  .run {
    background: var(--lane);
    border-radius: 2px;
  }

  .labels > span {
    font-size: 11px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: clip;
  }

  .pending {
    background: repeating-linear-gradient(135deg, var(--rule-soft) 0 2px, transparent 2px 5px);
  }
</style>
