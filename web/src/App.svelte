<script lang="ts">
  import Flow from './flow/Flow.svelte';
  import { runDemo, studio } from './lib/studio.svelte';
  import Results from './results/Results.svelte';
  import Drop, { pick } from './ui/Drop.svelte';
  import Header from './ui/Header.svelte';
  import Samples from './ui/Samples.svelte';

  const info = $derived(studio.info);
</script>

<Header />
<Drop />

<main id="top">
  <section class="hero">
    <h1>Every page, routed to the lane that can read it.</h1>
    <div class="intro">
      <p>
        jesteruct looks at each page of a document, measures it cheaply, puts the measurements into words, and lets
        TypeSafe Jev answer narrow yes or no questions. A fixed rule table turns the answers into a lane, and doubtful
        pages go to review. Watch it happen below.
      </p>
      <div class="actions">
        <button class="pill solid" onclick={runDemo} disabled={studio.demoing || studio.mode === 'connecting'}>
          {studio.mode === 'offline' ? 'Replay demo' : 'Run demo'}
        </button>
        <button class="pill" onclick={pick} disabled={studio.mode !== 'live'}>Add files</button>
        <span class="mono muted">or drop them anywhere</span>
      </div>
      {#if studio.mode === 'offline'}
        <p class="offline mono">
          The API is not reachable, so this is a recorded run replayed in the browser. Start the worker and the API to
          route your own files.
        </p>
      {/if}
    </div>
  </section>

  <section id="flow" aria-label="Flow">
    <div class="section-head"><h2 class="label">/ Flow</h2></div>
    <Flow />
  </section>

  <section id="results" aria-label="Results">
    <div class="section-head"><h2 class="label">/ Results</h2></div>
    <Results />
  </section>

  <section id="samples" aria-label="Samples">
    <div class="section-head"><h2 class="label">/ Samples</h2></div>
    <p class="lede">
      The demo set: one or more documents for every lane, from the labelled evaluation set and a few files of our own.
      Each card says what it shows and the lane it is labelled with; the flow shows where it actually goes.
    </p>
    <Samples />
  </section>
</main>

<footer class="mono">
  {#if info}
    <span>router {info.version}</span>
    <span>evidence {info.evidence}</span>
    <span>policy {info.policy}</span>
    <span>
      {info.calibration ? `calibration ${info.calibration.version}, review below ${info.calibration.threshold}` : 'no calibration'}
    </span>
    <span>Jev {info.jev_model}</span>
    <span>vision {info.vision_model}</span>
    <span>route key {info.route_key}</span>
  {/if}
</footer>

<style>
  main {
    padding: 0 var(--gutter);
    display: grid;
    gap: 72px;
  }

  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
    gap: 48px;
    align-items: end;
    padding: 72px 0 8px;
  }

  h1 {
    font-size: clamp(40px, 5.2vw, 76px);
    letter-spacing: -0.055em;
    line-height: 1.02;
    max-width: 14ch;
  }

  .intro {
    display: grid;
    gap: 24px;
  }

  .intro p {
    font-size: 17px;
    color: var(--ink-2);
    max-width: 56ch;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .actions .mono {
    font-size: 12px;
  }

  .intro .offline {
    font-size: 12px;
    padding: 10px 12px;
    border: 1px dashed var(--ink-3);
    color: var(--ink-2);
  }

  section {
    display: grid;
    gap: 20px;
    scroll-margin-top: 72px;
  }

  .lede {
    max-width: 70ch;
    color: var(--ink-2);
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 22px;
    margin-top: 96px;
    padding: 20px var(--gutter) 28px;
    border-top: 1px solid var(--rule-soft);
    font-size: 11px;
    color: var(--ink-3);
  }

  @media (max-width: 900px) {
    .hero {
      grid-template-columns: 1fr;
      padding-top: 40px;
    }
  }
</style>
