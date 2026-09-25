<script lang="ts">
  // A page, large. It grows out of its thumbnail and fits the window; the thumbnail shows at once and the
  // full-resolution view replaces it when it arrives. A trackpad pinch (or ctrl and the wheel, or Safari's gesture
  // events), a double click, or + and - zoom about the pointer; scrolling or dragging moves a zoomed page. A click
  // anywhere outside the page, or Escape, closes it.
  import { onMount } from 'svelte';

  let {
    thumb,
    full,
    alt,
    from,
    onclose,
  }: { thumb: string; full: string | null; alt: string; from: DOMRect | null; onclose: () => void } = $props();

  const MAX_SCALE = 8;
  const MARGIN = 0.9; // share of the window the fitted page may fill

  let stage: HTMLDivElement;
  let img: HTMLImageElement;
  let sharp = $state(false); // the full-resolution view has loaded
  const src = $derived(sharp && full ? full : thumb);
  let aspect = $state(0.75); // width / height, known once the thumbnail loads
  let view = $state({ w: 0, h: 0 }); // the window
  let scale = $state(1);
  let x = $state(0);
  let y = $state(0);
  let drag: { id: number; x: number; y: number; moved: boolean; outside: boolean } | null = null;
  let pinch = 1; // Safari's gesture scale at the previous gesturechange

  const fit = $derived.by(() => {
    const w = Math.min(view.w * MARGIN, view.h * MARGIN * aspect);
    return { w, h: w / aspect };
  });

  function clamp() {
    const maxX = Math.max(0, (fit.w * scale - view.w) / 2 + 24);
    const maxY = Math.max(0, (fit.h * scale - view.h) / 2 + 24);
    x = scale === 1 ? 0 : Math.min(maxX, Math.max(-maxX, x));
    y = scale === 1 ? 0 : Math.min(maxY, Math.max(-maxY, y));
  }

  /** Zoom by `factor`, keeping the page point under (cx, cy) in place (window coordinates). */
  function zoom(factor: number, cx = view.w / 2, cy = view.h / 2) {
    const next = Math.min(MAX_SCALE, Math.max(1, scale * factor));
    const px = cx - view.w / 2;
    const py = cy - view.h / 2;
    x = px - (px - x) * (next / scale);
    y = py - (py - y) * (next / scale);
    scale = next;
    clamp();
  }

  function onwheel(e: WheelEvent) {
    e.preventDefault();
    if (e.ctrlKey) zoom(Math.exp(-e.deltaY * 0.01), e.clientX, e.clientY); // trackpad pinch, or ctrl + wheel
    else if (scale > 1) {
      x -= e.deltaX;
      y -= e.deltaY;
      clamp();
    }
  }

  function ongesture(e: Event & { scale?: number; clientX?: number; clientY?: number }) {
    e.preventDefault(); // Safari: pinch arrives as gesture events rather than ctrl + wheel
    if (e.type === 'gesturestart') pinch = 1;
    else if (e.scale) {
      zoom(e.scale / pinch, e.clientX, e.clientY);
      pinch = e.scale;
    }
  }

  function onpointerdown(e: PointerEvent) {
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, outside: e.target === stage };
    if (scale > 1) stage.setPointerCapture(e.pointerId);
  }

  function onpointermove(e: PointerEvent) {
    if (!drag || drag.id !== e.pointerId) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (scale > 1 && drag.moved) {
      x += dx;
      y += dy;
      drag.x = e.clientX;
      drag.y = e.clientY;
      clamp();
    }
  }

  function onpointerup(e: PointerEvent) {
    const was = drag;
    drag = null;
    // a click that starts outside the page closes it; a drag does not, and neither does a click on the page
    if (was && was.id === e.pointerId && !was.moved && was.outside) onclose();
  }

  function ondblclick(e: MouseEvent) {
    if (scale > 1) {
      scale = 1;
      clamp();
    } else zoom(2.5, e.clientX, e.clientY);
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onclose();
    else if (e.key === '+' || e.key === '=') zoom(1.25);
    else if (e.key === '-') zoom(0.8);
    else if (e.key === '0') {
      scale = 1;
      clamp();
    } else return;
    e.preventDefault();
  }

  /** Mounts the overlay on the body, so no ancestor's layout or transform can clip it. */
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }

  onMount(() => {
    const measure = () => (view = { w: stage.clientWidth, h: stage.clientHeight });
    measure();
    window.addEventListener('resize', measure);
    // non-passive, so the page, not the document behind it, takes the pinch and the scroll
    stage.addEventListener('wheel', onwheel, { passive: false });
    for (const type of ['gesturestart', 'gesturechange']) stage.addEventListener(type, ongesture as EventListener);
    stage.focus();

    if (full) {
      const hi = new Image();
      hi.onload = () => (sharp = true);
      hi.src = full; // offline, or before the API can render it, the thumbnail simply stays
    }

    // grow out of the thumbnail
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (from && !reduced) {
      const to = img.getBoundingClientRect();
      const dx = from.left + from.width / 2 - (to.left + to.width / 2);
      const dy = from.top + from.height / 2 - (to.top + to.height / 2);
      const s = from.width / Math.max(1, to.width);
      img.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${s})` }, { transform: 'none' }], {
        duration: 260,
        easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      });
      stage.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200 });
    }
    return () => window.removeEventListener('resize', measure);
  });
</script>

<div
  class="stage"
  bind:this={stage}
  use:portal
  role="dialog"
  aria-modal="true"
  aria-label={alt}
  tabindex="-1"
  class:zoomed={scale > 1}
  {onpointerdown}
  {onpointermove}
  {onpointerup}
  {onkeydown}
>
  <img
    bind:this={img}
    {src}
    {alt}
    draggable="false"
    class:sharp
    style:width="{fit.w}px"
    style:height="{fit.h}px"
    style:transform="translate({x}px, {y}px) scale({scale})"
    onload={(e) => {
      const i = e.currentTarget as HTMLImageElement;
      if (i.naturalWidth && i.naturalHeight) aspect = i.naturalWidth / i.naturalHeight;
    }}
    {ondblclick}
  />
  <button class="close mono" onclick={onclose} aria-label="Close the page">Close</button>
  <p class="hint mono" aria-hidden="true">
    {Math.round(scale * 100)}% · {sharp ? 'full resolution' : 'thumbnail'} · pinch or ctrl + scroll to zoom · drag to move · Esc to close
  </p>
</div>

<style>
  .stage {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: grid;
    place-items: center;
    overflow: hidden;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(6px);
    cursor: zoom-out;
    touch-action: none;
    outline: none;
  }

  img {
    max-width: none;
    object-fit: contain;
    background: var(--surface);
    box-shadow: 0 12px 48px color-mix(in srgb, var(--ink) 22%, transparent);
    cursor: zoom-in;
    user-select: none;
    will-change: transform;
    image-rendering: auto;
  }

  .zoomed,
  .zoomed img {
    cursor: grab;
  }

  .close {
    position: absolute;
    top: calc(env(safe-area-inset-top, 0px) + 16px);
    right: 16px;
    padding: 8px 12px;
    border: 1px solid var(--rule-soft);
    background: var(--surface);
    color: var(--ink);
    font-size: 12px;
    cursor: pointer;
  }

  .close:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }

  .hint {
    position: absolute;
    bottom: calc(env(safe-area-inset-bottom, 0px) + 16px);
    left: 16px;
    right: 16px;
    margin: 0;
    text-align: center;
    font-size: 12px;
    color: var(--ink-3);
    pointer-events: none;
  }
</style>
