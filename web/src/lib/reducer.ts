// The Studio's model of the system, folded from events. Pure and immutable: an event returns a new state that shares
// every document and page it did not touch, so views re-render only what changed.

import type {
  DocFacts,
  JobStatus,
  Lane,
  Layout,
  OcrFacts,
  PageRoute,
  Segment,
  Stage,
  StageState,
  StudioEvent,
  TextReading,
  VisionFacts,
} from './types';

export interface PageView {
  index: number;
  stages: Partial<Record<Stage, StageState>>;
  ms: Partial<Record<Stage, number>>;
  trusted: boolean | null;
  evidence: string | null;
  image: Record<string, number> | null;
  layout: Layout | null;
  text: TextReading | null;
  ocr: OcrFacts | null;
  vision: VisionFacts | null;
  model: string | null;
  answers: Record<string, number> | null;
  route: PageRoute | null;
  thumb: string | null;
}

export interface DocView extends DocFacts {
  sha: string;
  job: string;
  at: number;
  pages: PageView[];
  done: boolean;
  cached: boolean;
  cost: number | null;
  segments: Segment[];
}

export interface JobView {
  id: string;
  name: string;
  size: number | null;
  status: JobStatus;
  error: string | null;
  deliveries: number;
  docs: string[];
  at: number;
}

type Timed = 'probe' | 'ocr' | 'vision' | 'jev' | 'total';

export interface State {
  jobs: Record<string, JobView>;
  order: string[]; // job ids, newest first
  docs: Record<string, DocView>;
  timings: Record<Timed, number[]>; // recent durations in ms, for medians
}

const RECENT = 256;
export const MAX_JOBS = 500; // the oldest job and its documents are forgotten beyond this, so a long session stays small

export const initial = (): State => ({
  jobs: {},
  order: [],
  docs: {},
  timings: { probe: [], ocr: [], vision: [], jev: [], total: [] },
});

const blankPage = (index: number): PageView => ({
  index,
  stages: {},
  ms: {},
  trusted: null,
  evidence: null,
  image: null,
  layout: null,
  text: null,
  ocr: null,
  vision: null,
  model: null,
  answers: null,
  route: null,
  thumb: null,
});

const pagesFor = (count: number) => Array.from({ length: count }, (_, i) => blankPage(i));

function job(s: State, id: string, at: number, name = ''): [State, JobView] {
  const existing = s.jobs[id];
  if (existing) return [s, existing];
  const view: JobView = { id, name, size: null, status: 'queued', error: null, deliveries: 0, docs: [], at };
  const next = { ...s, jobs: { ...s.jobs, [id]: view }, order: [id, ...s.order] };
  return [next.order.length > MAX_JOBS ? forget(next, next.order.at(-1)!) : next, view];
}

function forget(s: State, id: string): State {
  const { [id]: gone, ...jobs } = s.jobs;
  const docs = { ...s.docs };
  for (const sha of gone?.docs ?? []) if (docs[sha]?.job === id) delete docs[sha];
  return { ...s, jobs, docs, order: s.order.filter((j) => j !== id) };
}

const putJob = (s: State, v: JobView): State => ({ ...s, jobs: { ...s.jobs, [v.id]: v } });
const putDoc = (s: State, v: DocView): State => ({ ...s, docs: { ...s.docs, [v.sha]: v } });

function record(s: State, key: Timed, ms: number | null | undefined): State {
  if (ms == null) return s;
  const recent = s.timings[key].length >= RECENT ? s.timings[key].slice(1) : s.timings[key].slice();
  recent.push(ms);
  return { ...s, timings: { ...s.timings, [key]: recent } };
}

function page(p: PageView, e: Extract<StudioEvent, { type: 'page.stage' }>): PageView {
  const next: PageView = { ...p, stages: { ...p.stages, [e.stage]: e.state } };
  if (e.state !== 'done') return next;
  if (e.ms != null) next.ms = { ...p.ms, [e.stage]: e.ms };
  switch (e.stage) {
    case 'probe':
      return {
        ...next,
        trusted: e.data.text_layer_trusted,
        evidence: e.data.evidence || null, // replays of stored manifests carry no evidence
        image: e.data.image,
        layout: e.data.layout,
        text: e.data.text ?? null,
      };
    case 'ocr':
      return { ...next, ocr: e.data };
    case 'vision':
      return { ...next, vision: e.data };
    case 'jev':
      return { ...next, model: e.data.model, answers: e.data.answers, evidence: e.data.evidence ?? p.evidence };
    case 'policy': {
      const { thumb, ...route } = e.data;
      return {
        ...next,
        route,
        answers: route.answers,
        evidence: route.evidence ?? p.evidence,
        vision: route.vision ?? p.vision,
        text: route.text ?? p.text,
        thumb: thumb ?? p.thumb,
      };
    }
  }
}

export function reduce(s: State, e: StudioEvent): State {
  switch (e.type) {
    case 'job.queued': {
      const [t, v] = job(s, e.job_id, e.at, e.name);
      return putJob(t, { ...v, name: e.name, size: e.size, status: 'queued' });
    }
    case 'job.started': {
      const [t, v] = job(s, e.job_id, e.at);
      return putJob(t, { ...v, status: 'running' });
    }
    case 'job.retry': {
      // The attempt failed and the job will run again: its pages start over.
      const [t, v] = job(s, e.job_id, e.at);
      let next = putJob(t, { ...v, status: 'queued', error: e.error, deliveries: e.deliveries });
      for (const sha of v.docs) {
        const d = next.docs[sha];
        if (d) next = putDoc(next, { ...d, pages: pagesFor(d.page_count), done: false, cost: null, segments: [] });
      }
      return next;
    }
    case 'job.done': {
      const [t, v] = job(s, e.job_id, e.at);
      return putJob(t, { ...v, status: e.status, error: e.error });
    }
    case 'doc': {
      const [t, v] = job(s, e.job_id, e.at, e.name);
      const next = v.docs.includes(e.doc_sha) ? t : putJob(t, { ...v, docs: [...v.docs, e.doc_sha] });
      return putDoc(next, {
        sha: e.doc_sha,
        job: e.job_id,
        at: e.at,
        name: e.name,
        kind: e.kind,
        mime: e.mime,
        page_count: e.page_count,
        parent_sha: e.parent_sha,
        quarantine: e.quarantine,
        pages: pagesFor(e.page_count),
        done: false,
        cached: false,
        cost: null,
        segments: [],
      });
    }
    case 'page.stage': {
      const d = s.docs[e.doc_sha];
      if (!d) return s; // a page of a document we never saw announced: nothing to attach it to
      const pages = d.pages.slice();
      while (pages.length <= e.page) pages.push(blankPage(pages.length));
      pages[e.page] = page(pages[e.page]!, e);
      let next = putDoc(s, { ...d, pages });
      if (e.state === 'done' && e.stage !== 'policy') next = record(next, e.stage, e.ms);
      if (e.state === 'done' && e.stage === 'policy') next = record(next, 'total', e.data.timings_ms.total);
      return next;
    }
    case 'doc.done': {
      const d = s.docs[e.doc_sha];
      if (!d) return s;
      return putDoc(s, { ...d, done: true, cached: e.cached, cost: e.cost_usd, segments: e.segments });
    }
  }
}

export function median(values: readonly number[]): number | null {
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

export function laneCounts(s: State): Record<Lane, number> {
  const counts = { L0: 0, L1: 0, L2: 0, L3: 0, L4: 0, L5: 0, LQ: 0, LH: 0 };
  for (const d of Object.values(s.docs)) for (const p of d.pages) if (p.route) counts[p.route.lane] += 1;
  return counts;
}
