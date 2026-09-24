export function ms(v: number | null | undefined): string {
  if (v == null) return '-';
  if (v < 1000) return `${Math.round(v)} ms`;
  return `${(v / 1000).toFixed(v < 10_000 ? 1 : 0)} s`;
}

export function usd(v: number | null | undefined): string {
  if (v == null) return '-';
  if (v === 0) return '$0';
  if (v < 0.0001) return '<$0.0001';
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;
}

export function bytes(v: number | null | undefined): string {
  if (v == null) return '';
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${Math.round(v / 1024)} KB`;
  return `${(v / 1024 / 1024).toFixed(1)} MB`;
}

export const fixed = (v: number | null | undefined, digits = 2) => (v == null ? '-' : v.toFixed(digits));

/** `text_layer_trustworthy` reads as "text layer trustworthy". */
export const words = (key: string) => key.replace(/^(has|is)_/, '').replaceAll('_', ' ');

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "born-digital, simple" reads as "Born-digital, simple." */
export const sentence = (s: string) => `${s.charAt(0).toUpperCase()}${s.slice(1)}.`;

/** Evidence arrives as one paragraph; each sentence starts with what it describes ("Page image: ..."). */
export function sentences(evidence: string): { topic: string; text: string }[] {
  return evidence
    .split(/(?<=\.)\s+(?=[A-Z])/)
    .filter(Boolean)
    .map((s) => {
      const m = /^([A-Z][A-Za-z ]{2,28}):\s+(.*)$/.exec(s);
      return m ? { topic: m[1]!, text: m[2]! } : { topic: '', text: s };
    });
}
