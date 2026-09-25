<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { EDGE_NOTES, LANE_NAMES, steps } from '../lib/copy';
  import { ms, plural, sentence } from '../lib/format';
  import { median } from '../lib/reducer';
  import { current, onActivity, studio, traffic } from '../lib/studio.svelte';
  import { readPalette, theme } from '../lib/theme.svelte';
  import { LANES, type Lane } from '../lib/types';
  import { EDGES, geometry, type Geometry, NODES, type NodeId, STEPS, type Step } from './graph';
  import { createRenderer, type Renderer } from './renderer';
  import { FLOATS, MAX_TOKENS } from './traffic';

  let host: HTMLDivElement;
  let canvas = $state<HTMLCanvasElement>();
  let g = $state.raw<Geometry | null>(null);
  let kind = $state('');
  let fallback = $state(false);
  let waiting = $state.raw(new Int32Array(NODES.length));
  let landed = $state.raw(new Int32Array(LANES.length));
  let open = $state<NodeId | null>(null);
  let pinned = $state(false);

  const copy = $derived(steps(studio.info));
  const instances = new Float32Array(MAX_TOKENS * FLOATS);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let renderer: Renderer | null = null;
  let raf = 0;
  let last = 0;
  const t0 = performance.now();

  // What the reducer knows, per node: pages that finished the step, and the step's median time.
  const stats = $derived.by(() => {
    const m = current();
    const docs = Object.values(m.docs);
    const done = (stage: 'probe' | 'ocr' | 'vision' | 'jev') =>
      docs.reduce((n, d) => n + d.pages.filter((p) => p.stages[stage] === 'done').length, 0);
    const routed = docs.reduce((n, d) => n + d.pages.filter((p) => p.route).length, 0);
    const t = m.timings;
    return {
      intake: { count: docs.length, noun: 'document', time: null },
      probes: { count: done('probe'), noun: 'page', time: median(t.probe) },
      ocr: { count: done('ocr'), noun: 'page', time: median(t.ocr) },
      vision: { count: done('vision'), noun: 'page', time: median(t.vision) },
      evidence: { count: done('jev'), noun: 'page', time: null },
      jev: { count: done('jev'), noun: 'page', time: median(t.jev) },
      policy: { count: routed, noun: 'page', time: median(t.total) },
    } satisfies Record<Step, { count: number; noun: string; time: number | null }>;
  });
  const total = $derived(landed.reduce((a, b) => a + b, 0));

  function frame(now: number) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    traffic.step(dt);
    paint(now);
    raf = traffic.busy && !document.hidden ? requestAnimationFrame(frame) : 0;
  }

  function paint(now = performance.now()) {
    if (!renderer) return;
    const count = traffic.write(instances);
    renderer.draw({ instances, count, heat: traffic.heat, time: (now - t0) / 1000, animate: !reduced.matches });
  }

  function wake() {
    if (raf || document.hidden || !renderer || !g) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  function layout() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    if (!width || !height) return;
    g = geometry(width, height);
    traffic.setGeometry(g);
    renderer?.resize(g, devicePixelRatio || 1);
    paint();
  }

  async function mountRenderer() {
    renderer?.destroy();
    await tick();
    renderer = await createRenderer(canvas!, lost, fallback);
    kind = renderer.kind;
    renderer.setPalette(readPalette());
    layout();
    wake();
  }

  function lost() {
    // a lost device cannot take a 2D context on the same canvas: remount the canvas, then draw in 2D
    renderer = null;
    fallback = true;
    void mountRenderer();
  }

  onMount(() => {
    const resize = new ResizeObserver(layout);
    resize.observe(host);
    const off = onActivity(wake);
    const visible = () => {
      if (!document.hidden) return wake();
      cancelAnimationFrame(raf);
      raf = 0;
    };
    document.addEventListener('visibilitychange', visible);
    const motion = () => traffic.setReducedMotion(reduced.matches);
    reduced.addEventListener('change', motion);
    // counters go to the DOM a few times a second, never from the frame loop
    let seen = -1;
    const counters = setInterval(() => {
      if (traffic.version === seen) return;
      seen = traffic.version;
      waiting = traffic.waiting.slice();
      landed = traffic.landed.slice();
    }, 200);
    void mountRenderer();
    return () => {
      resize.disconnect();
      off();
      document.removeEventListener('visibilitychange', visible);
      reduced.removeEventListener('change', motion);
      clearInterval(counters);
      cancelAnimationFrame(raf);
      renderer?.destroy();
    };
  });

  $effect(() => {
    void theme.mode;
    renderer?.setPalette(readPalette());
    paint();
  });

  function show(id: NodeId, pin = false) {
    if (pin) {
      pinned = !(pinned && open === id);
      open = pinned ? id : null;
    } else if (!pinned) open = id;
  }

  function hide() {
    if (!pinned) open = null;
  }

  const isLane = (n: NodeId): n is Lane => (LANES as readonly string[]).includes(n);
  const here = (id: NodeId) => waiting[NODES.indexOf(id)] ?? 0;
</script>

<svelte:window
  onkeydown={(e) => e.key === 'Escape' && ((pinned = false), (open = null))}
  onpointerdown={(e) => pinned && !(e.target as Element).closest('.explainer, .node, .lane') && ((pinned = false), (open = null))}
/>

<div class="scroller">
  <div class="flow" bind:this={host}>
    {#key fallback}
      <canvas bind:this={canvas} aria-hidden="true"></canvas>
    {/key}

    {#if g}
      {#each EDGES as e, i (i)}
        {#if e.kind !== 'main'}
          {@const mid = g.edges[i]!.mid}
          <span class="note mono" style:left="{mid.x}px" style:top="{mid.y}px">
            {EDGE_NOTES[e.kind]}
          </span>
        {/if}
      {/each}

      {#each STEPS as id (id)}
        {@const c = g.nodes[id]}
        {@const s = stats[id]}
        <button
          class="node"
          style:left="{c.x}px"
          style:top="{c.y}px"
          aria-expanded={open === id}
          aria-controls="explainer"
          onpointerenter={() => show(id)}
          onpointerleave={hide}
          onfocus={() => show(id)}
          onblur={hide}
          onclick={() => show(id, true)}
        >
          <span class="label">{copy[id].title}</span>
          <span class="line">{copy[id].line}</span>
        </button>
        <div class="stats mono" style:left="{c.x}px" style:top="{c.y}px">
          <span>{s.count.toLocaleString()}</span>
          {#if s.time != null}<span class="muted">p50 {ms(s.time)}</span>{/if}
          {#if here(id) > 24}<span class="muted">+{here(id) - 24} waiting</span>{/if}
        </div>
      {/each}

      {#each LANES as lane, i (lane)}
        {@const c = g.nodes[lane]}
        <button
          class="lane"
          style:left="{c.x}px"
          style:top="{c.y}px"
          style:--lane="var(--lane-{lane})"
          aria-expanded={open === lane}
          aria-controls="explainer"
          onpointerenter={() => show(lane)}
          onpointerleave={hide}
          onfocus={() => show(lane)}
          onblur={hide}
          onclick={() => show(lane, true)}
        >
          <span class="code mono">{lane}</span>
          <span class="name">{LANE_NAMES[lane]}</span>
          <span class="count mono">{landed[i]}</span>
        </button>
      {/each}

      {#if open}
        {@const c = g.nodes[open]}
        <div
          id="explainer"
          class="explainer"
          class:left={c.x > g.width * 0.75}
          class:up={c.x <= g.width * 0.75 && c.y > g.height * 0.55}
          style:left="{c.x}px"
          style:top="{c.y}px"
          role="dialog"
          aria-label="What this step does"
        >
          {#if isLane(open)}
            {@const n = landed[LANES.indexOf(open)] ?? 0}
            <p class="label">/ {open} {LANE_NAMES[open]}</p>
            <p>{sentence(studio.info?.lanes[open] ?? LANE_NAMES[open])}</p>
            <p class="mono muted">{plural(n, 'page')}{total ? `, ${Math.round((n / total) * 100)}% of what landed` : ''}</p>
          {:else}
            {@const e = copy[open]}
            <p class="label">/ {e.title}</p>
            <dl>
              <dt class="label muted">Measures</dt>
              <dd>{e.measures}</dd>
              <dt class="label muted">Why</dt>
              <dd>{e.why}</dd>
              <dt class="label muted">Passes on</dt>
              <dd>{e.passes}</dd>
            </dl>
            <p class="mono muted">
              {plural(stats[open].count, stats[open].noun)}{stats[open].time != null ? `, p50 ${ms(stats[open].time)}` : ''}{here(open)
                ? `, ${here(open)} here now`
                : ''}
            </p>
          {/if}
        </div>
      {/if}
    {/if}
  </div>
</div>
<p class="renderer mono muted">{kind ? `Drawn with ${kind}` : ''}</p>

<style>
  @media (max-width: 1180px) {
    .scroller {
      overflow-x: auto;
      overscroll-behavior-x: contain;
    }
  }

  .flow {
    position: relative;
    min-width: 1080px;
    height: 600px;
    background-image: radial-gradient(var(--dot) 1px, transparent 1.2px);
    background-size: 16px 16px;
    background-position: 8px 8px;
    user-select: none;
  }

  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    pointer-events: none;
  }

  .node,
  .lane {
    position: absolute;
    border: 0;
    background: none;
    padding: 0;
    cursor: pointer;
    text-align: center;
  }

  .node {
    width: 140px;
    height: 74px;
    transform: translate(-50%, calc(-100% - 10px));
    display: grid;
    align-content: start;
    gap: 3px;
    padding: 6px 4px 4px;
    border-radius: 4px;
  }

  .node .line {
    font-size: 12px;
    line-height: 15px;
    color: var(--ink-2);
    text-wrap: balance;
  }

  .node:hover .label,
  .node[aria-expanded='true'] .label {
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .stats {
    position: absolute;
    background: var(--bg);
    padding: 0 4px;
    transform: translate(-50%, 48px);
    display: flex;
    gap: 8px;
    font-size: 11px;
    line-height: 14px;
    white-space: nowrap;
    pointer-events: none;
  }

  .lane {
    transform: translate(14px, -50%);
    display: grid;
    grid-template-columns: 24px 140px auto;
    align-items: baseline;
    gap: 8px;
    text-align: left;
    white-space: nowrap;
    font-size: 13px;
    padding: 2px 4px;
  }

  .lane .code {
    font-size: 12px;
    font-weight: 500;
  }

  .lane .name {
    color: var(--ink-2);
  }

  .lane .count {
    font-size: 12px;
    color: var(--ink);
    min-width: 2ch;
  }

  .lane:hover .name,
  .lane[aria-expanded='true'] .name {
    color: var(--ink);
  }

  .note {
    position: absolute;
    transform: translate(-50%, calc(-100% - 5px));
    font-size: 11px;
    color: var(--ink-3);
    white-space: nowrap;
    pointer-events: none;
    background: var(--bg);
    padding: 0 4px;
  }

  .explainer {
    position: absolute;
    z-index: 3;
    width: 340px;
    transform: translate(-50%, 72px);
    padding: 16px 18px;
    background: var(--surface);
    border: 1px solid var(--rule);
    box-shadow: 6px 6px 0 var(--rule-soft);
    display: grid;
    gap: 10px;
    font-size: 13px;
    line-height: 1.45;
  }

  .explainer.left {
    transform: translate(calc(-100% - 16px), -50%);
  }

  .explainer.up {
    transform: translate(-50%, calc(-100% - 100px));
  }

  dl {
    margin: 0;
    display: grid;
    gap: 4px;
  }

  dd {
    margin: 0 0 6px;
    color: var(--ink-2);
  }

  .renderer {
    margin: 8px 0 0;
    font-size: 11px;
    text-align: right;
  }
</style>
