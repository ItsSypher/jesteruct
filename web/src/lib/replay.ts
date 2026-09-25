// Replays: a stored manifest turned back into the page events it would have produced, and a player that emits
// timed events through the same path as the live stream (for cached documents and the offline fixture).

import { thumb } from './api';
import type { Manifest, PageRoute, StudioEvent } from './types';

const PAGE_STAGGER_MS = 140;

type Draft = StudioEvent; // `at` holds an offset in ms from the start of the replay

/** The page events for a manifest, from each page's recorded stage timings. Older manifests carry no evidence. */
export function manifestEvents(m: Manifest, job: string, announce: boolean): Draft[] {
  const sha = m.doc.sha256;
  const out: Draft[] = [];
  if (announce) {
    const { name, kind, mime, page_count, parent_sha, quarantine } = m.doc;
    out.push({ type: 'doc', job_id: job, at: 0, doc_sha: sha, name, kind, mime, page_count, parent_sha, quarantine });
  }
  let end = 0;
  for (const route of m.pages) {
    const events = pageEvents(route, sha, job, route.index * PAGE_STAGGER_MS);
    out.push(...events);
    end = Math.max(end, events.at(-1)?.at ?? 0);
  }
  const lanes: Partial<Record<PageRoute['lane'], number>> = {};
  for (const p of m.pages) lanes[p.lane] = (lanes[p.lane] ?? 0) + 1;
  out.push({
    type: 'doc.done',
    job_id: job,
    at: end + 40,
    doc_sha: sha,
    route_key: m.route_key,
    lanes,
    segments: m.segments,
    cost_usd: m.cost_usd,
    cached: true,
  });
  return out.sort((a, b) => a.at - b.at);
}

function pageEvents(route: PageRoute, sha: string, job: string, start: number): Draft[] {
  const t = route.timings_ms;
  const base = { type: 'page.stage' as const, job_id: job, doc_sha: sha, page: route.index };
  const policy: Draft = {
    ...base,
    at: start + (t.total ?? 0),
    stage: 'policy',
    state: 'done',
    ms: null,
    data: { ...route, thumb: route.thumb_key ? thumb(sha, route.index) : null },
  };
  if (t.probe == null) return [policy]; // decided without probing: native formats and quarantine
  const read = t.ocr != null || t.vision != null;
  const probed = start + t.probe;
  const out: Draft[] = [
    { ...base, at: start, stage: 'probe', state: 'start' },
    {
      ...base,
      at: probed,
      stage: 'probe',
      state: 'done',
      ms: t.probe,
      data: { text_layer_trusted: !read, evidence: '', image: {}, layout: null, pdf: null },
    },
  ];
  if (!read) {
    out.push({ ...base, at: probed, stage: 'ocr', state: 'skip' }, { ...base, at: probed, stage: 'vision', state: 'skip' });
  } else {
    out.push({ ...base, at: probed, stage: 'ocr', state: 'start' }, { ...base, at: probed, stage: 'vision', state: 'start' });
    if (t.ocr != null) out.push({ ...base, at: probed + t.ocr, stage: 'ocr', state: 'done', ms: t.ocr, data: null });
    else out.push({ ...base, at: probed, stage: 'ocr', state: 'fail' });
    if (t.vision != null && route.vision)
      out.push({ ...base, at: probed + t.vision, stage: 'vision', state: 'done', ms: t.vision, data: route.vision });
    else out.push({ ...base, at: probed, stage: 'vision', state: 'fail' });
  }
  if (t.jev != null) {
    const read_ms = Math.max(t.ocr ?? 0, t.vision ?? 0);
    const asked = Math.max(probed + read_ms, start + (t.total ?? 0) - t.jev);
    out.push(
      { ...base, at: asked, stage: 'jev', state: 'start' },
      { ...base, at: asked + t.jev, stage: 'jev', state: 'done', ms: t.jev, data: { answers: route.answers, model: null, evidence: route.evidence ?? undefined } },
    );
    policy.at = Math.max(policy.at, asked + t.jev);
  }
  out.push(policy);
  return out;
}

/** Emits events at their offsets from when they were queued. One timer, however many replays overlap. */
export class Player {
  private queue: StudioEvent[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(private emit: (e: StudioEvent) => void) {}

  play(drafts: Draft[], delay = 0): void {
    const base = Date.now() + delay;
    this.queue.push(...drafts.map((d) => ({ ...d, at: base + d.at })));
    this.queue.sort((a, b) => a.at - b.at);
    this.schedule();
  }

  get playing(): boolean {
    return this.queue.length > 0;
  }

  stop(): void {
    clearTimeout(this.timer);
    this.queue = [];
  }

  private schedule(): void {
    clearTimeout(this.timer);
    const next = this.queue[0];
    if (!next) return;
    this.timer = setTimeout(() => this.tick(), Math.max(0, next.at - Date.now()));
  }

  private tick(): void {
    const now = Date.now();
    let n = 0;
    while (n < this.queue.length && this.queue[n]!.at <= now) n++;
    for (const e of this.queue.splice(0, n)) this.emit(e);
    this.schedule();
  }
}
