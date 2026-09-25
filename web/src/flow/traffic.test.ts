import { describe, expect, it } from 'vitest';
import type { Lane, StudioEvent } from '../lib/types';
import { geometry, NODES } from './graph';
import { Traffic } from './traffic';

const g = geometry(1200, 600);
const L = (lane: Lane) => ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'LQ', 'LH'].indexOf(lane);
const waitingAt = (t: Traffic, node: (typeof NODES)[number]) => t.waiting[NODES.indexOf(node)]!;

type StageEvent = Extract<StudioEvent, { type: 'page.stage' }>;
const ev = (page: number, s: Partial<StageEvent>): StudioEvent =>
  ({ type: 'page.stage', job_id: 'j', at: 0, doc_sha: 'd', page, ...s }) as StudioEvent;
const policy = (page: number, lane: Lane) =>
  ev(page, { stage: 'policy', state: 'done', ms: null, data: { lane } as never });

function traffic(): Traffic {
  const t = new Traffic();
  t.setGeometry(g);
  return t;
}

/** Step the simulation in frames of 1/60 s, up to `seconds`, stopping early once `until` holds. */
function run(t: Traffic, seconds: number, until: () => boolean = () => false): number {
  let elapsed = 0;
  while (elapsed < seconds && !until()) {
    t.step(1 / 60);
    elapsed += 1 / 60;
  }
  return elapsed;
}

const bornDigital = (page: number): StudioEvent[] => [
  ev(page, { stage: 'probe', state: 'start' }),
  ev(page, { stage: 'probe', state: 'done', ms: 200, data: { text_layer_trusted: true } as never }),
  ev(page, { stage: 'ocr', state: 'skip' }),
  ev(page, { stage: 'vision', state: 'skip' }),
  ev(page, { stage: 'jev', state: 'start' }),
  ev(page, { stage: 'jev', state: 'done', ms: 300, data: { answers: {}, model: null } }),
  policy(page, 'L1'),
];

describe('Traffic', () => {
  it('holds a burst to a minimum dwell per node, then lands every page', () => {
    const t = traffic();
    for (const e of bornDigital(0)) t.event(e, true);
    // intake, probes, evidence, jev, policy: a page whose events all arrived at once still pauses at each step
    const landed = run(t, 20, () => t.landed[L('L1')] === 1);
    expect(t.landed[L('L1')]).toBe(1);
    expect(landed).toBeGreaterThan(0.12 + 0.4 + 0.22 + 0.4 + 0.3);
    expect(landed).toBeLessThan(8);
  });

  it('keeps a page waiting at vision until its vision check is done', () => {
    const t = traffic();
    for (const e of [
      ev(0, { stage: 'probe', state: 'start' }),
      ev(0, { stage: 'ocr', state: 'start' }),
      ev(0, { stage: 'vision', state: 'start' }),
      ev(0, { stage: 'ocr', state: 'done', ms: 600, data: null }),
    ])
      t.event(e, true);
    run(t, 10);
    expect(waitingAt(t, 'vision')).toBe(1);
    expect(t.size).toBe(1); // the OCR twin went ahead and merged back at evidence
    t.event(ev(0, { stage: 'vision', state: 'done', ms: 9000, data: {} as never }), true);
    t.event(ev(0, { stage: 'jev', state: 'start' }), true);
    t.event(policy(0, 'L4'), true);
    run(t, 20, () => t.landed[L('L4')] === 1);
    expect(t.landed[L('L4')]).toBe(1);
    expect(waitingAt(t, 'vision')).toBe(0);
  });

  it('spaces departures when many pages arrive together', () => {
    const t = traffic();
    for (let p = 0; p < 30; p++) t.event(ev(p, { stage: 'probe', state: 'start' }), true);
    run(t, 0.3);
    expect(waitingAt(t, 'intake')).toBeGreaterThan(0); // not all released in the same instant
    run(t, 5);
    expect(waitingAt(t, 'probes')).toBe(30);
  });

  it('sends pages decided at intake straight along their arc', () => {
    const t = traffic();
    t.event(policy(0, 'L0'), true);
    t.event(policy(1, 'LQ'), true);
    run(t, 10, () => t.landed[L('L0')] === 1 && t.landed[L('LQ')] === 1);
    expect(waitingAt(t, 'probes')).toBe(0);
    expect(t.landed[L('L0')]).toBe(1);
    expect(t.landed[L('LQ')]).toBe(1);
  });

  it('counts history without animating it, and each page once', () => {
    const t = traffic();
    for (const e of bornDigital(0)) t.event(e, false);
    expect(t.size).toBe(0);
    expect(t.landed[L('L1')]).toBe(1);
    for (const e of bornDigital(0)) t.event(e, true); // the same page replayed
    run(t, 20, () => t.size === 0);
    expect(t.landed[L('L1')]).toBe(1);
  });

  it('drops the tokens of a job that is retried', () => {
    const t = traffic();
    t.event(ev(0, { stage: 'probe', state: 'start' }), true);
    t.event({ type: 'job.retry', job_id: 'j', at: 0, error: null, deliveries: 2 }, true);
    expect(t.size).toBe(0);
  });
});
