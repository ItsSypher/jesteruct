// What a flow renderer does, and the pick between WebGPU and the Canvas 2D fallback.

import type { Palette } from '../lib/theme.svelte';
import { EDGES, type Geometry, segmentCount } from './graph';

export interface Frame {
  instances: Float32Array; // Traffic.write() output
  count: number;
  heat: Float32Array; // per edge, 0-1
  time: number; // seconds
  animate: boolean; // false under reduced motion: edges light up but do not run
}

export interface Renderer {
  readonly kind: 'WebGPU' | 'Canvas 2D';
  resize(g: Geometry, dpr: number): void;
  setPalette(p: Palette): void;
  draw(f: Frame): void;
  destroy(): void;
}

const KIND = { main: 0, bypass: 1, native: 2, quarantine: 2 } as const;
export const EDGE_FLOATS = 8;

/** One instance per edge segment: from, to, arc length at both ends, edge index and kind. */
export function edgeSegments(g: Geometry): Float32Array {
  const out = new Float32Array(segmentCount(g) * EDGE_FLOATS);
  let o = 0;
  g.edges.forEach((e, index) => {
    for (let i = 0; i < e.lengths.length - 1; i++) {
      out.set(
        [
          e.points[2 * i]!,
          e.points[2 * i + 1]!,
          e.points[2 * i + 2]!,
          e.points[2 * i + 3]!,
          e.lengths[i]!,
          e.lengths[i + 1]!,
          index,
          KIND[EDGES[index]!.kind],
        ],
        o,
      );
      o += EDGE_FLOATS;
    }
  });
  return out;
}

/** WebGPU when the browser has a working adapter, otherwise Canvas 2D. */
export async function createRenderer(canvas: HTMLCanvasElement, onLost: () => void, forceFallback = false): Promise<Renderer> {
  if (!forceFallback && 'gpu' in navigator) {
    try {
      const { createWebGPU } = await import('./webgpu');
      const gpu = await createWebGPU(canvas, onLost);
      if (gpu) return gpu;
    } catch (e) {
      console.warn('WebGPU unavailable, drawing with Canvas 2D', e);
    }
  }
  const { createCanvas2D } = await import('./canvas2d');
  return createCanvas2D(canvas);
}
