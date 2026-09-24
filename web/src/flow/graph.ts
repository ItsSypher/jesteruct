// The pipeline as a graph: which nodes exist, how pages can move between them, and the geometry for a given size.

import { LANES, type Lane } from '../lib/types';

export const STEPS = ['intake', 'probes', 'ocr', 'vision', 'evidence', 'jev', 'policy'] as const;
export type Step = (typeof STEPS)[number];
export type NodeId = Step | Lane;
export const NODES: readonly NodeId[] = [...STEPS, ...LANES];

export type EdgeKind = 'main' | 'bypass' | 'native' | 'quarantine';
export interface EdgeDef {
  from: NodeId;
  to: NodeId;
  kind: EdgeKind;
}

export const EDGES: readonly EdgeDef[] = [
  { from: 'intake', to: 'probes', kind: 'main' },
  { from: 'probes', to: 'ocr', kind: 'main' },
  { from: 'probes', to: 'vision', kind: 'main' },
  { from: 'probes', to: 'evidence', kind: 'bypass' },
  { from: 'ocr', to: 'evidence', kind: 'main' },
  { from: 'vision', to: 'evidence', kind: 'main' },
  { from: 'evidence', to: 'jev', kind: 'main' },
  { from: 'jev', to: 'policy', kind: 'main' },
  ...(['L1', 'L2', 'L3', 'L4', 'L5', 'LH', 'LQ'] as const).map((to) => ({ from: 'policy' as const, to, kind: 'main' as const })),
  { from: 'intake', to: 'L0', kind: 'native' },
  { from: 'intake', to: 'LQ', kind: 'quarantine' },
];

/** The shortest chain of nodes from one node to another, both included; empty when there is no way. */
export function path(from: NodeId, to: NodeId): NodeId[] {
  const previous = new Map<NodeId, NodeId>();
  const queue: NodeId[] = [from];
  for (let i = 0; i < queue.length; i++) {
    const at = queue[i]!;
    if (at === to) break;
    for (const e of EDGES) {
      if (e.from === at && e.to !== from && !previous.has(e.to)) {
        previous.set(e.to, at);
        queue.push(e.to);
      }
    }
  }
  if (from !== to && !previous.has(to)) return [];
  const chain: NodeId[] = [to];
  while (chain[0] !== from) chain.unshift(previous.get(chain[0]!)!);
  return chain;
}

export const edgeIndex = (from: NodeId, to: NodeId) => EDGES.findIndex((e) => e.from === from && e.to === to);

// --- geometry ------------------------------------------------------------------------------------------------------

export const PORT = 7; // edges meet a node this far from its centre
export const SLOT = 9; // dock slot pitch in px
export const DOCK_COLUMNS = 8;
export const DOCK_ROWS = 3;
const RADIUS = 14; // corner radius of the routed edges
const CORNER_STEPS = 8;

export interface EdgeGeometry {
  points: Float32Array; // x and y interleaved
  lengths: Float32Array; // arc length at each point
  length: number;
  mid: { x: number; y: number };
}

export interface Geometry {
  width: number;
  height: number;
  nodes: Record<NodeId, { x: number; y: number }>;
  edges: EdgeGeometry[];
}

const COLUMN: Record<Step, number> = {
  intake: 0.055,
  probes: 0.2,
  ocr: 0.345,
  vision: 0.345,
  evidence: 0.49,
  jev: 0.605,
  policy: 0.72,
};
const ROW: Record<NodeId, number> = {
  intake: 0.47,
  probes: 0.47,
  ocr: 0.24,
  vision: 0.73,
  evidence: 0.47,
  jev: 0.47,
  policy: 0.47,
  L0: 0.1,
  L1: 0.215,
  L2: 0.33,
  L3: 0.445,
  L4: 0.56,
  L5: 0.675,
  LH: 0.8,
  LQ: 0.905,
};
const LANE_COLUMN = 0.82;

type P = { x: number; y: number };

export function geometry(width: number, height: number): Geometry {
  const nodes = {} as Geometry['nodes'];
  for (const id of NODES) {
    const column = (STEPS as readonly string[]).includes(id) ? COLUMN[id as Step] : LANE_COLUMN;
    nodes[id] = { x: Math.round(column * width), y: Math.round(ROW[id] * height) };
  }
  const out = (n: NodeId): P => ({ x: nodes[n].x + PORT, y: nodes[n].y });
  const into = (n: NodeId): P => ({ x: nodes[n].x - PORT, y: nodes[n].y });
  const between = (a: NodeId, b: NodeId) => Math.round((nodes[a].x + nodes[b].x) / 2);
  // The arcs that skip the pipeline leave intake through the gap before the probes' label, and come down (or up)
  // to their lane just left of it.
  const gap = Math.round(nodes.intake.x + (nodes.probes.x - nodes.intake.x) * 0.5);
  const drop = nodes.L0.x - 30;

  const edges = EDGES.map((e): EdgeGeometry => {
    const a = out(e.from);
    const b = into(e.to);
    if (e.kind === 'native' || e.kind === 'quarantine') {
      const rail = Math.round(e.kind === 'native' ? height * 0.03 : height * 0.975);
      return route([a, { x: gap, y: a.y }, { x: gap, y: rail }, { x: drop, y: rail }, { x: drop, y: b.y }, b]);
    }
    if (a.y === b.y) return route([a, b]);
    // one vertical run halfway between the two nodes, so parallel edges share a trunk
    const x = between(e.from, e.to);
    return route([a, { x, y: a.y }, { x, y: b.y }, b]);
  });
  return { width, height, nodes, edges };
}

/** An orthogonal polyline with rounded corners, as points with their arc lengths. */
function route(corners: P[]): EdgeGeometry {
  const xy: number[] = [corners[0]!.x, corners[0]!.y];
  for (let i = 1; i < corners.length - 1; i++) {
    const a = corners[i - 1]!;
    const b = corners[i]!;
    const c = corners[i + 1]!;
    const la = Math.hypot(b.x - a.x, b.y - a.y);
    const lc = Math.hypot(c.x - b.x, c.y - b.y);
    const r = Math.min(RADIUS, la / 2, lc / 2);
    const s = { x: b.x - ((b.x - a.x) / (la || 1)) * r, y: b.y - ((b.y - a.y) / (la || 1)) * r };
    const t = { x: b.x + ((c.x - b.x) / (lc || 1)) * r, y: b.y + ((c.y - b.y) / (lc || 1)) * r };
    for (let k = 0; k <= CORNER_STEPS; k++) {
      const u = k / CORNER_STEPS;
      const v = 1 - u;
      xy.push(v * v * s.x + 2 * v * u * b.x + u * u * t.x, v * v * s.y + 2 * v * u * b.y + u * u * t.y);
    }
  }
  xy.push(corners.at(-1)!.x, corners.at(-1)!.y);

  const points = new Float32Array(xy);
  const lengths = new Float32Array(points.length / 2);
  for (let i = 1; i < lengths.length; i++) {
    lengths[i] = lengths[i - 1]! + Math.hypot(points[2 * i]! - points[2 * i - 2]!, points[2 * i + 1]! - points[2 * i - 1]!);
  }
  const edge: EdgeGeometry = { points, lengths, length: lengths.at(-1)!, mid: { x: 0, y: 0 } };
  at(edge, edge.length / 2, edge.mid);
  return edge;
}

/** The point at arc length `s` along an edge, written into `out` along with the unit direction there. */
export function at(edge: EdgeGeometry, s: number, out: { x: number; y: number; dx?: number; dy?: number }): void {
  const { points, lengths } = edge;
  let lo = 0;
  let hi = lengths.length - 1;
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if (lengths[m]! < s) lo = m;
    else hi = m;
  }
  const span = lengths[hi]! - lengths[lo]! || 1;
  const f = Math.min(1, Math.max(0, (s - lengths[lo]!) / span));
  const x0 = points[2 * lo]!;
  const y0 = points[2 * lo + 1]!;
  const x1 = points[2 * hi]!;
  const y1 = points[2 * hi + 1]!;
  out.x = x0 + (x1 - x0) * f;
  out.y = y0 + (y1 - y0) * f;
  const d = Math.hypot(x1 - x0, y1 - y0) || 1;
  out.dx = (x1 - x0) / d;
  out.dy = (y1 - y0) / d;
}

/** Where the n-th page waiting at a node sits: a small grid under the node, or on the node for a lane. */
export function slot(g: Geometry, node: NodeId, n: number, out: { x: number; y: number }): void {
  const c = g.nodes[node];
  if ((LANES as readonly string[]).includes(node)) {
    out.x = c.x;
    out.y = c.y;
    return;
  }
  const i = Math.min(n, DOCK_COLUMNS * DOCK_ROWS - 1);
  out.x = c.x + ((i % DOCK_COLUMNS) - (DOCK_COLUMNS - 1) / 2) * SLOT;
  out.y = c.y + 17 + Math.floor(i / DOCK_COLUMNS) * SLOT;
}

/** The number of line segments across all edges, for sizing vertex buffers. */
export const segmentCount = (g: Geometry) => g.edges.reduce((n, e) => n + e.lengths.length - 1, 0);
