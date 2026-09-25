// The flow on Canvas 2D, for browsers without WebGPU: the same frame, drawn with cached paths and no allocation.

import type { Palette } from '../lib/theme.svelte';
import { EDGES, type Geometry } from './graph';
import type { Frame, Renderer } from './renderer';
import { FLOATS, INK } from './traffic';

const EDGE_COLOUR = 10;
const DASH: Record<string, number[]> = { main: [], bypass: [5.4, 3.6], native: [2.25, 2.75], quarantine: [2.25, 2.75] };
const PULSE = [3, 19];

export function createCanvas2D(canvas: HTMLCanvasElement): Renderer {
  const ctx = canvas.getContext('2d')!;
  let paths: Path2D[] = [];
  let colours: string[] = [];
  let dpr = 1;
  let width = 0;
  let height = 0;

  return {
    kind: 'Canvas 2D',
    resize(g: Geometry, ratio: number) {
      dpr = ratio;
      width = g.width;
      height = g.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      paths = g.edges.map((e) => {
        const p = new Path2D();
        p.moveTo(e.points[0]!, e.points[1]!);
        for (let i = 1; i < e.lengths.length; i++) p.lineTo(e.points[2 * i]!, e.points[2 * i + 1]!);
        return p;
      });
    },
    setPalette(p: Palette) {
      colours = p.css;
    },
    draw(f: Frame) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.lineWidth = 1;
      for (let i = 0; i < paths.length; i++) {
        const heat = f.heat[i]!;
        ctx.setLineDash(DASH[EDGES[i]!.kind]!);
        ctx.lineDashOffset = 0;
        ctx.globalAlpha = 1;
        ctx.strokeStyle = colours[EDGE_COLOUR]!;
        ctx.stroke(paths[i]!);
        if (heat < 0.01) continue;
        ctx.strokeStyle = colours[INK]!;
        ctx.globalAlpha = heat * 0.7;
        ctx.stroke(paths[i]!);
        ctx.setLineDash(PULSE);
        ctx.lineDashOffset = f.animate ? -f.time * 70 : 0;
        ctx.lineWidth = 2;
        ctx.globalAlpha = heat;
        ctx.stroke(paths[i]!);
        ctx.lineWidth = 1;
      }
      ctx.setLineDash(DASH.main!);

      const d = f.instances;
      for (let n = 0; n < f.count; n++) {
        const o = n * FLOATS;
        const x = d[o]!;
        const y = d[o + 1]!;
        const size = d[o + 4]!;
        const mix = d[o + 7]!;
        const alpha = d[o + 8]!;
        const ring = d[o + 9]!;
        const a = colours[d[o + 5]!]!;
        const b = colours[d[o + 6]!]!;
        const half = size / 2;
        // trail: two segments, fading away from the head
        if (d[o + 2] || d[o + 3]) {
          ctx.strokeStyle = mix > 0.5 ? b : a;
          ctx.lineWidth = 1.4;
          ctx.globalAlpha = alpha * 0.45;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + d[o + 2]! * 0.5, y + d[o + 3]! * 0.5);
          ctx.stroke();
          ctx.globalAlpha = alpha * 0.15;
          ctx.beginPath();
          ctx.moveTo(x + d[o + 2]! * 0.5, y + d[o + 3]! * 0.5);
          ctx.lineTo(x + d[o + 2]!, y + d[o + 3]!);
          ctx.stroke();
          ctx.lineWidth = 1;
        }
        ctx.globalAlpha = alpha * (1 - mix);
        ctx.fillStyle = a;
        if (mix < 1) ctx.fillRect(x - half, y - half, size, size);
        ctx.globalAlpha = alpha * mix;
        ctx.fillStyle = b;
        if (mix > 0) ctx.fillRect(x - half, y - half, size, size);
        if (ring > 0) {
          const r = half + 2.5 + (1 - ring) * 7;
          ctx.globalAlpha = alpha * ring * 0.8;
          ctx.strokeStyle = b;
          ctx.strokeRect(x - r, y - r, r * 2, r * 2);
        }
      }
      ctx.globalAlpha = 1;
    },
    destroy() {
      paths = [];
    },
  };
}
