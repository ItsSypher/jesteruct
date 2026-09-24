<script lang="ts" module>
  import { add } from '../lib/studio.svelte';

  /** Open the file picker. Intake decides every type by its bytes, so nothing is filtered here. */
  export function pick(): void {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = () => input.files && add(input.files);
    input.click();
  }
</script>

<script lang="ts">
  import { studio } from '../lib/studio.svelte';

  let depth = $state(0); // dragenter and dragleave fire for every child element crossed
  const carriesFiles = (e: DragEvent) => e.dataTransfer?.types.includes('Files') ?? false;
</script>

<svelte:window
  ondragenter={(e) => carriesFiles(e) && (e.preventDefault(), depth++)}
  ondragover={(e) => carriesFiles(e) && e.preventDefault()}
  ondragleave={(e) => carriesFiles(e) && (depth = Math.max(0, depth - 1))}
  ondrop={(e) => {
    if (!carriesFiles(e)) return;
    e.preventDefault();
    depth = 0;
    if (e.dataTransfer?.files.length) add(e.dataTransfer.files);
  }}
/>

{#if depth > 0}
  <div class="overlay" aria-hidden="true">
    <div class="target">
      {#if studio.mode === 'live'}
        <p class="label">/ Drop to route</p>
        <p class="title">Every page goes through the flow.</p>
        <p class="mono muted">PDF · PNG JPEG TIFF GIF WebP BMP HEIC · DOC XLS PPT DOCX XLSX PPTX ODT ODS ODP RTF · ZIP · EML · text</p>
      {:else}
        <p class="label">/ Offline</p>
        <p class="title">The API is not reachable, so files cannot be routed.</p>
        <p class="mono muted">Start the worker and the API, then reload.</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: grid;
    place-items: center;
    padding: var(--gutter);
    background: color-mix(in srgb, var(--bg) 82%, transparent);
    backdrop-filter: blur(3px);
    pointer-events: none;
  }

  .target {
    width: 100%;
    height: 100%;
    display: grid;
    place-content: center;
    gap: 14px;
    text-align: center;
    border: 1px dashed var(--ink);
  }

  .title {
    font-size: clamp(24px, 3vw, 40px);
    font-weight: 500;
    letter-spacing: -0.045em;
  }

  .mono {
    font-size: 12px;
  }
</style>
