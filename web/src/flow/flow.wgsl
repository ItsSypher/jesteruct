// The flow canvas: hairline edges with travelling pulses, and pages as small squares with a short trail.
// Everything is in CSS pixels; colours arrive premultiplied-ready from the theme's CSS custom properties.

struct Uniforms {
  view: vec4f,   // width, height, device pixel ratio, time in seconds
  flags: vec4f,  // x: 1 when edges may animate
  palette: array<vec4f, 16>,  // 0-7 lanes, 8 particle, 9 ink, 10 edge
  heat: array<vec4f, 8>,      // one float per edge, packed four to a vector
}

@group(0) @binding(0) var<uniform> u: Uniforms;

const CORNERS = array<vec2f, 6>(
  vec2f(0.0, -1.0), vec2f(1.0, -1.0), vec2f(0.0, 1.0),
  vec2f(0.0, 1.0), vec2f(1.0, -1.0), vec2f(1.0, 1.0),
);

fn clip(p: vec2f) -> vec4f {
  return vec4f(p.x / u.view.x * 2.0 - 1.0, 1.0 - p.y / u.view.y * 2.0, 0.0, 1.0);
}

fn heat_of(i: u32) -> f32 {
  return u.heat[i / 4u][i % 4u];
}

// --- edges: one instance per line segment ---------------------------------------------------------------------

struct EdgeIn {
  @location(0) a: vec2f,
  @location(1) b: vec2f,
  @location(2) arc: vec2f,   // arc length at a and at b
  @location(3) info: vec2f,  // edge index, kind (0 main, 1 bypass, 2 native or quarantine)
}

struct EdgeOut {
  @builtin(position) pos: vec4f,
  @location(0) across: f32,
  @location(1) arc: f32,
  @location(2) @interpolate(flat) info: vec2f,
}

@vertex
fn edge_vs(@builtin(vertex_index) vi: u32, e: EdgeIn) -> EdgeOut {
  var corners = CORNERS;
  let c = corners[vi];
  let dir = normalize(e.b - e.a);
  let normal = vec2f(-dir.y, dir.x);
  let reach = 3.0;
  // overlap neighbouring segments by half a pixel so joints never show a seam
  let p = mix(e.a - dir * 0.5, e.b + dir * 0.5, c.x) + normal * c.y * reach;
  var out: EdgeOut;
  out.pos = clip(p);
  out.across = c.y * reach;
  out.arc = mix(e.arc.x, e.arc.y, c.x);
  out.info = e.info;
  return out;
}

@fragment
fn edge_fs(in: EdgeOut) -> @location(0) vec4f {
  let heat = heat_of(u32(in.info.x));
  let kind = in.info.y;
  let aa = 1.0 / u.view.z;
  let half_w = 0.5 + heat * 0.4;
  let cover = 1.0 - smoothstep(half_w - aa * 0.5, half_w + aa, abs(in.across));

  // bypass edges are dashed, and the arcs that skip the pipeline dotted
  var pattern = 1.0;
  if (kind > 1.5) {
    pattern = step(fract(in.arc / 5.0), 0.45);
  } else if (kind > 0.5) {
    pattern = step(fract(in.arc / 9.0), 0.6);
  }

  let base = mix(u.palette[10].rgb, u.palette[9].rgb, heat * 0.85);
  var alpha = cover * pattern;

  // pulses that run along an edge while pages travel it
  let phase = fract((in.arc - u.view.w * 70.0 * u.flags.x) / 22.0);
  let pulse = smoothstep(0.82, 0.97, phase) * (1.0 - smoothstep(0.97, 1.0, phase));
  let pulse_cover = 1.0 - smoothstep(1.0, 1.0 + aa, abs(in.across));
  let glow = pulse * pulse_cover * heat;

  let colour = mix(base, u.palette[9].rgb, glow);
  alpha = max(alpha, glow);
  return vec4f(colour * alpha, alpha);
}

// --- pages and node markers: one instance per square --------------------------------------------------------------

struct DotIn {
  @location(0) pos: vec2f,
  @location(1) trail: vec2f,  // from the head backwards, in px
  @location(2) size: f32,
  @location(3) colour: vec4f, // palette index a, palette index b, mix, alpha
  @location(4) ring: f32,
}

struct DotOut {
  @builtin(position) pos: vec4f,
  @location(0) local: vec2f,  // x along the trail (0 at the head), y across
  @location(1) @interpolate(flat) shape: vec4f,  // half size, trail length, ring, alpha
  @location(2) @interpolate(flat) rgb: vec3f,
}

@vertex
fn dot_vs(@builtin(vertex_index) vi: u32, d: DotIn) -> DotOut {
  var corners = CORNERS;
  let c = corners[vi];
  let len = length(d.trail);
  let axis = select(vec2f(1.0, 0.0), d.trail / max(len, 1e-4), len > 0.5);
  let normal = vec2f(-axis.y, axis.x);
  let hs = d.size * 0.5;
  let pad = select(1.5, 12.0, d.ring > 0.0);
  let x = mix(-hs - pad, len + hs + pad, c.x);
  let y = c.y * (hs + pad);
  var out: DotOut;
  out.pos = clip(d.pos + axis * x + normal * y);
  out.local = vec2f(x, y);
  out.shape = vec4f(hs, len, d.ring, d.colour.w);
  let a = u.palette[u32(d.colour.x)].rgb;
  let b = u.palette[u32(d.colour.y)].rgb;
  out.rgb = mix(a, b, d.colour.z);
  return out;
}

@fragment
fn dot_fs(in: DotOut) -> @location(0) vec4f {
  let hs = in.shape.x;
  let len = in.shape.y;
  let ring = in.shape.z;
  let aa = 0.9 / u.view.z;

  // head: a square with softly rounded corners
  let r = 1.2;
  let q = abs(in.local) - vec2f(hs - r);
  let d_head = length(max(q, vec2f(0.0))) + min(max(q.x, q.y), 0.0) - r;
  let head = 1.0 - smoothstep(-aa, aa, d_head);

  // trail: a thin line that fades out behind the head
  var trail = 0.0;
  if (len > 0.5 && in.local.x > 0.0) {
    let t = clamp(in.local.x / len, 0.0, 1.0);
    let thin = 1.0 - smoothstep(0.7 - aa, 0.7 + aa, abs(in.local.y));
    trail = thin * (1.0 - t) * (1.0 - t) * 0.6 * step(in.local.x, len);
  }

  // ring: a square outline that grows and fades when a page arrives
  var halo = 0.0;
  if (ring > 0.0) {
    let rr = hs + 2.5 + (1.0 - ring) * 7.0;
    let d_ring = abs(max(abs(in.local.x), abs(in.local.y)) - rr) - 0.5;
    halo = (1.0 - smoothstep(-aa, aa, d_ring)) * ring * 0.8;
  }

  let alpha = clamp(max(head, trail) + halo, 0.0, 1.0) * in.shape.w;
  return vec4f(in.rgb * alpha, alpha);
}
