// The flow on WebGPU: two instanced draws per frame (edge segments, then squares), one uniform buffer, no allocation.

import type { Palette } from '../lib/theme.svelte';
import shader from './flow.wgsl?raw';
import { EDGE_FLOATS, edgeSegments, type Frame, type Renderer } from './renderer';
import { FLOATS, MAX_TOKENS } from './traffic';

const UNIFORM_FLOATS = 4 + 4 + 16 * 4 + 8 * 4; // view, flags, palette, heat
const HEAT_OFFSET = 4 + 4 + 16 * 4;

export async function createWebGPU(canvas: HTMLCanvasElement, onLost: () => void): Promise<Renderer | null> {
  const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'low-power' });
  if (!adapter) return null;
  const device = await adapter.requestDevice();
  const context = canvas.getContext('webgpu');
  if (!context) return null;
  const format = navigator.gpu.getPreferredCanvasFormat();
  context.configure({ device, format, alphaMode: 'premultiplied' });
  let destroyed = false;
  device.lost.then((info) => {
    if (!destroyed) {
      console.warn('WebGPU device lost:', info.message);
      onLost();
    }
  });

  const module = device.createShaderModule({ code: shader });
  const uniforms = new Float32Array(UNIFORM_FLOATS);
  const uniformBuffer = device.createBuffer({ size: uniforms.byteLength, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
  let edgeBuffer: GPUBuffer | null = null;
  let edgeCount = 0;
  const dotBuffer = device.createBuffer({ size: MAX_TOKENS * FLOATS * 4, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });

  const layout = device.createBindGroupLayout({
    entries: [{ binding: 0, visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT, buffer: {} }],
  });
  const bindGroup = device.createBindGroup({ layout, entries: [{ binding: 0, resource: { buffer: uniformBuffer } }] });
  const blend: GPUBlendState = {
    color: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha' },
    alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha' },
  };
  const pipeline = (entry: string, attributes: GPUVertexAttribute[], stride: number) =>
    device.createRenderPipeline({
      layout: device.createPipelineLayout({ bindGroupLayouts: [layout] }),
      vertex: { module, entryPoint: `${entry}_vs`, buffers: [{ arrayStride: stride, stepMode: 'instance', attributes }] },
      fragment: { module, entryPoint: `${entry}_fs`, targets: [{ format, blend }] },
      primitive: { topology: 'triangle-list' },
    });
  const edges = pipeline(
    'edge',
    [
      { shaderLocation: 0, offset: 0, format: 'float32x2' },
      { shaderLocation: 1, offset: 8, format: 'float32x2' },
      { shaderLocation: 2, offset: 16, format: 'float32x2' },
      { shaderLocation: 3, offset: 24, format: 'float32x2' },
    ],
    EDGE_FLOATS * 4,
  );
  const dots = pipeline(
    'dot',
    [
      { shaderLocation: 0, offset: 0, format: 'float32x2' },
      { shaderLocation: 1, offset: 8, format: 'float32x2' },
      { shaderLocation: 2, offset: 16, format: 'float32' },
      { shaderLocation: 3, offset: 20, format: 'float32x4' },
      { shaderLocation: 4, offset: 36, format: 'float32' },
    ],
    FLOATS * 4,
  );

  const commands: GPUCommandBuffer[] = [];
  const pass: GPURenderPassDescriptor & { colorAttachments: GPURenderPassColorAttachment[] } = {
    colorAttachments: [{ view: undefined as unknown as GPUTextureView, clearValue: [0, 0, 0, 0], loadOp: 'clear', storeOp: 'store' }],
  };

  return {
    kind: 'WebGPU',
    resize(g, dpr) {
      canvas.width = Math.round(g.width * dpr);
      canvas.height = Math.round(g.height * dpr);
      uniforms[0] = g.width;
      uniforms[1] = g.height;
      uniforms[2] = dpr;
      const segments = edgeSegments(g);
      if (!edgeBuffer || edgeBuffer.size < segments.byteLength) {
        edgeBuffer?.destroy();
        edgeBuffer = device.createBuffer({ size: segments.byteLength, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST });
      }
      device.queue.writeBuffer(edgeBuffer, 0, segments);
      edgeCount = segments.length / EDGE_FLOATS;
    },
    setPalette(p: Palette) {
      uniforms.set(p.rgba, 8);
    },
    draw(f: Frame) {
      uniforms[3] = f.time;
      uniforms[4] = f.animate ? 1 : 0;
      uniforms.set(f.heat, HEAT_OFFSET);
      device.queue.writeBuffer(uniformBuffer, 0, uniforms);
      device.queue.writeBuffer(dotBuffer, 0, f.instances, 0, f.count * FLOATS);
      pass.colorAttachments[0]!.view = context.getCurrentTexture().createView();
      const encoder = device.createCommandEncoder();
      const rp = encoder.beginRenderPass(pass);
      rp.setBindGroup(0, bindGroup);
      if (edgeBuffer) {
        rp.setPipeline(edges);
        rp.setVertexBuffer(0, edgeBuffer);
        rp.draw(6, edgeCount);
      }
      if (f.count) {
        rp.setPipeline(dots);
        rp.setVertexBuffer(0, dotBuffer);
        rp.draw(6, f.count);
      }
      rp.end();
      commands[0] = encoder.finish();
      device.queue.submit(commands);
    },
    destroy() {
      destroyed = true;
      device.destroy();
    },
  };
}
