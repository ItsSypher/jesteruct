"""Lean tests for jesteruct.calibrate: the isotonic fit, the threshold arithmetic, persistence and evaluate()."""

from pathlib import Path

import pytest

from jesteruct import calibrate


def row(path_p: float, candidate: str, gt: list[str]) -> dict:
    return {"id": f"{candidate}-{path_p}", "path_p": path_p, "candidate": candidate, "lane": candidate, "gt": gt}


# Correctness by path_p: 0.1 wrong, 0.2 right, 0.3 wrong (violates order, pools with 0.2), 0.4-0.6 right.
TOY = [
    row(0.1, "L3", ["L4"]),
    row(0.2, "L1", ["L1"]),
    row(0.3, "L1", ["L2"]),
    row(0.4, "L2", ["L2"]),
    row(0.5, "L3", ["L3", "L4"]),
    row(0.6, "L5", ["L5"]),
]


def test_pav_is_monotone_and_pools_violators() -> None:
    cal = calibrate.fit([*TOY, {"id": "broken", "error": "boom"}, row(1.0, "LH", ["L3"])])

    assert cal.n == 6  # the error row and the fixed LH route are skipped
    ys = [p for _, p in cal.pooled]
    assert ys == sorted(ys)
    assert cal.pooled == [(0.1, 0.0), (0.2, 0.5), (0.3, 0.5), (0.4, 1.0), (0.6, 1.0)]
    assert cal.lanes == {}  # no lane has enough results for a curve of its own, so every lane uses the pooled one
    assert cal("L1", 0.25) == pytest.approx(0.5)
    assert cal("L3", 0.35) == pytest.approx(0.75)  # linear between blocks
    assert cal("L2", 0.0) == 0.0 and cal("L2", 1.0) == 1.0  # clamped outside the fitted range


def test_a_lane_with_enough_results_gets_its_own_curve() -> None:
    confident_misses = [row(0.9, "L3", ["L4"]) for _ in range(calibrate.MIN_LANE_ROWS)]
    cal = calibrate.fit([*confident_misses, *[row(0.9, "L1", ["L1"]) for _ in range(5)]])

    assert set(cal.lanes) == {"L3"}
    assert cal("L3", 0.9) == 0.0  # an L3 at 0.9 is always wrong here
    assert cal("L1", 0.9) == pytest.approx(5 / 35, abs=1e-4)  # L1 has too few results and borrows the pooled curve


def test_threshold_is_where_review_becomes_cheaper() -> None:
    assert calibrate.fit(TOY, cost_ratio=20).threshold == pytest.approx(0.95)
    assert calibrate.fit(TOY, cost_ratio=4).threshold == pytest.approx(0.75)
    assert calibrate.fit(TOY, cost_ratio=1).threshold == 0.0  # review never pays
    assert calibrate.fit(TOY, cost_ratio=20).version != calibrate.fit(TOY, cost_ratio=4).version


def test_save_load_round_trip(tmp_path: Path) -> None:
    cal = calibrate.fit(TOY, fitted_on="evalset/fresh/cases.jsonl")
    path = tmp_path / "cal" / "calibration.json"

    calibrate.save(cal, path)

    assert calibrate.load(path) == cal
    assert calibrate.load(tmp_path / "missing.json") is None


def test_evaluate_at_threshold() -> None:
    cal = calibrate.fit(TOY, cost_ratio=4)  # threshold 0.75: path_p 0.1-0.3 go to review
    rows = [*TOY, row(0.9, "L3", ["L4"])]  # a confident miss: kept, wrong and under-routed

    m = calibrate.evaluate(cal, rows)

    assert m["n"] == 7
    assert m["review_rate"] == pytest.approx(3 / 7, abs=1e-4)
    assert m["reviewed_wrong"] == pytest.approx(2 / 3, abs=1e-4)  # 0.1 and 0.3 were wrong, 0.2 was right
    assert m["kept_accuracy"] == pytest.approx(3 / 4)
    assert m["silent_wrong"] == pytest.approx(1 / 7, abs=1e-4)
    assert m["silent_under_route"] == pytest.approx(1 / 7, abs=1e-4)
    assert m["cost_per_page"] == pytest.approx((3 + 4 * 1) / 7, abs=1e-4)


def test_router_applies_only_a_calibration_of_its_own_answer_basis(tmp_path: Path, monkeypatch) -> None:
    from jesteruct import pipeline
    from jesteruct.config import Settings

    settings = Settings(openrouter_api_key="k")
    ours = [{**r, "basis": pipeline.answer_basis(settings)} for r in TOY]
    path = tmp_path / "calibration.json"
    monkeypatch.setattr(pipeline, "CALIBRATION_FILE", path)

    calibrate.save(calibrate.fit(ours), path)
    assert pipeline.load_calibration(settings) is not None
    calibrate.save(calibrate.fit(TOY), path)  # fitted on results that do not say what they came from
    assert pipeline.load_calibration(settings) is None
    with pytest.raises(ValueError):
        calibrate.fit([*ours, *TOY])
