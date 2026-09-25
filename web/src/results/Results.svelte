<script lang="ts">
  import { LANE_NAMES } from '../lib/copy';
  import { bytes, ms, plural, usd } from '../lib/format';
  import { type DocView, laneCounts, median } from '../lib/reducer';
  import { current, select, studio } from '../lib/studio.svelte';
  import { LANES } from '../lib/types';
  import LaneChip from '../ui/LaneChip.svelte';
  import PageCard from './PageCard.svelte';
  import PageDetail from './PageDetail.svelte';
  import Segments from './Segments.svelte';

  const m = $derived(current());
  const live = $derived(studio.mode === 'live');
  const jobs = $derived(m.order.map((id) => m.jobs[id]!).filter((j) => j.docs.length || j.status !== 'done'));
  const uploading = $derived(studio.uploads.filter((u) => !u.job || !m.jobs[u.job]));
  const doc = $derived(studio.selected ? (m.docs[studio.selected] ?? null) : null);
  const page = $derived(doc && studio.page != null ? (doc.pages[studio.page] ?? null) : null);

  const summary = $derived.by(() => {
    const docs = Object.values(m.docs);
    const lanes = laneCounts(m);
    const routed = LANES.reduce((n, l) => n + lanes[l], 0);
    const cost = docs.reduce((c, d) => c + (d.cost ?? 0), 0);
    return { docs: docs.length, routed, lanes, cost, p50: median(m.timings.total) };
  });

  const routedPages = (d: DocView) => d.pages.filter((p) => p.route).length;
  const pageTotal = (d: DocView) => Math.max(d.pages.length, d.page_count, 1);
</script>

<div class="summary">
  <div class="figures">
    <p><span class="big mono">{summary.docs}</span><span class="label muted">documents</span></p>
    <p><span class="big mono">{summary.routed}</span><span class="label muted">pages routed</span></p>
    <p><span class="big mono">{ms(summary.p50)}</span><span class="label muted">page p50</span></p>
    <p><span class="big mono">{usd(summary.cost)}</span><span class="label muted">spent</span></p>
  </div>
  <div class="distribution">
    <div class="stack" role="img" aria-label="Pages per lane">
      {#each LANES as l (l)}
        {#if summary.lanes[l]}<span style:flex-grow={summary.lanes[l]} style:--lane="var(--lane-{l})" title="{l} {LANE_NAMES[l]}: {summary.lanes[l]}"></span>{/if}
      {/each}
      {#if !summary.routed}<span class="none"></span>{/if}
    </div>
    <div class="legend">
      {#each LANES as l (l)}
        <span class:zero={!summary.lanes[l]}><LaneChip lane={l} /><span class="mono">{summary.lanes[l]}</span></span>
      {/each}
    </div>
  </div>
</div>

<div class="results" class:with-detail={page}>
  <div class="docs" role="list" aria-label="Documents">
    {#each uploading as u (u.id)}
      <div class="upload" role="listitem">
        <span class="name">{u.name}</span>
        <span class="mono muted">{u.error ? 'failed' : u.progress < 1 ? `uploading ${Math.round(u.progress * 100)}%` : 'queued'}</span>
        <span class="progress"><i style:width="{u.progress * 100}%"></i></span>
        {#if u.error}<span class="error mono">{u.error}</span>{/if}
      </div>
    {/each}

    {#each jobs as job (job.id)}
      {@const docs = job.docs.map((sha) => m.docs[sha]).filter((d) => d !== undefined)}
      {@const container = docs.length !== 1 || docs[0]?.name !== job.name}
      <div class="job" role="listitem">
        {#if container}
          <p class="job-head">
            <span class="name">{job.name || job.id}</span>
            <span class="mono muted">{job.size != null ? bytes(job.size) : ''}</span>
            <span class="status mono" data-status={job.status}>{job.status}</span>
          </p>
        {/if}
        {#if job.error}<p class="error mono">{job.error}{job.deliveries > 1 ? ` (attempt ${job.deliveries})` : ''}</p>{/if}
        {#each docs as d (d.sha)}
          <button class="doc" class:child={container} class:selected={studio.selected === d.sha} onclick={() => select(d.sha)}>
            <span class="row">
              <span class="kind mono">{d.kind}</span>
              <span class="name">{d.name}</span>
              <span class="mono muted">{routedPages(d)}/{plural(pageTotal(d), 'page')}</span>
            </span>
            <Segments doc={d} />
            <span class="row small mono muted">
              <span>{d.quarantine ? `quarantined: ${d.quarantine}` : d.done ? (d.cached ? 'done, from the store' : 'done') : 'routing'}</span>
              <span>{usd(d.cost)}</span>
            </span>
          </button>
        {/each}
      </div>
    {:else}
      {#if !uploading.length}<p class="empty muted">Nothing routed yet. Drop a file anywhere on the page, or run the demo.</p>{/if}
    {/each}
  </div>

  <div class="pages">
    {#if doc}
      <header class="doc-head">
        <div>
          <p class="label muted">{doc.kind} · {doc.mime}</p>
          <h3>{doc.name}</h3>
        </div>
        <p class="mono muted">{plural(pageTotal(doc), 'page')} · {usd(doc.cost)}</p>
      </header>
      <Segments {doc} tall />
      <div class="grid">
        {#each doc.pages as p (p.index)}
          <PageCard doc={doc} page={p} {live} selected={studio.page === p.index} onselect={() => select(doc.sha, studio.page === p.index ? null : p.index)} />
        {/each}
      </div>
    {:else}
      <p class="empty muted">Pick a document to see its pages.</p>
    {/if}
  </div>

  {#if doc && page}
    <div class="side">
      <PageDetail {doc} {page} info={studio.info} {live} onclose={() => select(doc.sha, null)} />
    </div>
  {/if}
</div>

<style>
  .summary {
    display: grid;
    grid-template-columns: auto minmax(280px, 1fr);
    gap: 32px 56px;
    align-items: end;
    padding: 28px 0 32px;
  }

  .figures {
    display: flex;
    gap: 40px;
    flex-wrap: wrap;
  }

  .figures p {
    display: grid;
    gap: 6px;
  }

  .big {
    font-size: 34px;
    line-height: 1;
    letter-spacing: -0.04em;
  }

  .distribution {
    display: grid;
    gap: 10px;
  }

  .stack {
    display: flex;
    gap: 2px;
    height: 14px;
  }

  .stack span {
    flex-basis: 0;
    min-width: 3px;
    background: var(--lane);
    border-radius: 2px;
  }

  .stack .none {
    flex-grow: 1;
    background: repeating-linear-gradient(135deg, var(--rule-soft) 0 2px, transparent 2px 5px);
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    font-size: 12px;
  }

  .legend > span {
    display: inline-flex;
    gap: 6px;
    align-items: center;
  }

  .legend .zero {
    opacity: 0.45;
  }

  .results {
    display: grid;
    grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
    gap: 28px;
    align-items: start;
  }

  .results.with-detail {
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(360px, 440px);
  }

  .docs,
  .side {
    position: sticky;
    top: 76px;
    max-height: calc(100vh - 96px);
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .docs {
    display: grid;
    gap: 8px;
    align-content: start;
    padding: 0 8px 8px 0;
  }

  .side {
    padding: 0 8px 8px 0;
  }

  .job {
    display: grid;
    gap: 6px;
  }

  .job-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    font-size: 14px;
    padding: 4px 0 0;
  }

  .status {
    margin-left: auto;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ink-3);
  }

  .status[data-status='running'] {
    color: var(--ink);
  }

  .status[data-status='failed'] {
    color: var(--lane-LQ);
  }

  .doc,
  .upload {
    display: grid;
    gap: 7px;
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--rule-soft);
    background: var(--surface);
    text-align: left;
    cursor: pointer;
    transition: border-color 0.2s var(--ease);
  }

  .doc:hover {
    border-color: var(--ink-3);
  }

  .doc.selected {
    border-color: var(--rule);
    box-shadow: 4px 4px 0 var(--rule-soft);
  }

  .doc.child {
    margin-left: 14px;
    width: calc(100% - 14px);
  }

  .row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    min-width: 0;
    font-size: 14px;
  }

  .row.small {
    justify-content: space-between;
    font-size: 11px;
  }

  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row .mono.muted {
    font-size: 12px;
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

  .upload {
    cursor: default;
    grid-template-columns: 1fr auto;
  }

  .progress {
    grid-column: 1 / -1;
    height: 2px;
    background: var(--surface-2);
  }

  .progress i {
    display: block;
    height: 100%;
    background: var(--ink);
    transition: width 0.2s linear;
  }

  .error {
    color: var(--lane-LQ);
    font-size: 11px;
    grid-column: 1 / -1;
  }

  .pages {
    display: grid;
    gap: 18px;
    min-width: 0;
  }

  .doc-head {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 16px;
  }

  .doc-head h3 {
    font-size: 26px;
    margin-top: 4px;
    overflow-wrap: anywhere;
  }

  .doc-head p.mono {
    font-size: 12px;
    white-space: nowrap;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 14px;
  }

  .empty {
    font-size: 14px;
    padding: 24px 0;
  }

  @media (max-width: 1180px) {
    .results.with-detail {
      grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
    }

    .side {
      grid-column: 1 / -1;
      position: static;
      max-height: none;
    }
  }

  @media (max-width: 760px) {
    .summary,
    .results,
    .results.with-detail {
      grid-template-columns: 1fr;
    }

    .docs {
      position: static;
      max-height: none;
    }

    .figures {
      gap: 24px;
    }
  }
</style>
