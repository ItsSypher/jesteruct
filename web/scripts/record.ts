// Record the offline replay fixture from a real run. Run the demo in the Studio against a live API first, then
// `pnpm record` (JST_API defaults to http://localhost:8000). It reads the API's recent event history, keeps the
// newest finished job for each file name, saves the thumbnails next to the Studio, and writes
// src/fixtures/demo-events.json.

import { mkdir, rm, writeFile } from 'node:fs/promises';

const API = process.env.JST_API ?? 'http://localhost:8000';
const HISTORY = 1000;
const IDLE_MS = 2500;
const THUMBS = new URL('../public/replay/', import.meta.url);
const FIXTURE = new URL('../src/fixtures/demo-events.json', import.meta.url);

type Event = { type: string; job_id: string; at: number; [k: string]: unknown };

/** The event stream's history: everything it replays on connect, until it goes quiet. */
async function history(): Promise<Event[]> {
  const abort = new AbortController();
  const response = await fetch(`${API}/v1/events?last=${HISTORY}`, { signal: abort.signal });
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
  const events: Event[] = [];
  let buffer = '';
  let idle = setTimeout(() => abort.abort(), IDLE_MS * 2);
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        const data = frame.split('\n').find((line) => line.startsWith('data: '));
        if (!data) continue;
        events.push(JSON.parse(data.slice(6)) as Event);
        clearTimeout(idle);
        idle = setTimeout(() => abort.abort(), IDLE_MS);
      }
    }
  } catch (e) {
    if (!abort.signal.aborted) throw e;
  }
  return events;
}

const info = await (await fetch(`${API}/v1/info`)).json();
const events = await history();

// the newest job for each file that finished, so repeated runs do not pile up
const newest = new Map<string, string>();
const finished = new Set(events.filter((e) => e.type === 'job.done' && e.status === 'done').map((e) => e.job_id));
for (const e of events) if (e.type === 'job.queued' && finished.has(e.job_id)) newest.set(String(e.name), e.job_id);
const keep = new Set(newest.values());
const recorded = events.filter((e) => keep.has(e.job_id));

await rm(THUMBS, { recursive: true, force: true });
await mkdir(THUMBS, { recursive: true });
for (const e of recorded) {
  const data = e.data as { thumb?: string | null } | null | undefined;
  if (e.type !== 'page.stage' || e.stage !== 'policy' || !data?.thumb) continue;
  const file = `${e.doc_sha}-${e.page}.jpg`;
  const image = await fetch(`${API}${data.thumb}`);
  if (!image.ok) continue;
  await writeFile(new URL(file, THUMBS), Buffer.from(await image.arrayBuffer()));
  data.thumb = `/replay/${file}`;
}

await writeFile(FIXTURE, JSON.stringify({ info, events: recorded }) + '\n');
console.log(`${keep.size} jobs, ${recorded.length} events recorded from ${API}`);
