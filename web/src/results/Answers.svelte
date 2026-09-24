<script lang="ts">
  // Jev's answers as bars from 0 to 1, with the 0.5 line the rule table decides on.
  import { fixed, words } from '../lib/format';
  import type { Info } from '../lib/types';

  let { answers, info }: { answers: Record<string, number>; info: Info | null } = $props();

  const ROUTING = ['text_layer_trustworthy', 'mostly_handwritten', 'camera_or_fax', 'heavily_degraded', 'capture_defects', 'complex_layout'];
  const SCORES = new Set(['degradation']); // answered on a 0 to 3 scale, shown with the modifiers below

  const groups = $derived.by(() => {
    const group = (q: string) => info?.questions[q]?.group ?? (ROUTING.includes(q) ? 'routing' : q === 'continues_previous' ? 'continuation' : 'modifier');
    const keys = Object.keys(answers).filter((q) => !SCORES.has(q));
    return [
      { name: 'Routing', keys: keys.filter((q) => group(q) === 'routing') },
      { name: 'Modifiers', keys: keys.filter((q) => group(q) === 'modifier') },
      { name: 'Continuation', keys: keys.filter((q) => group(q) === 'continuation') },
    ].filter((g) => g.keys.length);
  });
</script>

{#each groups as g (g.name)}
  <div class="group">
    <p class="label muted">{g.name}</p>
    {#each g.keys as q (q)}
      {@const v = answers[q] ?? 0}
      <div class="row" title={info?.questions[q]?.instructions ?? ''}>
        <span class="name">{words(q)}</span>
        <span class="track" class:yes={v >= 0.5}><i style:width="{Math.min(1, Math.max(0, v)) * 100}%"></i></span>
        <span class="mono value">{fixed(v)}</span>
      </div>
    {/each}
  </div>
{/each}

<style>
  .group {
    display: grid;
    gap: 5px;
  }

  .group + .group {
    margin-top: 10px;
  }

  .row {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(80px, 1fr) 36px;
    align-items: center;
    gap: 10px;
    font-size: 13px;
  }

  .name {
    color: var(--ink-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .track {
    position: relative;
    height: 8px;
    background: var(--surface-2);
    border-radius: 2px;
  }

  .track::after {
    content: '';
    position: absolute;
    left: 50%;
    top: -3px;
    bottom: -3px;
    width: 1px;
    background: var(--ink-3);
  }

  .track i {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--ink-3);
  }

  .track.yes i {
    background: var(--ink);
  }

  .value {
    font-size: 12px;
    text-align: right;
  }
</style>
