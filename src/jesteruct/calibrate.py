"""Review-threshold calibration: map the raw path probability to P(candidate lane correct), then pick the threshold.

The fit is isotonic (pool adjacent violators) on `jst evaluate` results, one curve per candidate lane, because the same
path probability means different things in different lanes; a lane with few results uses the curve of all lanes. A
page sent to review costs 1 and a kept page costs cost_ratio x (1 - p), where p is its calibrated probability, so
review is the cheaper choice exactly when p < 1 - 1/cost_ratio. That makes the threshold a function of the cost ratio
alone; the data decides which raw path probabilities fall below it.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from .models import LANE_RANK

_JEV_LANES = {"L1", "L2", "L3", "L4", "L5"}  # candidates decided by the rule table; fixed routes carry path_p 1.0
MIN_LANE_ROWS = 30  # results a lane needs for a curve of its own

Curve = list[tuple[float, float]]  # (raw path_p, P(candidate correct)), both non-decreasing


class Calibration(BaseModel):
    version: str
    pooled: Curve  # all lanes together
    lanes: dict[str, Curve]  # per candidate lane, for lanes with at least MIN_LANE_ROWS results
    threshold: float  # calibrated probability below which a page goes to LH
    cost_ratio: float  # cost of a silent wrong lane / cost of one review
    n: int
    basis: str | None = None  # the answer basis of the results it was fitted on (pipeline.answer_basis)
    fitted_on: str = ""

    def __call__(self, lane: str, path_p: float) -> float:
        xs, ys = zip(*self.lanes.get(lane, self.pooled), strict=True)
        return float(np.interp(path_p, xs, ys))  # clamps to the end values outside the fitted range


def _usable(rows: list[dict]) -> list[dict]:
    return [r for r in rows if "error" not in r and r.get("candidate") in _JEV_LANES]


def _isotonic(x: np.ndarray, y: np.ndarray) -> list[tuple[float, float]]:
    """Non-decreasing least-squares fit of y on x, as interpolation knots; each pooled block is flat over its x span."""
    xs, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, weights=y)
    blocks: list[list[float]] = []  # [sum of y, weight, first x, last x]
    for xi, s, w in zip(xs, sums, counts, strict=True):
        blocks.append([float(s), float(w), float(xi), float(xi)])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
            s2, w2, _, hi = blocks.pop()
            blocks[-1][0] += s2
            blocks[-1][1] += w2
            blocks[-1][3] = hi
    points: list[tuple[float, float]] = []
    for s, w, lo, hi in blocks:
        p = round(s / w, 4)
        points.append((lo, p))
        if hi > lo:
            points.append((hi, p))
    return points


def _curve(rows: list[dict]) -> Curve:
    x = np.array([r["path_p"] for r in rows], dtype=float)
    y = np.array([r["candidate"] in r["gt"] for r in rows], dtype=float)
    return _isotonic(x, y)


def fit(rows: list[dict], cost_ratio: float = 10.0, fitted_on: str = "") -> Calibration:
    """Fit on `jst evaluate` results rows (path_p, candidate, gt); error rows and fixed routes are skipped."""
    if cost_ratio <= 0:
        raise ValueError("cost_ratio must be positive")
    usable = _usable(rows)
    if not usable:
        raise ValueError("no routed rows to fit on")
    bases = {r.get("basis") for r in usable}
    if len(bases) > 1:
        raise ValueError(f"results come from {len(bases)} different evidence or model versions; fit on one")
    (basis,) = bases
    by_lane = {lane: [r for r in usable if r["candidate"] == lane] for lane in sorted(_JEV_LANES)}
    pooled = _curve(usable)
    lanes = {lane: _curve(rs) for lane, rs in by_lane.items() if len(rs) >= MIN_LANE_ROWS}
    threshold = round(max(0.0, 1 - 1 / cost_ratio), 6)
    digest = hashlib.sha256(json.dumps([pooled, lanes, threshold, basis]).encode()).hexdigest()[:10]
    return Calibration(
        version=f"c2-{digest}",
        pooled=pooled,
        lanes=lanes,
        threshold=threshold,
        cost_ratio=cost_ratio,
        n=len(usable),
        basis=basis,
        fitted_on=fitted_on,
    )


def load(path: Path) -> Calibration | None:
    return Calibration.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def save(cal: Calibration, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cal.model_dump_json(indent=2) + "\n", encoding="utf-8")


def evaluate(cal: Calibration, rows: list[dict]) -> dict:
    """What the calibrated threshold does on a results set: review rate, and what the kept pages get wrong."""
    usable = _usable(rows)
    n = len(usable)
    if n == 0:
        return {"n": 0}
    reviewed = reviewed_wrong = kept_correct = silent_wrong = silent_under = 0
    for r in usable:
        correct = r["candidate"] in r["gt"]
        if cal(r["candidate"], r["path_p"]) < cal.threshold:
            reviewed += 1
            reviewed_wrong += not correct
            continue
        kept_correct += correct
        silent_wrong += not correct
        gt_ranks = [LANE_RANK[g] for g in r["gt"] if g in LANE_RANK]
        silent_under += bool(gt_ranks) and LANE_RANK[r["candidate"]] < min(gt_ranks)
    kept = n - reviewed
    return {
        "n": n,
        "threshold": cal.threshold,
        "review_rate": round(reviewed / n, 4),
        "reviewed_wrong": round(reviewed_wrong / reviewed, 4) if reviewed else None,  # reviews that caught an error
        "kept_accuracy": round(kept_correct / kept, 4) if kept else None,
        "silent_wrong": round(silent_wrong / n, 4),
        "silent_under_route": round(silent_under / n, 4),
        "cost_per_page": round((reviewed + cal.cost_ratio * silent_wrong) / n, 4),
    }
