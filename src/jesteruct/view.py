"""Render every manifest under a directory into one self-contained HTML report."""

import base64
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .config import Settings
from .models import LANES, Manifest
from .store import Store


async def render_dir(manifests_dir: Path, settings: Settings, out: Path) -> Path:
    manifests = _load_manifests(manifests_dir)
    store = Store.from_settings(settings)
    documents = [await _document_view(manifest, store) for manifest in manifests]

    env = Environment(loader=PackageLoader("jesteruct", "templates"), autoescape=select_autoescape(["html"]))
    html = env.get_template("report.html.j2").render(documents=documents, lanes=LANES)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _load_manifests(manifests_dir: Path) -> list[Manifest]:
    manifests = []
    for path in sorted(manifests_dir.rglob("*.json")):
        try:
            manifests.append(Manifest.model_validate_json(path.read_text()))
        except Exception:
            continue  # not a manifest; skip it
    return manifests


async def _document_view(manifest: Manifest, store: Store) -> dict:
    total = len(manifest.pages) or 1
    pages = [{"route": page, "thumb": await _thumb_uri(store, page.thumb_key)} for page in manifest.pages]
    lane_counts: dict[str, int] = {}
    for page in manifest.pages:
        lane_counts[page.lane] = lane_counts.get(page.lane, 0) + 1
    segments = [
        {
            "lane": seg.lane,
            "start": seg.start,
            "end": seg.end,
            "modifiers": seg.modifiers,
            "width_pct": (seg.end - seg.start + 1) / total * 100,
        }
        for seg in manifest.segments
    ]
    return {
        "doc": manifest.doc,
        "route_key": manifest.route_key,
        "created_at": manifest.created_at,
        "page_count": len(manifest.pages),
        "lane_counts": lane_counts,
        "segments": segments,
        "pages": pages,
    }


async def _thumb_uri(store: Store, thumb_key: str | None) -> str | None:
    if thumb_key is None:
        return None
    data = await store.get(thumb_key)
    if data is None:
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode('ascii')}"
