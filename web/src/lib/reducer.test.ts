import { describe, expect, it } from 'vitest';
import { initial, MAX_JOBS, reduce, type State } from './reducer';
import { manifestEvents } from './replay';
import type { Manifest, PageRoute, StudioEvent } from './types';

const JOB = 'job-1';
const SHA = 'a'.repeat(64);

const route: PageRoute = {
  index: 0,
  lane: 'LH',
  candidate_lane: 'L4',
  path_p: 0.62,
  confidence: 0.71,
  answers: { text_layer_trustworthy: 0.04, camera_or_fax: 0.8 },
  modifiers: ['table'],
  degradation: 1.2,
  continuation: null,
  vision: {
    capture: 'photo',
    legibility: 'fair',
    handwriting: 'none',
    script: 'latin',
    content: { table: true },
    defects: { photocopy: false },
  },
  reasons: ['no trusted text (0.96)', 'low confidence (calibrated 0.71 < 0.90)'],
  evidence: 'Input: an image. Quick OCR found 12 lines.',
  thumb_key: `thumbs/${SHA}/0`,
  timings_ms: { probe: 300, ocr: 600, vision: 9000, jev: 350, total: 9800 },
};

const at = (n: number) => ({ job_id: JOB, at: n });
const stage = (s: Partial<Extract<StudioEvent, { type: 'page.stage' }>>) =>
  ({ type: 'page.stage', doc_sha: SHA, page: 0, ...at(1), ...s }) as StudioEvent;

const live: StudioEvent[] = [
  { type: 'job.queued', name: 'photo.jpg', size: 1000, ...at(0) },
  { type: 'job.started', ...at(0) },
  { type: 'doc', doc_sha: SHA, name: 'photo.jpg', kind: 'image', mime: 'image/jpeg', page_count: 1, parent_sha: null, quarantine: null, ...at(0) },
  stage({ stage: 'probe', state: 'start' }),
  stage({
    stage: 'probe',
    state: 'done',
    ms: 300,
    data: { text_layer_trusted: false, evidence: 'Input: an image. Page image: sharp.', image: {}, layout: null, pdf: null },
  }),
  stage({ stage: 'ocr', state: 'start' }),
  stage({ stage: 'vision', state: 'start' }),
  stage({ stage: 'ocr', state: 'done', ms: 600, data: { lines: 12, confidence: 0.9, backend: 'apple' } }),
  stage({ stage: 'vision', state: 'done', ms: 9000, data: route.vision! }),
  stage({ stage: 'jev', state: 'start' }),
  stage({ stage: 'jev', state: 'done', ms: 350, data: { answers: route.answers, model: 'jev', evidence: 'Input: an image. Quick OCR found 12 lines.' } }),
  stage({ stage: 'policy', state: 'done', ms: null, data: { ...route, thumb: `/v1/thumbs/${SHA}/0` } }),
  { type: 'doc.done', doc_sha: SHA, route_key: 'k', lanes: { LH: 1 }, segments: [{ start: 0, end: 0, lane: 'LH', modifiers: [] }], cost_usd: 0.003, cached: false, ...at(2) },
  { type: 'job.done', status: 'done', error: null, ...at(2) },
];

const fold = (events: StudioEvent[], s: State = initial()) => events.reduce(reduce, s);

describe('reduce', () => {
  it('folds a routed page from its stage events', () => {
    const s = fold(live);
    const doc = s.docs[SHA]!;
    const page = doc.pages[0]!;
    expect(s.jobs[JOB]).toMatchObject({ name: 'photo.jpg', status: 'done', docs: [SHA] });
    expect(doc).toMatchObject({ done: true, cost: 0.003, cached: false });
    expect(page.stages).toEqual({ probe: 'done', ocr: 'done', vision: 'done', jev: 'done', policy: 'done' });
    expect(page.route?.lane).toBe('LH');
    expect(page.route?.candidate_lane).toBe('L4');
    expect(page.evidence).toBe('Input: an image. Quick OCR found 12 lines.'); // Jev's evidence replaces the probe's
    expect(page.thumb).toBe(`/v1/thumbs/${SHA}/0`);
    expect(s.timings.vision).toEqual([9000]);
    expect(s.timings.total).toEqual([9800]);
  });

  it('starts a job over when it is retried', () => {
    const s = fold([...live.slice(0, 8), { type: 'job.retry', error: 'provider unavailable', deliveries: 2, ...at(3) }]);
    expect(s.jobs[JOB]).toMatchObject({ status: 'queued', deliveries: 2 });
    expect(s.docs[SHA]!.pages[0]!.stages).toEqual({});
  });

  it('shares what an event did not touch', () => {
    const other = 'b'.repeat(64);
    const before = fold([...live.slice(0, 3), { ...(live[2] as Extract<StudioEvent, { type: 'doc' }>), doc_sha: other }]);
    const after = reduce(before, stage({ stage: 'probe', state: 'start' }));
    expect(after.docs[other]).toBe(before.docs[other]);
    expect(after.docs[SHA]).not.toBe(before.docs[SHA]);
  });

  it('forgets the oldest job and its documents past the limit', () => {
    let s = fold(live);
    for (let i = 0; i < MAX_JOBS; i++) s = reduce(s, { type: 'job.queued', job_id: `j${i}`, at: 3, name: `f${i}`, size: 1 });
    expect(s.order).toHaveLength(MAX_JOBS);
    expect(s.jobs[JOB]).toBeUndefined();
    expect(s.docs[SHA]).toBeUndefined();
  });

  it('ignores pages of a document it never saw', () => {
    const s = initial();
    expect(reduce(s, stage({ stage: 'probe', state: 'start' }))).toBe(s);
  });

  it('rebuilds the same route from a stored manifest', () => {
    const manifest: Manifest = {
      doc: { sha256: SHA, name: 'photo.jpg', kind: 'image', mime: 'image/jpeg', size: 1000, page_count: 1, parent_sha: null, quarantine: null },
      route_key: 'k',
      pages: [route],
      segments: [{ start: 0, end: 0, lane: 'LH', modifiers: [] }],
      cost_usd: 0.003,
    };
    const drafts = manifestEvents(manifest, JOB, true);
    expect(drafts.map((d) => d.at)).toEqual([...drafts.map((d) => d.at)].sort((a, b) => a - b));
    const page = fold(drafts).docs[SHA]!.pages[0]!;
    expect(page.route).toEqual(route);
    expect(page.stages).toEqual({ probe: 'done', ocr: 'done', vision: 'done', jev: 'done', policy: 'done' });
    expect(page.evidence).toBe(route.evidence);
    const older = fold(manifestEvents({ ...manifest, pages: [{ ...route, evidence: undefined }] }, JOB, true));
    expect(older.docs[SHA]!.pages[0]!.evidence).toBeNull(); // stored before manifests recorded evidence
  });
});
