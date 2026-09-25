// What each node does, in plain words: a line on the canvas, and an explainer on hover or click.

import type { Step } from '../flow/graph';
import type { Info, Lane } from './types';

export interface Explainer {
  title: string;
  line: string;
  measures: string;
  why: string;
  passes: string;
}

export function steps(info: Info | null): Record<Step, Explainer> {
  const vision = info?.vision_model ?? 'the vision model';
  const jev = info?.jev_model ?? 'Jev';
  const threshold = info?.calibration ? info.calibration.threshold.toFixed(2) : 'the threshold';
  return {
    intake: {
      title: 'Intake',
      line: 'Sniffs bytes, opens zips and emails, applies limits',
      measures:
        'The file type from its first bytes, never its name. Zip archives and emails are opened, and every file inside becomes a document of its own. Size, page and depth limits are checked here.',
      why: 'A renamed or broken file still lands in the right place. Native office and text files need no rendering, so they go straight to L0; encrypted, corrupt, unsupported or oversized inputs go to LQ with a reason.',
      passes: 'Routable documents and their page counts, one page at a time.',
    },
    probes: {
      title: 'Probes',
      line: 'PDF structure, 1024 px render, quality, layout, text',
      measures:
        'The PDF text layer and structure (image coverage, invisible OCR text, fonts, producer), a 1024 px render with sharpness, contrast, noise and colour, a small layout model for tables, formulas, figures and columns, and statistics of the text.',
      why: 'Cheap facts, measured in a process pool in well under a second. A cheap rule then decides whether the text layer can be trusted.',
      passes: 'The measurements, and whether the page needs OCR and a vision check.',
    },
    ocr: {
      title: 'OCR',
      line: 'A quick text pass, only without a trusted layer',
      measures:
        'Text lines and their confidence, from Apple Vision on a Mac or RapidOCR in the containers. On a PDF page the fresh text is compared with the embedded layer.',
      why: 'A text layer that disagrees with fresh OCR is usually OCR run over handwriting, or a garbled encoding.',
      passes: 'Line count, confidence and agreement, for the evidence.',
    },
    vision: {
      title: 'Vision',
      line: `${vision} looks at the page image`,
      measures:
        'How the page was captured (scan, photo, fax, screenshot), legibility, handwriting, defects such as photocopy artefacts or bleed-through, content such as tables and math, and the main script.',
      why: 'The one step that looks at the page the way a person does. It is also the slowest, which is why pages wait here while born-digital pages skip it.',
      passes: 'Vision facts, for the evidence and the manifest.',
    },
    evidence: {
      title: 'Evidence',
      line: `Measurements put into words, frozen at ${info?.evidence ?? 'one version'}`,
      measures: 'Every measurement is binned into fixed phrases: "sharp", "low contrast", "a full page of text", "no formula blocks".',
      why: 'Jev reasons well over words and poorly over raw numbers. The wording is versioned and changes only together with an evaluation run.',
      passes: 'One paragraph of evidence per page.',
    },
    jev: {
      title: 'Jev',
      line: 'Six yes/no routing questions, plus modifiers',
      measures: `${jev} answers narrow questions: trusted text layer, mostly handwritten, camera or fax, heavily degraded, capture defects, complex layout; then table, math, code, form, handwriting, degradation and continuation.`,
      why: 'Narrow yes/no questions and a rule table reached 0.92 to 0.94 lane accuracy, against 0.80 for one question with every lane as an option.',
      passes: 'A probability for every question.',
    },
    policy: {
      title: 'Policy',
      line: 'Rule table, then calibrated review',
      measures:
        'Handwriting first, then text-layer trust, then the image condition. The answers along the rule path become a calibrated probability that the lane is right.',
      why: `Below ${threshold} a page goes to human review (LH) and keeps its candidate lane: one review costs less than a page silently sent to the wrong lane.`,
      passes: 'The lane, modifiers and reasons, written to the manifest.',
    },
  };
}

export const LANE_NAMES: Record<Lane, string> = {
  L0: 'Native format',
  L1: 'Born-digital, simple',
  L2: 'Born-digital, complex',
  L3: 'Clean scan',
  L4: 'Degraded, photo, fax',
  L5: 'Handwriting',
  LQ: 'Quarantine',
  LH: 'Human review',
};

export const EDGE_NOTES = {
  bypass: 'trusted text layer',
  native: 'native formats need no rendering',
  quarantine: 'quarantined at intake',
} as const;
