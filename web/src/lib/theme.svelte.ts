// Light or dark: follows the system until the viewer picks one, then remembers the pick.

import { LANES } from './types';

type Mode = 'light' | 'dark';
const KEY = 'jst-theme';
const system = matchMedia('(prefers-color-scheme: dark)');

function stored(): Mode | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

export const theme = $state({ mode: stored() ?? (system.matches ? 'dark' : 'light') });

system.addEventListener('change', (e) => {
  if (!stored()) theme.mode = e.matches ? 'dark' : 'light';
});

export function toggleTheme(): void {
  theme.mode = theme.mode === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme.mode;
  try {
    localStorage.setItem(KEY, theme.mode);
  } catch {
    // storage is blocked: the pick lasts for this visit
  }
}

/** The palette the flow renderers draw with, in their index order: lanes, then particle, ink and edge. */
const PALETTE_VARS = [...LANES.map((l) => `--lane-${l}`), '--particle', '--ink', '--edge'] as const;

export interface Palette {
  css: string[];
  rgba: Float32Array;
}

export function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement);
  const css = PALETTE_VARS.map((v) => style.getPropertyValue(v).trim());
  const rgba = new Float32Array(16 * 4);
  css.forEach((hex, i) => {
    const n = parseInt(hex.slice(1), 16);
    rgba.set([((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1], i * 4);
  });
  return { css, rgba };
}
