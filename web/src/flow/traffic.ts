// Pages as tokens moving through the flow graph. Events say where a page is in the pipeline; the traffic turns that
// into motion that stays readable: each token dwells a minimum time at the node it was sent to, leaves a node spaced
// from the tokens before it, catches up when it falls behind, and glides straight through when its answers came from
// the provider cache. No DOM here: the frame loop calls step() and write(), and views read the counters.

import { LANES, type Lane, type StudioEvent } from '../lib/types';
import { at, EDGES, edgeIndex, type Geometry, NODES, type NodeId, path, slot } from './graph';

export const FLOATS = 10; // per instance: x, y, trail x, trail y, size, colour a, colour b, mix, alpha, ring
export const NEUTRAL = 8; // palette index of a page whose lane is not known yet; 0-7 are the lanes
export const INK = 9;
export const MAX_TOKENS = 4096;

const SPEED = 520; // px per second along an edge
const MIN_TRAVEL = 0.28;
const MAX_TRAVEL = 1.1;
const DWELL: Partial<Record<NodeId, number>> = { intake: 0.12, evidence: 0.22, policy: 0.3 };
const STAGE_DWELL = 0.4;
const GLIDE_MS = 60; // a provider answer this fast came from the cache
const SPACING = 0.07; // seconds between departures from one node, shrinking as the node fills up
const LINGER = 1.3; // seconds a page stays visible in its lane
const FADE = 0.45;
const HEAT_DECAY = 1.4; // seconds for edge and node highlights to fade
const REMEMBERED = 20_000; // pages whose lane is remembered, so a replay is not counted twice

interface Hop {
  node: NodeId;
  lane?: Lane;
}

interface Token {
  key: string;
  job: string;
  node: NodeId; // where it is docked, or the node it last left
  edge: number; // -1 while at a node
  s: number; // arc length travelled on the edge
  duration: number;
  hops: Hop[]; // where events have sent it, in order
  docked: boolean; // holds a dock slot at `node`
  since: number; // seconds at the current node
  dwell: number;
  x: number;
  y: number;
  fromX: number; // where the current edge was joined, for a smooth exit from a dock slot
  fromY: number;
  dirX: number;
  dirY: number;
  lane: Lane | null;
  mix: number;
  alpha: number;
  ring: number;
  glide: boolean;
  landed: boolean;
  parent: Token | null; // set on the OCR twin, which runs beside its page and merges back at evidence
  twin: Token | null;
  fork: Hop[] | null; // hops for a twin that has not split off yet
}

const LANE_INDEX = Object.fromEntries(LANES.map((l, i) => [l, i])) as Record<Lane, number>;
const isLane = (n: NodeId): n is Lane => (LANES as readonly string[]).includes(n);
const smooth = (x: number) => x * x * (3 - 2 * x);

export class Traffic {
  readonly heat = new Float32Array(EDGES.length);
  readonly nodeHeat = new Float32Array(NODES.length);
  readonly waiting = new Int32Array(NODES.length);
  readonly landed = new Int32Array(LANES.length);
  /** Bumped whenever `waiting` or `landed` change, so views can skip identical updates. */
  version = 0;

  private tokens: Token[] = [];
  private byKey = new Map<string, Token>();
  private lanes = new Map<string, Lane>(); // where each page landed, so a replayed page is not counted twice
  private docks = new Map<NodeId, Token[]>(NODES.map((n) => [n, []]));
  private lastDeparture = new Float64Array(NODES.length);
  private clock = 0;
  private g: Geometry | null = null;
  private readonly p = { x: 0, y: 0, dx: 0, dy: 0 };

  constructor(private reduced = false) {}

  setGeometry(g: Geometry): void {
    this.g = g;
  }

  setReducedMotion(reduced: boolean): void {
    this.reduced = reduced;
  }

  get busy(): boolean {
    return this.tokens.length > 0 || warm(this.heat) || warm(this.nodeHeat);
  }

  get size(): number {
    return this.tokens.length;
  }

  /** Apply one event. A live event moves tokens; history (replayed on connect) only adds to the lane counts. */
  event(e: StudioEvent, live: boolean): void {
    if (e.type === 'doc' && live) this.nodeHeat[NODES.indexOf('intake')] = 1;
    if (e.type === 'job.retry') this.clearJob(e.job_id);
    if (e.type !== 'page.stage') return;
    const key = `${e.doc_sha}:${e.page}`;
    if (e.stage === 'policy' && e.state === 'done' && !live) return this.land(key, e.data.lane);
    if (!live) return;
    const t = this.token(key, e.job_id);
    switch (e.stage) {
      case 'probe':
        if (e.state === 'start') this.send(t, { node: 'probes' });
        break;
      case 'ocr':
        if (e.state === 'start') t.fork = [{ node: 'ocr' }];
        else if (e.state === 'done' || e.state === 'fail') (t.twin ? t.twin.hops : (t.fork ??= [])).push({ node: 'evidence' });
        break;
      case 'vision':
        if (e.state === 'start') this.send(t, { node: 'vision' });
        else this.send(t, { node: 'evidence' }); // done, fail or skip
        if (e.state === 'done' && (e.ms ?? Infinity) < GLIDE_MS) t.glide = true;
        break;
      case 'jev':
        if (e.state === 'start') this.send(t, { node: 'jev' });
        if (e.state === 'done' && (e.ms ?? Infinity) < GLIDE_MS) t.glide = true;
        break;
      case 'policy':
        if (e.state !== 'done') break;
        if (t.node === 'intake' && t.hops.length === 0 && (e.data.lane === 'L0' || e.data.lane === 'LQ')) {
          // decided at intake (native format or quarantine): straight along the arc to the lane
          t.lane = e.data.lane;
          t.mix = 1;
          this.send(t, { node: e.data.lane });
        } else {
          this.send(t, { node: 'policy', lane: e.data.lane });
          this.send(t, { node: e.data.lane });
        }
    }
  }

  /** Advance every token by dt seconds. */
  step(dt: number): void {
    const g = this.g;
    if (!g) return;
    this.clock += dt;
    const decay = Math.exp(-dt / HEAT_DECAY);
    for (let i = 0; i < this.heat.length; i++) this.heat[i]! *= decay;
    for (let i = 0; i < this.nodeHeat.length; i++) this.nodeHeat[i]! *= decay;
    const ease = this.reduced ? 1 : 1 - Math.exp(-dt * 14);

    for (let i = this.tokens.length - 1; i >= 0; i--) {
      const t = this.tokens[i]!;
      if (t.lane && t.mix < 1) t.mix = Math.min(1, t.mix + dt / 0.35);
      if (t.ring > 0) t.ring = Math.max(0, t.ring - dt / 0.8);

      if (t.edge >= 0) {
        const edge = g.edges[t.edge]!;
        t.s += (edge.length / t.duration) * dt;
        if (t.s >= edge.length) {
          this.arrive(t, EDGES[t.edge]!.to);
        } else {
          at(edge, t.s, this.p);
          const blend = smooth(Math.min(1, t.s / Math.min(40, edge.length * 0.3)));
          t.x = t.fromX + (this.p.x - t.fromX) * blend;
          t.y = t.fromY + (this.p.y - t.fromY) * blend;
          t.dirX = this.p.dx;
          t.dirY = this.p.dy;
        }
        continue;
      }

      t.since += dt;
      if (t.docked) {
        slot(g, t.node, this.docks.get(t.node)!.indexOf(t), this.p);
        t.x += (this.p.x - t.x) * ease;
        t.y += (this.p.y - t.y) * ease;
      }
      if (t.landed || (t.parent && t.node === 'evidence')) {
        if (t.since > (t.landed ? LINGER : 0.1)) t.alpha -= dt / FADE;
        if (t.alpha <= 0) this.remove(i);
        continue;
      }
      if (t.fork && t.docked && t.node !== 'intake') this.split(t);
      if (t.hops.length && t.since >= t.dwell) this.depart(t);
    }
  }

  /** Write the node markers and then every token as instances; returns the instance count. */
  write(out: Float32Array): number {
    const g = this.g;
    if (!g) return 0;
    let n = 0;
    for (let i = 0; i < NODES.length; i++) {
      const id = NODES[i]!;
      const c = g.nodes[id];
      const colour = isLane(id) ? LANE_INDEX[id] : INK;
      n = put(out, n, c.x, c.y, 0, 0, isLane(id) ? 10 : 8, colour, colour, 1, 1, this.nodeHeat[i]!);
    }
    for (const t of this.tokens) {
      if (n >= MAX_TOKENS) break;
      const moving = t.edge >= 0;
      const trail = moving ? Math.min(18, (g.edges[t.edge]!.length / t.duration) * 0.05) : 0;
      const b = t.lane ? LANE_INDEX[t.lane] : NEUTRAL;
      n = put(out, n, t.x, t.y, -t.dirX * trail, -t.dirY * trail, t.parent ? 5 : 7, NEUTRAL, b, t.mix, t.alpha, t.ring);
    }
    return n;
  }

  private token(key: string, job: string): Token {
    const existing = this.byKey.get(key);
    if (existing && !existing.landed) return existing;
    if (existing) this.remove(this.tokens.indexOf(existing));
    const c = this.g?.nodes.intake ?? { x: 0, y: 0 };
    const t = spawn(key, job, c.x, c.y);
    this.tokens.push(t);
    this.byKey.set(key, t);
    this.dock(t, 'intake', DWELL.intake!);
    return t;
  }

  private send(t: Token, hop: Hop): void {
    const last = t.hops.at(-1)?.node ?? (t.edge >= 0 ? EDGES[t.edge]!.to : t.node);
    if (last !== hop.node || hop.lane) t.hops.push(hop);
  }

  private split(t: Token): void {
    const twin = spawn(`${t.key}:ocr`, t.job, t.x, t.y);
    twin.parent = t;
    twin.hops = t.fork!;
    twin.glide = t.glide;
    t.fork = null;
    t.twin = twin;
    this.tokens.push(twin);
    this.dock(twin, t.node, 0);
  }

  private depart(t: Token): void {
    const g = this.g!;
    const node = NODES.indexOf(t.node);
    const dock = this.docks.get(t.node)!;
    if (t.docked && this.clock - this.lastDeparture[node]! < SPACING / (1 + dock.length / 10)) return;
    if (t.node === 'evidence' && (t.twin || t.fork)) return; // wait for the OCR twin to merge back
    const route = path(t.node, t.hops[0]!.node);
    if (route.length < 2) {
      const hop = t.hops.shift()!; // already there, or out of reach from here
      if (hop.lane) t.lane = hop.lane;
      return;
    }
    const e = edgeIndex(t.node, route[1]!);
    if (t.docked) this.undock(t);
    this.lastDeparture[node] = this.clock;
    const behind = t.hops.length;
    const pace = (t.glide ? 1.8 : 1) * (1 + 0.5 * Math.max(0, behind - 2));
    t.edge = e;
    t.s = 0;
    t.duration = this.reduced ? 1e-3 : Math.min(MAX_TRAVEL, Math.max(MIN_TRAVEL, g.edges[e]!.length / SPEED)) / pace;
    t.fromX = t.x;
    t.fromY = t.y;
    this.heat[e] = 1;
  }

  private arrive(t: Token, node: NodeId): void {
    const g = this.g!;
    t.edge = -1;
    t.node = node;
    t.since = 0;
    this.nodeHeat[NODES.indexOf(node)] = 1;
    const c = g.nodes[node];
    const hop = t.hops[0];
    if (hop?.node !== node) {
      // passing through on the way to where it was sent
      t.x = c.x;
      t.y = c.y;
      t.dwell = 0;
      return;
    }
    t.hops.shift();
    if (hop.lane) t.lane = hop.lane;
    if (isLane(node)) {
      t.x = c.x;
      t.y = c.y;
      t.landed = true;
      t.ring = 1;
      this.land(t.key, node);
      return;
    }
    const behind = t.hops.length >= 2 ? 0.3 : 1;
    this.dock(t, node, t.glide || t.parent ? 0 : (DWELL[node] ?? STAGE_DWELL) * behind);
    if (t.parent && node === 'evidence') {
      t.parent.twin = null;
      this.undock(t);
    }
  }

  private dock(t: Token, node: NodeId, dwell: number): void {
    t.node = node;
    t.docked = true;
    t.since = 0;
    t.dwell = dwell;
    this.docks.get(node)!.push(t);
    this.waiting[NODES.indexOf(node)]! += 1;
    this.version++;
  }

  private undock(t: Token): void {
    const dock = this.docks.get(t.node)!;
    const i = dock.indexOf(t);
    if (i >= 0) {
      dock.splice(i, 1);
      this.waiting[NODES.indexOf(t.node)]! -= 1;
      this.version++;
    }
    t.docked = false;
  }

  private land(key: string, lane: Lane): void {
    const before = this.lanes.get(key);
    if (before === lane) return;
    if (before) this.landed[LANE_INDEX[before]]! -= 1;
    this.landed[LANE_INDEX[lane]]! += 1;
    this.lanes.set(key, lane);
    if (this.lanes.size > REMEMBERED) this.lanes.delete(this.lanes.keys().next().value!);
    this.version++;
  }

  private remove(i: number): void {
    const t = this.tokens[i];
    if (!t) return;
    if (t.docked) this.undock(t);
    if (t.parent?.twin === t) t.parent.twin = null;
    if (this.byKey.get(t.key) === t) this.byKey.delete(t.key);
    this.tokens[i] = this.tokens[this.tokens.length - 1]!;
    this.tokens.pop();
  }

  private clearJob(job: string): void {
    for (let i = this.tokens.length - 1; i >= 0; i--) if (this.tokens[i]!.job === job) this.remove(i);
  }
}

function warm(heat: Float32Array): boolean {
  for (let i = 0; i < heat.length; i++) if (heat[i]! > 0.01) return true;
  return false;
}

function spawn(key: string, job: string, x: number, y: number): Token {
  return {
    key,
    job,
    node: 'intake',
    edge: -1,
    s: 0,
    duration: 1,
    hops: [],
    docked: false,
    since: 0,
    dwell: 0,
    x,
    y,
    fromX: x,
    fromY: y,
    dirX: 1,
    dirY: 0,
    lane: null,
    mix: 0,
    alpha: 1,
    ring: 0,
    glide: false,
    landed: false,
    parent: null,
    twin: null,
    fork: null,
  };
}

function put(
  out: Float32Array,
  n: number,
  x: number,
  y: number,
  tx: number,
  ty: number,
  size: number,
  a: number,
  b: number,
  mix: number,
  alpha: number,
  ring: number,
): number {
  const o = n * FLOATS;
  out[o] = x;
  out[o + 1] = y;
  out[o + 2] = tx;
  out[o + 3] = ty;
  out[o + 4] = size;
  out[o + 5] = a;
  out[o + 6] = b;
  out[o + 7] = mix;
  out[o + 8] = alpha;
  out[o + 9] = ring;
  return n + 1;
}
