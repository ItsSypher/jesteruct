// The HTTP API and the event stream. Every URL is relative: the API serves the Studio, and `pnpm dev` proxies /v1.

import { EVENT_TYPES, type Info, type JobIndex, type Manifest, type StudioEvent, type Submitted } from './types';

const HISTORY = 500; // events replayed on connect, so a reload keeps the recent picture

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${url}`);
  return (await r.json()) as T;
}

interface Reachable {
  info: Info;
  skew: number; // server clock minus this clock, in ms, from the Date header (to the second)
}

/** The API's description of itself, or null when it cannot be reached in time. */
export async function reach(timeoutMs = 2500): Promise<Reachable | null> {
  try {
    const r = await fetch('/v1/info', { signal: AbortSignal.timeout(timeoutMs) });
    if (!r.ok) return null;
    const date = Date.parse(r.headers.get('date') ?? '');
    return { info: (await r.json()) as Info, skew: Number.isNaN(date) ? 0 : date + 500 - Date.now() };
  } catch {
    return null;
  }
}

export type Link = 'connecting' | 'live' | 'reconnecting';

/** Subscribe to every event in the system. EventSource resumes by Last-Event-ID after a drop. */
export function subscribe(onEvent: (e: StudioEvent) => void, onLink: (l: Link) => void): () => void {
  const source = new EventSource(`/v1/events?last=${HISTORY}`);
  const handle = (m: MessageEvent<string>) => onEvent(JSON.parse(m.data) as StudioEvent);
  for (const type of EVENT_TYPES) source.addEventListener(type, handle);
  source.onopen = () => onLink('live');
  source.onerror = () => onLink(source.readyState === EventSource.CLOSED ? 'connecting' : 'reconnecting');
  return () => source.close();
}

/** Submit one file as a job, reporting upload progress from 0 to 1. */
export function submit(file: Blob, name: string, onProgress: (f: number) => void): Promise<Submitted> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('file', file, name);
    xhr.open('POST', '/v1/jobs');
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status < 300
        ? resolve(xhr.response as Submitted)
        : reject(new Error(xhr.response?.detail ?? `${xhr.status} ${xhr.statusText}`));
    xhr.onerror = () => reject(new Error('the upload did not reach the API'));
    xhr.send(form);
  });
}

export const job = (id: string) => json<JobIndex>(`/v1/jobs/${encodeURIComponent(id)}`);
export const manifest = (sha: string) => json<Manifest>(`/v1/manifests/${sha}`);
export const thumb = (sha: string, page: number) => `/v1/thumbs/${sha}/${page}`;
