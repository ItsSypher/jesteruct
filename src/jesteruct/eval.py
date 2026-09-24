"""`jst evaluate`: route the labelled set through the real pipeline and report lane accuracy, review rate, latency
and cost, overall and per group (img/pdf/ocr/garb). Never calls a provider itself; it drives the Router.
"""

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel

from .config import Settings
from .models import LANE_RANK, Lane
from .store import Store

_METRIC_COLUMNS = (
    "n",
    "accuracy",
    "candidate_accuracy",
    "under_route",
    "candidate_under_route",
    "over_route",
    "review_rate",
    "p50_ms",
    "p95_ms",
    "cost_usd",
    "cost_per_1k",
)


class EvalCase(BaseModel):
    id: str
    file: str
    page: int = 0
    gt: list[Lane]
    group: str
    source: str = ""
    text_override: str | None = None


def _load_cases(path: Path, limit: int | None) -> list[EvalCase]:
    with open(path, encoding="utf-8") as fh:
        cases = [EvalCase.model_validate_json(line) for line in fh if line.strip()]
    return cases[:limit] if limit else cases


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {**dict.fromkeys(_METRIC_COLUMNS, 0), "confusion": {}}
    # under_route counts silent failures: the final lane is too weak. A page sent to review (LH) is not silent, so
    # it only shows in candidate_under_route, the policy's lane before review.
    under = candidate_under = over = 0
    for row in rows:
        gt_ranks = [LANE_RANK[g] for g in row["gt"] if g in LANE_RANK]
        if not gt_ranks:
            continue
        if row["lane"] in LANE_RANK:
            under += LANE_RANK[row["lane"]] < min(gt_ranks)
            over += LANE_RANK[row["lane"]] > max(gt_ranks)
        if row["candidate"] in LANE_RANK:
            candidate_under += LANE_RANK[row["candidate"]] < min(gt_ranks)
    latencies = [row["latency_ms"] for row in rows]
    cost = sum(row["cost_usd"] for row in rows)
    confusion: dict[str, dict[str, int]] = {}
    for row in rows:
        key = "/".join(row["gt"])
        confusion.setdefault(key, {}).setdefault(row["candidate"], 0)
        confusion[key][row["candidate"]] += 1
    return {
        "n": n,
        "accuracy": round(sum(row["lane"] in row["gt"] for row in rows) / n, 4),
        "candidate_accuracy": round(sum(row["candidate"] in row["gt"] for row in rows) / n, 4),
        "under_route": round(under / n, 4),
        "candidate_under_route": round(candidate_under / n, 4),
        "over_route": round(over / n, 4),
        "review_rate": round(sum(row["lane"] == "LH" for row in rows) / n, 4),
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "cost_usd": round(cost, 6),
        "cost_per_1k": round(cost / n * 1000, 4),
        "confusion": confusion,
    }


def _report_md(summary: dict, rows: list[dict], errors: list[dict]) -> str:
    lines = ["# Eval report", ""]
    header = ["group", *_METRIC_COLUMNS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for name in ("overall", "img", "pdf", "ocr", "garb"):
        m = summary["groups"].get(name) if name != "overall" else summary["overall"]
        if m is None or m["n"] == 0:
            continue
        lines.append("| " + name + " | " + " | ".join(str(m[c]) for c in _METRIC_COLUMNS) + " |")
    lines.append("")

    lines.append("## Confusion (gt -> candidate lane)")
    lines.append("")
    confusion = summary["overall"]["confusion"]
    candidates = sorted({c for row in confusion.values() for c in row})
    lines.append("| gt | " + " | ".join(candidates) + " |")
    lines.append("|" + "---|" * (len(candidates) + 1))
    for gt_key in sorted(confusion):
        counts = [str(confusion[gt_key].get(c, 0)) for c in candidates]
        lines.append(f"| {gt_key} | " + " | ".join(counts) + " |")
    lines.append("")

    wrong = [row for row in rows if row["lane"] not in row["gt"]]
    lines.append(f"## Wrong cases ({len(wrong)})")
    lines.append("")
    for row in wrong:
        lines.append(
            f"- `{row['id']}`: gt {row['gt']}, routed {row['lane']} (candidate {row['candidate']}), "
            f"reasons: {row['reasons']}"
        )
    if errors:
        lines.append("")
        lines.append(f"## Errors ({len(errors)})")
        lines.append("")
        for e in errors:
            lines.append(f"- `{e['id']}`: {e['error']}")
    return "\n".join(lines) + "\n"


async def run_eval(cases: Path, settings: Settings, out: Path, limit: int | None = None) -> dict:
    from .pipeline import answer_basis, open_router

    out.mkdir(parents=True, exist_ok=True)
    basis = answer_basis(settings)  # recorded on every row, so `jst calibrate` knows what the answers came from
    root = cases.parent
    eval_cases = _load_cases(cases, limit)
    sem = asyncio.Semaphore(settings.page_concurrency)
    rows: list[dict] = []
    errors: list[dict] = []

    async with open_router(settings, Store.from_settings(settings)) as router:

        async def run_one(case: EvalCase) -> None:
            overrides = {case.page: case.text_override} if case.text_override is not None else None
            async with sem:
                try:
                    # always route afresh; provider responses still come from the cache, so re-runs are cheap
                    manifests = await router.route_file(root / case.file, text_overrides=overrides, reuse=False)
                    route = manifests[0].pages[case.page]
                except Exception as e:  # a case that can't be routed is an error, not a crash
                    errors.append({"id": case.id, "error": f"{type(e).__name__}: {e}"})
                    return
            rows.append(
                {
                    "id": case.id,
                    "group": case.group,
                    "gt": case.gt,
                    "lane": route.lane,
                    "candidate": route.candidate_lane,
                    "path_p": route.path_p,
                    "basis": basis,
                    "answers": route.answers,
                    "vision_used": route.vision is not None,
                    "reasons": route.reasons,
                    "latency_ms": route.timings_ms.get("total", sum(route.timings_ms.values())),
                    "cost_usd": manifests[0].cost_usd,
                }
            )

        await asyncio.gather(*(run_one(c) for c in eval_cases))

    rows.sort(key=lambda r: next(i for i, c in enumerate(eval_cases) if c.id == r["id"]))
    summary = {
        "n_cases": len(eval_cases),
        "n_errors": len(errors),
        "overall": _metrics(rows),
        "groups": {g: _metrics([r for r in rows if r["group"] == g]) for g in ("img", "pdf", "ocr", "garb")},
        "errors": errors,
    }

    with open(out / "results.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({k: v for k, v in row.items() if k != "group"}, ensure_ascii=False) + "\n")
        for e in errors:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(_report_md(summary, rows, errors), encoding="utf-8")

    return summary
