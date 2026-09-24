"""Group consecutive pages into segments, without ever downgrading a merged run."""

from .models import LANE_RANK, Lane, PageRoute, Segment

# Continuation-based merging only applies inside the scan-quality ladder; L0 (native
# text) and the LQ/LH outliers merge only when the lane is exactly the same.
_CONTINUATION_LANES = {"L1", "L2", "L3", "L4", "L5"}


def segment(pages: list[PageRoute]) -> list[Segment]:
    """Merge consecutive pages into runs, in page order."""
    runs: list[dict] = []
    for page in pages:
        if runs and _joins(runs[-1], page):
            run = runs[-1]
            run["end"] = page.index
            run["lane"] = _merged_lane(run["lane"], page.lane)
            run["modifiers"] |= set(page.modifiers)
        else:
            runs.append({"start": page.index, "end": page.index, "lane": page.lane, "modifiers": set(page.modifiers)})
    return [Segment(start=r["start"], end=r["end"], lane=r["lane"], modifiers=sorted(r["modifiers"])) for r in runs]


def _joins(run: dict, page: PageRoute) -> bool:
    if page.lane == run["lane"]:
        return True
    if run["lane"] not in _CONTINUATION_LANES or page.lane not in _CONTINUATION_LANES:
        return False
    return (page.continuation or 0) >= 0.5


def _merged_lane(run_lane: Lane, page_lane: Lane) -> Lane:
    if run_lane == page_lane:
        return run_lane
    return run_lane if LANE_RANK[run_lane] >= LANE_RANK[page_lane] else page_lane
