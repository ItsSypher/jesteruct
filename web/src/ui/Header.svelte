<script lang="ts">
  import { studio } from '../lib/studio.svelte';
  import { theme, toggleTheme } from '../lib/theme.svelte';

  const status = $derived(
    studio.mode === 'offline'
      ? 'Offline replay'
      : studio.mode === 'connecting' || studio.link === 'connecting'
        ? 'Connecting'
        : studio.link === 'live'
          ? 'Live'
          : 'Reconnecting',
  );
</script>

<header>
  <a class="brand" href="#top">
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">
      <rect x="0" y="0" width="7" height="7" />
      <rect x="9" y="0" width="7" height="7" opacity="0.35" />
      <rect x="0" y="9" width="7" height="7" opacity="0.35" />
      <rect x="9" y="9" width="7" height="7" />
    </svg>
    <span class="word">jesteruct</span>
    <span class="label muted">/ Studio</span>
  </a>
  <nav class="label">
    <a href="#flow">Flow</a>
    <a href="#results">Results</a>
    <a href="#samples">Samples</a>
  </nav>
  <span class="status label" data-mode={studio.mode} data-link={studio.link}><i></i>{status}</span>
  <button class="theme label" onclick={toggleTheme} aria-label="{theme.mode === 'dark' ? 'Dark mode, switch to light' : 'Light mode, switch to dark'}">
    <span class="dial" aria-hidden="true"></span>{theme.mode === 'dark' ? 'Dark' : 'Light'}
  </button>
</header>

<style>
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 32px;
    height: 60px;
    padding: 0 var(--gutter);
    background: color-mix(in srgb, var(--bg) 90%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--rule-soft);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    color: inherit;
    text-decoration: none;
  }

  .brand svg {
    fill: var(--ink);
  }

  .word {
    font-size: 19px;
    font-weight: 500;
    letter-spacing: -0.05em;
  }

  nav {
    display: flex;
    gap: 24px;
  }

  nav a {
    color: inherit;
    text-decoration: none;
  }

  nav a:hover {
    text-decoration: underline;
    text-underline-offset: 4px;
  }

  .status {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--ink-2);
  }

  .status i {
    width: 7px;
    height: 7px;
    background: var(--ink-3);
  }

  .status[data-mode='live'][data-link='live'] i {
    background: var(--ink);
    animation: blink 1.6s steps(2, jump-none) infinite;
  }

  .status[data-mode='offline'] i {
    background: none;
    box-shadow: inset 0 0 0 1px var(--ink-2);
  }

  @keyframes blink {
    50% {
      opacity: 0.2;
    }
  }

  .theme {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    height: 32px;
    padding: 0 14px;
    border: 1px solid var(--rule-soft);
    border-radius: 999px;
    background: none;
    cursor: pointer;
  }

  .theme:hover {
    border-color: var(--ink);
  }

  .dial {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 1px solid var(--ink);
    background: linear-gradient(90deg, var(--ink) 50%, transparent 50%);
  }

  @media (max-width: 760px) {
    nav {
      display: none;
    }

    header {
      gap: 16px;
    }
  }
</style>
