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
      line: 'PDF structure, 1024 px render, quality, layout, language',
      measures:
        'The PDF text layer and structure (image coverage and hidden OCR text at any depth, fonts, producer), a 1024 px render with sharpness, contrast, noise and colour, a small layout model for tables, formulas, figures and columns, and the text layer’s language and whether it reads as language at all, in any of about 190 languages.',
      why: 'Cheap facts: about 50 ms of CPU a page, in a process pool. A cheap rule then trusts a text layer that reads as language and is not an OCR layer over a scan.',
      passes: 'The measurements, and whether the page needs a vision check.',
    },
    ocr: {
      title: 'OCR',
      line: 'Checks an untrusted PDF text layer against the page',
      measures:
        'Text read from the page image (RapidOCR in the containers, Apple Vision on a Mac), compared word by word with the embedded layer, in any script.',
      why: 'A layer that disagrees with the page is garbled, or OCR run over handwriting. Image files skip this step: the vision check judges them better than an OCR engine’s confidence does.',
      passes: 'How well the layer agrees with the page, for the evidence.',
    },
    vision: {
      title: 'Vision',
      line: `${vision} looks at the page image`,
      measures:
        'How the page was captured (scan, photo, fax, screenshot), legibility, handwriting, defects such as photocopy artefacts or bleed-through, content such as tables and math, and the main script.',
      why: 'The one step that looks at the page the way a person does, for every page without a trusted text layer. It is also the slowest, which is why pages wait here while born-digital pages skip it.',
      passes: 'Vision facts, for the evidence and the manifest.',
    },
    evidence: {
      title: 'Evidence',
      line: `Measurements put into words, frozen at ${info?.evidence ?? 'one version'}`,
      measures:
        'Every measurement is binned into fixed phrases: "sharp", "low contrast", "reads as French text", "no formula blocks". OCR text itself is never shown: a fluent read of handwriting outvoted the vision check.',
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
        'Handwriting first, then text-layer trust, then the image condition. A trusted page with a table, code, a form, maths or columns is complex. The answers along the rule path become a calibrated probability that the lane is right.',
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
