<script lang="ts">
  import * as api from '../lib/api';
  import { LANE_NAMES } from '../lib/copy';
  import { fixed, ms, sentences, words } from '../lib/format';
  import type { DocView, PageView } from '../lib/reducer';
  import type { Info } from '../lib/types';
  import LaneChip from '../ui/LaneChip.svelte';
  import Answers from './Answers.svelte';
  import Lightbox from './Lightbox.svelte';
  import { thumbFor } from './thumbs';
  import Timeline from './Timeline.svelte';

  let {
    doc,
    page,
    info,
    live,
    onclose,
  }: { doc: DocView; page: PageView; info: Info | null; live: boolean; onclose: () => void } = $props();

  const OFFLINE_SCALE = ['clean', 'mild', 'heavy', 'severe']; // used only when the API has not described the scale
  const route = $derived(page.route);
  // the scale Jev answers on, as "Clean: flat, sharp" and so on: the words before the colon name each step
  const scale = $derived(
    info?.questions.degradation?.criteria?.map((c) => c.split(':')[0]!.trim().toLowerCase()) ?? OFFLINE_SCALE,
  );
  const src = $derived(thumbFor(doc, page, live));
  const threshold = $derived(info?.calibration?.threshold ?? null);
  const review = $derived(route?.lane === 'LH' && route.candidate_lane !== 'LH');
  const evidence = $derived(page.evidence ? sentences(page.evidence) : []);
  const flags = (m: Record<string, boolean>) =>
    Object.entries(m).map(([k, v]) => ({ name: words(k), on: v }));

  // the page, large: it grows out of the thumbnail, and focus returns to the thumbnail when it closes
  let expanded = $state<{ from: DOMRect | null; opener: HTMLElement } | null>(null);
  function open(e: MouseEvent) {
    const opener = e.currentTarget as HTMLElement;
    expanded = { from: opener.querySelector('img')?.getBoundingClientRect() ?? null, opener };
  }
  function close() {
    const opener = expanded?.opener;
    expanded = null;
    opener?.focus();
  }
</script>

<article class="detail" aria-label="Page {page.index + 1} of {doc.name}">
  <header>
    <p class="label">/ Page {page.index + 1} of {Math.max(doc.pages.length, 1)}</p>
    <button class="close mono" onclick={onclose} aria-label="Close the page details">Close</button>
  </header>
  <p class="doc">{doc.name}</p>

  <div class="top">
    <div class="thumb">
      {#if src}
        <button class="expand" onclick={open} aria-label="View page {page.index + 1} large">
          <img {src} alt="Page {page.index + 1} of {doc.name}" />
        </button>
      {:else}<span class="mono muted">no image</span>{/if}
    </div>
    {#if expanded && src}
      <Lightbox
        thumb={src}
        full={live ? api.pageView(doc.sha, page.index) : null}
        alt="Page {page.index + 1} of {doc.name}"
        from={expanded.from}
        onclose={close}
      />
    {/if}
    <div class="verdict">
      {#if route}
        <LaneChip lane={route.lane} named large />
        {#if review}
          <p class="note">Sent to review. The rule table chose <LaneChip lane={route.candidate_lane} named />.</p>
        {/if}
        <div class="confidence">
          <span class="big mono">{fixed(route.confidence)}</span>
          <span class="muted">calibrated probability that {review ? 'the candidate' : 'this'} lane is right</span>
          {#if route.confidence != null}
            <span class="meter" aria-hidden="true">
              <i style:width="{route.confidence * 100}%"></i>
              {#if threshold != null}<b style:left="{threshold * 100}%" title="review below {threshold}"></b>{/if}
            </span>
          {/if}
          <span class="mono muted small">rule path {fixed(route.path_p)}{threshold != null ? ` · review below ${fixed(threshold)}` : ''}</span>
        </div>
      {:else}
        <p class="mono muted">Routing: {Object.entries(page.stages).map(([s, v]) => `${s} ${v}`).join(', ') || 'waiting'}</p>
      {/if}
    </div>
  </div>

  {#if route}
    <section>
      <p class="label muted">Reasons</p>
      <ul class="reasons mono">
        {#each route.reasons as r (r)}<li>{r}</li>{/each}
      </ul>
    </section>

    <section class="facts">
      <div>
        <p class="label muted">Modifiers</p>
        <p class="mods">
          {#each route.modifiers as m (m)}<span class="tag mono">{words(m)}</span>{:else}<span class="muted">none</span>{/each}
        </p>
      </div>
      {#if route.degradation != null}
        <div>
          <p class="label muted">Degradation</p>
          <span class="scale" style:--steps={scale.length} aria-label="Degradation {fixed(route.degradation)} of {scale.length - 1}">
            {#each scale as d, i (d)}
              <span class:on={Math.round(route.degradation) === i}>{d}</span>
            {/each}
            <b style:left="{(Math.min(scale.length - 1, route.degradation) / (scale.length - 1)) * 100}%"></b>
          </span>
          <p class="mono muted small">{fixed(route.degradation)} on a scale of 0 to {scale.length - 1}</p>
        </div>
      {/if}
      {#if route.continuation != null}
        <div>
          <p class="label muted">Continues previous page</p>
          <p class="mono">{fixed(route.continuation)}</p>
        </div>
      {/if}
    </section>
  {/if}

  {#if page.text}
    {@const t = page.text}
    <section>
      <p class="label muted">Text layer</p>
      <dl class="vision">
        <dt>language</dt><dd>{t.name || (t.readability == null ? 'too little text to tell' : 'several')}</dd>
        <dt>reads as language</dt><dd>{t.readability == null ? '-' : fixed(t.readability)}</dd>
        {#if t.unreadable}<dt>why not</dt><dd>{t.unreadable}</dd>{/if}
      </dl>
    </section>
  {/if}

  {#if page.vision}
    {@const v = page.vision}
    <section>
      <p class="label muted">Vision check</p>
      <dl class="vision">
        <dt>capture</dt><dd>{v.capture}</dd>
        <dt>legibility</dt><dd>{v.legibility}</dd>
        <dt>handwriting</dt><dd>{v.handwriting}</dd>
        <dt>script</dt><dd>{v.script}</dd>
      </dl>
      {#each [{ name: 'defects', set: v.defects }, { name: 'content', set: v.content }] as group (group.name)}
        <div class="flags">
          <span class="mono muted group">{group.name}</span>
          <span class="set">
            {#each flags(group.set) as f (f.name)}
              <span class="flag mono" class:on={f.on}><i></i>{f.name}</span>
            {/each}
          </span>
        </div>
      {/each}
    </section>
  {/if}

  {#if page.answers}
    <section>
      <p class="label muted">Jev's answers {#if page.model}<span class="model">{page.model}</span>{/if}</p>
      <Answers answers={page.answers} {info} />
    </section>
  {/if}

  {#if evidence.length}
    <section>
      <p class="label muted">Evidence</p>
      <ul class="evidence">
        {#each evidence as s, i (i)}
          <li>{#if s.topic}<span class="mono topic">{s.topic}</span>{/if}{s.text}</li>
        {/each}
      </ul>
    </section>
  {:else if route && page.stages.probe}
    <section>
      <p class="label muted">Evidence</p>
      <p class="muted">This manifest was stored before evidence was recorded.</p>
    </section>
  {/if}

  {#if page.ocr}
    <section>
      <p class="label muted">OCR check of the text layer</p>
      <p class="mono small">{page.ocr.lines} lines, confidence {fixed(page.ocr.confidence)}, {page.ocr.backend}</p>
    </section>
  {/if}

  {#if route}
    <section>
      <p class="label muted">Timeline <span class="model">{ms(route.timings_ms.total)}</span></p>
      <Timeline timings={route.timings_ms} />
    </section>
  {/if}

  {#if route}<p class="mono muted small">{LANE_NAMES[route.lane]} · {doc.kind} · {doc.mime}</p>{/if}
</article>

<style>
  .detail {
    display: grid;
    gap: 22px;
    align-content: start;
    padding: 18px 20px 24px;
    background: var(--surface);
    border: 1px solid var(--rule);
    box-shadow: 6px 6px 0 var(--rule-soft);
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .close {
    border: 1px solid var(--rule-soft);
    background: none;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    cursor: pointer;
  }

  .close:hover {
    border-color: var(--ink);
  }

  .doc {
    margin-top: -14px;
    font-size: 13px;
    color: var(--ink-2);
    overflow-wrap: anywhere;
  }

  .top {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 18px;
    align-items: start;
  }

  .thumb {
    aspect-ratio: 3 / 4;
    background: var(--surface-2);
    display: grid;
    place-items: center;
    border: 1px solid var(--rule-soft);
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .expand {
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    border: 0;
    background: none;
    cursor: zoom-in;
  }

  .expand:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }

  .verdict {
    display: grid;
    gap: 14px;
    align-content: start;
  }

  .note {
    font-size: 13px;
    color: var(--ink-2);
  }

  .confidence {
    display: grid;
    gap: 6px;
    font-size: 12px;
  }

  .big {
    font-size: 34px;
    line-height: 1;
    letter-spacing: -0.03em;
  }

  .meter {
    position: relative;
    height: 6px;
    background: var(--surface-2);
    border-radius: 2px;
  }

  .meter i {
    display: block;
    height: 100%;
    background: var(--ink);
    border-radius: 2px;
  }

  .meter b,
  .scale b {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 2px;
    margin-left: -1px;
    background: var(--lane-LH);
  }

  .small {
    font-size: 11px;
  }

  section {
    display: grid;
    gap: 8px;
  }

  .model {
    text-transform: none;
    letter-spacing: 0;
    margin-left: 6px;
    color: var(--ink-3);
    font-weight: 400;
  }

  .reasons {
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 12px;
    display: grid;
    gap: 3px;
    overflow-wrap: anywhere;
  }

  .reasons li::before {
    content: '- ';
    color: var(--ink-3);
  }

  .facts {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px;
  }

  .facts > div {
    display: grid;
    gap: 8px;
    align-content: start;
  }

  .mods {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }

  .tag {
    font-size: 11px;
    padding: 3px 7px;
    border: 1px solid var(--rule-soft);
    border-radius: 999px;
  }

  .scale {
    position: relative;
    display: grid;
    grid-template-columns: repeat(var(--steps), 1fr);
    gap: 2px;
    font: 10px var(--font-mono);
    text-transform: uppercase;
  }

  .scale span {
    padding: 5px 0 4px;
    text-align: center;
    background: var(--surface-2);
    color: var(--ink-3);
  }

  .scale span.on {
    background: var(--ink);
    color: var(--bg);
  }

  .scale b {
    background: var(--ink-3);
    top: auto;
    bottom: -6px;
    height: 4px;
  }

  .vision {
    display: grid;
    grid-template-columns: 90px 1fr;
    gap: 4px 12px;
    margin: 0;
    font-size: 13px;
  }

  .vision dt {
    font: 12px var(--font-mono);
    color: var(--ink-3);
  }

  .vision dd {
    margin: 0;
  }

  .flags {
    display: grid;
    grid-template-columns: 90px 1fr;
    gap: 12px;
    margin-top: 4px;
  }

  .group {
    font-size: 12px;
  }

  .set {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
  }

  .flag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: var(--ink-3);
  }

  .flag i {
    width: 8px;
    height: 8px;
    border: 1px solid var(--ink-3);
    border-radius: 1.5px;
  }

  .flag.on {
    color: var(--ink);
  }

  .flag.on i {
    background: var(--ink);
    border-color: var(--ink);
  }

  .evidence {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 8px;
    font-size: 13px;
    color: var(--ink-2);
  }

  .topic {
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--ink-3);
    margin-bottom: 1px;
  }
</style>
