import * as api from '../lib/api';
import type { DocView, PageView } from '../lib/reducer';

/** The page image: the one the route names, or, against a live API, the stored one as soon as Jev is asked
 * (the worker writes thumbnails before it asks). Offline, only what the fixture carries. */
export function thumbFor(doc: DocView, page: PageView, live: boolean): string | null {
  if (page.thumb) return page.thumb;
  if (live && page.stages.jev) return api.thumb(doc.sha, page.index);
  return null;
}
