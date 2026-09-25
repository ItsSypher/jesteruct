// The Studio's controller: where events come from (the live stream, replays of cached documents, or the offline
// fixture), how they reach the flow (at once) and the views (batched), and the actions a viewer can take.

import { Traffic } from '../flow/traffic';
import * as api from './api';
import { initial, reduce, type State } from './reducer';
import { manifestEvents, Player } from './replay';
import type { Info, StudioEvent } from './types';

const LIVE_WINDOW_MS = 5000; // an event older than this (history replayed on connect) is counted, not animated
const FLUSH_MS = 80; // views take events in batches, so bursts cost one render
const DEMO_STAGGER_MS = 450;

export interface Upload {
  id: number;
  name: string;
  size: number;
  progress: number;
  job: string | null;
  error: string | null;
}

export interface Sample {
  file: string;
  title: string;
  lanes: string[];
  shows: string;
  source: string;
}

interface Fixture {
  info: Info;
  events: StudioEvent[];
}

export const studio = $state({
  mode: 'connecting' as 'connecting' | 'live' | 'offline',
  link: 'connecting' as api.Link,
  info: null as Info | null,
  uploads: [] as Upload[],
  samples: [] as Sample[],
  selected: null as string | null, // doc sha
  page: null as number | null,
  demoing: false,
});

let model = $state.raw<State>(initial());
export const current = () => model;

export const traffic = new Traffic(matchMedia('(prefers-reduced-motion: reduce)').matches);
const wakers = new Set<() => void>();
export const onActivity = (wake: () => void) => (wakers.add(wake), () => wakers.delete(wake));

let skew = 0;
let pending: StudioEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | undefined;
let fixture: Fixture | null = null;
let uploads = 0;
let follow: string | null = null; // the viewer's latest upload: its first document is selected when it appears
const player = new Player((e) => ingest(e, true)); // replays happen now, whatever the server clock says

/** Hand an event to the flow at once and to the views in the next batch. Stream events are live unless they are
 * history replayed on connect. */
function ingest(e: StudioEvent, live = Date.now() + skew - e.at < LIVE_WINDOW_MS): boolean {
  traffic.event(e, live);
  for (const wake of wakers) wake();
  pending.push(e);
  flushTimer ??= setTimeout(flush, FLUSH_MS);
  return live;
}

function fromStream(e: StudioEvent): void {
  const live = ingest(e);
  if (e.type === 'doc.done' && e.cached) void replayDoc(e.doc_sha, e.job_id, live);
}

function flush(): void {
  let m = model;
  for (const e of pending) m = reduce(m, e);
  pending = [];
  flushTimer = undefined;
  model = m;
  const followed = follow ? m.jobs[follow]?.docs[0] : undefined;
  if (followed) {
    select(followed);
    follow = null;
  } else if (!studio.selected || !m.docs[studio.selected]) studio.selected = m.order.flatMap((j) => m.jobs[j]!.docs)[0] ?? null;
}

/** A stored manifest sends no page events: rebuild them from its timings, animated when it is happening now. */
async function replayDoc(sha: string, job: string, live: boolean): Promise<void> {
  const drafts = manifestEvents(await api.manifest(sha), job, false);
  if (live) player.play(drafts);
  else for (const d of drafts) ingest(d, false);
}

/** A job that was already done when submitted sends no events at all: replay it from its manifests, one document
 * after another as the worker routed them. */
async function replayJob(id: string, name: string, size: number): Promise<void> {
  const index = await api.job(id);
  const manifests = await Promise.all(index.documents.map((d) => api.manifest(d.doc_sha)));
  const drafts: StudioEvent[] = [
    { type: 'job.queued', job_id: id, at: 0, name, size },
    { type: 'job.started', job_id: id, at: 0 },
  ];
  let t = 0;
  for (const m of manifests) {
    for (const d of manifestEvents(m, id, true)) drafts.push({ ...d, at: d.at + t });
    t = drafts.at(-1)!.at + 60;
  }
  drafts.push({ type: 'job.done', job_id: id, at: t, status: index.status === 'failed' ? 'failed' : 'done', error: index.error });
  player.play(drafts);
}

export async function start(): Promise<void> {
  void loadSamples();
  const reached = await api.reach();
  if (!reached) return offline();
  studio.info = reached.info;
  skew = reached.skew;
  studio.mode = 'live';
  api.subscribe(fromStream, (l) => (studio.link = l));
}

async function offline(): Promise<void> {
  studio.mode = 'offline';
  fixture ??= (await import('../fixtures/demo-events.json')).default as unknown as Fixture;
  studio.info = fixture.info;
  replayFixture();
}

function replayFixture(): void {
  const events = fixture!.events;
  const first = events[0]?.at ?? 0;
  player.play(events.map((e) => ({ ...e, at: e.at - first })));
}

async function loadSamples(): Promise<void> {
  try {
    studio.samples = await (await fetch('/samples/samples.json')).json();
  } catch {
    studio.samples = [];
  }
}

export function add(files: Iterable<File>): void {
  if (studio.mode !== 'live') return;
  for (const file of files) void send(file, file.name, true);
}

async function send(file: Blob, name: string, followIt = false): Promise<void> {
  studio.uploads.push({ id: ++uploads, name, size: file.size, progress: 0, job: null, error: null });
  const u = studio.uploads.at(-1)!; // the reactive proxy, not the object pushed
  try {
    const r = await api.submit(file, name, (f) => (u.progress = f));
    u.progress = 1;
    u.job = r.job_id;
    if (followIt) follow = r.job_id;
    if (r.status === 'done') await replayJob(r.job_id, name, file.size);
  } catch (e) {
    u.error = e instanceof Error ? e.message : String(e);
  }
}

export async function runSample(s: Sample, delay = 0, followIt = true): Promise<void> {
  if (studio.mode !== 'live') return;
  const blob = await (await fetch(`/samples/${s.file}`)).blob();
  if (delay) await new Promise((r) => setTimeout(r, delay));
  await send(blob, s.file, followIt);
}

export async function runDemo(): Promise<void> {
  if (studio.demoing) return;
  studio.demoing = true;
  try {
    if (studio.mode === 'offline') replayFixture();
    else await Promise.all(studio.samples.map((s, i) => runSample(s, i * DEMO_STAGGER_MS, false)));
  } finally {
    studio.demoing = false;
  }
}

export function select(sha: string | null, page: number | null = null): void {
  studio.selected = sha;
  studio.page = page;
}
