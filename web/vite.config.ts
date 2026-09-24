/// <reference types="vitest/config" />
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// `pnpm dev` proxies the API; in production the API serves web/dist itself, so every URL stays relative.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: { '/v1': { target: process.env.JST_API ?? 'http://localhost:8000', changeOrigin: true } },
  },
  build: { target: 'es2022', assetsInlineLimit: 0, chunkSizeWarningLimit: 400 },
  test: { include: ['src/**/*.test.ts'] },
});
