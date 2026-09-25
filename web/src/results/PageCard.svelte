<script lang="ts">
  import { fixed, words } from '../lib/format';
  import type { DocView, PageView } from '../lib/reducer';
  import { STAGES } from '../lib/types';
  import LaneChip from '../ui/LaneChip.svelte';
  import { thumbFor } from './thumbs';

  let {
    doc,
    page,
    live,
    selected,
    onselect,
  }: { doc: DocView; page: PageView; live: boolean; selected: boolean; onselect: () => void } = $props();

  const src = $derived(thumbFor(doc, page, live));
  const route = $derived(page.route);
  const review = $derived(route?.lane === 'LH' && route.candidate_lane !== 'LH');
</script>

<button class="card" class:selected aria-pressed={selected} onclick={onselect}>
  <span class="thumb" class:blank={!src}>
    {#if src}
      <img {src} alt="Page {page.index + 1} of {doc.name}" loading="lazy" decoding="async" />
    {:else}
      <span class="mono muted">{route ? doc.kind : 'routing'}</span>
    {/if}
  </span>
  <span class="meta">
    <span class="row">
      <span class="mono muted">P{page.index + 1}</span>
      {#if route}
        <LaneChip lane={route.lane} />
        {#if review}<span class="mono muted">from</span><LaneChip lane={route.candidate_lane} />{/if}
        <span class="mono conf" title="Calibrated probability that the candidate lane is right">{fixed(route.confidence)}</span>
      {:else}
        <span class="stages" aria-label="Pipeline progress">
          {#each STAGES as s (s)}
            <i class={page.stages[s] ?? 'todo'} title="{s}: {page.stages[s] ?? 'waiting'}"></i>
          {/each}
        </span>
      {/if}
    </span>
    {#if route?.modifiers.length}
      <span class="mods mono">{route.modifiers.map(words).join(' · ')}</span>
    {/if}
  </span>
</button>

<style>
  .card {
    display: grid;
    grid-template-rows: auto 1fr;
    width: 100%;
    padding: 0;
    border: 1px solid var(--rule-soft);
    background: var(--surface);
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.2s var(--ease),
      box-shadow 0.2s var(--ease);
  }

  .card:hover {
    border-color: var(--ink-3);
  }

  .card.selected {
    border-color: var(--rule);
    box-shadow: 4px 4px 0 var(--rule-soft);
  }

  .thumb {
    aspect-ratio: 3 / 4;
    display: grid;
    place-items: center;
    background: var(--surface-2);
    overflow: hidden;
    border-bottom: 1px solid var(--rule-soft);
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .thumb.blank {
    background-image: radial-gradient(var(--rule-soft) 1px, transparent 1.2px);
    background-size: 6px 6px;
  }

  .thumb.blank span {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: var(--surface-2);
    padding: 2px 6px;
  }

  .meta {
    display: grid;
    gap: 6px;
    padding: 9px 10px 10px;
    align-content: start;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    min-width: 0;
  }

  .conf {
    margin-left: auto;
    font-size: 12px;
  }

  .mods {
    font-size: 11px;
    color: var(--ink-2);
    line-height: 1.35;
  }

  .stages {
    display: flex;
    gap: 3px;
    margin-left: auto;
  }

  .stages i {
    width: 8px;
    height: 8px;
    border-radius: 1.5px;
    background: var(--rule-soft);
  }

  .stages .done {
    background: var(--ink);
  }

  .stages .skip {
    background: transparent;
    box-shadow: inset 0 0 0 1px var(--ink-3);
  }

  .stages .fail {
    background: var(--lane-LQ);
  }

  .stages .start {
    background: var(--ink-2);
    animation: pulse 1s var(--ease) infinite alternate;
  }

  @keyframes pulse {
    to {
      opacity: 0.25;
    }
  }
</style>
