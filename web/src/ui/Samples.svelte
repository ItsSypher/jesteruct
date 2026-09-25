<script lang="ts">
  import { runSample, studio } from '../lib/studio.svelte';
  import type { Lane } from '../lib/types';
  import LaneChip from './LaneChip.svelte';

  const extension = (file: string) => file.split('.').pop() ?? '';
</script>

<div class="samples">
  {#each studio.samples as s (s.file)}
    <article class="sample">
      <header>
        <span class="kind mono">{extension(s.file)}</span>
        <h3>{s.title}</h3>
      </header>
      <p class="shows">{s.shows}</p>
      <p class="lanes">
        <span class="label muted">Labelled</span>
        {#each s.lanes as l (l)}<LaneChip lane={l as Lane} />{/each}
      </p>
      <footer>
        <span class="source mono muted">{s.file} · {s.source}</span>
        <button class="pill" disabled={studio.mode !== 'live'} onclick={() => runSample(s)}>Route</button>
      </footer>
    </article>
  {/each}
</div>

<style>
  .samples {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    border-top: 1px solid var(--rule-soft);
    border-left: 1px solid var(--rule-soft);
  }

  .sample {
    display: grid;
    grid-template-rows: auto 1fr auto auto;
    gap: 12px;
    padding: 20px 20px 18px;
    border-right: 1px solid var(--rule-soft);
    border-bottom: 1px solid var(--rule-soft);
    transition: background-color 0.25s var(--ease);
  }

  .sample:hover {
    background: var(--surface);
  }

  header {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  h3 {
    font-size: 19px;
  }

  .kind {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 5px;
    border: 1px solid var(--rule-soft);
    border-radius: 3px;
    color: var(--ink-2);
  }

  .shows {
    font-size: 14px;
    color: var(--ink-2);
  }

  .lanes {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  footer {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 12px;
  }

  .source {
    font-size: 11px;
    line-height: 1.4;
  }

  .pill {
    height: 32px;
    padding: 0 14px;
    font-size: 11px;
    flex: none;
  }
</style>
