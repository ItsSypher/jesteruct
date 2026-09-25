// The API contract (src/jesteruct/models.py, api.py and events.py), as the Studio reads it.

export const LANES = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'LQ', 'LH'] as const;
export type Lane = (typeof LANES)[number];

export const STAGES = ['probe', 'ocr', 'vision', 'jev', 'policy'] as const;
export type Stage = (typeof STAGES)[number];
export type StageState = 'start' | 'done' | 'skip' | 'fail';

export type DocKind = 'pdf' | 'image' | 'office' | 'text' | 'email' | 'archive' | 'unknown';
export type JobStatus = 'queued' | 'running' | 'done' | 'failed';

export interface VisionFacts {
  capture: string;
  legibility: string;
  handwriting: string;
  script: string;
  content: Record<string, boolean>;
  defects: Record<string, boolean>;
}

/** What the language probe made of a PDF text layer, in any language. */
export interface TextReading {
  language: string; // ISO 639-3; "" when no single language holds most of the text
  name: string;
  readability: number | null; // probability that the letters are real language; null with too few to judge
  unreadable: string; // why it does not read as language; "" when it does
}

export interface PageRoute {
  index: number;
  lane: Lane;
  candidate_lane: Lane;
  path_p: number;
  confidence: number | null;
  answers: Record<string, number>;
  modifiers: string[];
  degradation: number | null;
  continuation: number | null;
  vision: VisionFacts | null;
  text?: TextReading | null; // absent from manifests stored before e4, and null for image files
  reasons: string[];
  evidence?: string | null; // what Jev was told; absent from manifests stored before it was recorded
  thumb_key: string | null;
  timings_ms: Partial<Record<'probe' | 'ocr' | 'vision' | 'jev' | 'total', number>>;
}

export interface Segment {
  start: number;
  end: number;
  lane: Lane;
  modifiers: string[];
}

export interface DocFacts {
  name: string;
  kind: DocKind;
  mime: string;
  page_count: number;
  parent_sha: string | null;
  quarantine: string | null;
}

export interface Manifest {
  doc: DocFacts & { sha256: string; size: number };
  route_key: string;
  pages: PageRoute[];
  segments: Segment[];
  cost_usd: number;
}

export interface JobIndex {
  job_id: string;
  status: JobStatus;
  documents: { doc_sha: string; name: string; parent_sha: string | null; lanes: Record<string, number> }[];
  error: string | null;
}

export interface Submitted {
  job_id: string;
  status: JobStatus;
}

export type QuestionGroup = 'routing' | 'modifier' | 'continuation';

export interface Info {
  version: string;
  route_key: string;
  evidence: string;
  policy: string;
  jev_model: string;
  vision_model: string;
  calibration: { version: string; threshold: number } | null;
  questions: Record<string, { group: QuestionGroup; instructions: string; criteria?: string[] | null }>;
  lanes: Record<Lane, string>;
}

export interface Layout {
  model: string;
  counts: Record<string, number>;
  area: Record<string, number>;
  columns: 1 | 2 | null;
}

export interface ProbeFacts {
  text_layer_trusted: boolean;
  evidence: string;
  image: Record<string, number>;
  layout: Layout | null;
  pdf: Record<string, unknown> | null;
  text?: TextReading | null;
}

export interface OcrFacts {
  lines: number;
  confidence: number;
  backend: string;
}

export interface JevFacts {
  answers: Record<string, number>;
  model: string | null;
  evidence?: string;
}

export type PolicyFacts = PageRoute & { thumb: string | null };

interface Base {
  job_id: string;
  at: number;
}

type StageEvent<S extends Stage, D> =
  | { stage: S; state: 'done'; ms: number | null; data: D }
  | { stage: S; state: 'start' | 'skip' | 'fail'; ms?: null; data?: null };

export type PageStage = Base & { type: 'page.stage'; doc_sha: string; page: number } & (
    | StageEvent<'probe', ProbeFacts>
    | StageEvent<'ocr', OcrFacts | null>
    | StageEvent<'vision', VisionFacts>
    | StageEvent<'jev', JevFacts>
    | StageEvent<'policy', PolicyFacts>
  );

export type StudioEvent =
  | (Base & { type: 'job.queued'; name: string; size: number })
  | (Base & { type: 'job.started' })
  | (Base & { type: 'job.retry'; error: string | null; deliveries: number })
  | (Base & { type: 'job.done'; status: 'done' | 'failed'; error: string | null })
  | (Base & DocFacts & { type: 'doc'; doc_sha: string })
  | PageStage
  | (Base & {
      type: 'doc.done';
      doc_sha: string;
      route_key: string;
      lanes: Partial<Record<Lane, number>>;
      segments: Segment[];
      cost_usd: number;
      cached: boolean;
    });

export const EVENT_TYPES = ['job.queued', 'job.started', 'job.retry', 'job.done', 'doc', 'page.stage', 'doc.done'] as const;
