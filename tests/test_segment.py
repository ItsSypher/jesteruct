from jesteruct.models import PageRoute
from jesteruct.segment import segment


def _page(index: int, lane: str, continuation: float | None = None, modifiers: list[str] | None = None) -> PageRoute:
    return PageRoute(
        index=index,
        lane=lane,
        candidate_lane=lane,
        path_p=0.9,
        continuation=continuation,
        modifiers=modifiers or [],
    )


def test_same_lane_pages_merge_into_one_segment():
    pages = [_page(0, "L1"), _page(1, "L1"), _page(2, "L1")]

    segments = segment(pages)

    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == 2
    assert segments[0].lane == "L1"


def test_different_lanes_without_continuation_stay_separate():
    pages = [_page(0, "L1"), _page(1, "L2", continuation=0.1)]

    segments = segment(pages)

    assert [s.lane for s in segments] == ["L1", "L2"]
    assert [(s.start, s.end) for s in segments] == [(0, 0), (1, 1)]


def test_continuation_merges_and_never_downgrades():
    pages = [_page(0, "L1"), _page(1, "L2", continuation=0.75), _page(2, "L1", continuation=0.9)]

    segments = segment(pages)

    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == 2
    assert segments[0].lane == "L2"  # the higher-capability lane wins, the run is never downgraded


def test_lh_and_lq_only_merge_with_the_exact_same_lane():
    pages = [_page(0, "L2"), _page(1, "LH", continuation=0.95), _page(2, "LH"), _page(3, "L2", continuation=0.95)]

    segments = segment(pages)

    assert [s.lane for s in segments] == ["L2", "LH", "L2"]
    assert [(s.start, s.end) for s in segments] == [(0, 0), (1, 2), (3, 3)]


def test_modifiers_are_the_sorted_union_of_merged_pages():
    pages = [_page(0, "L1", modifiers=["table"]), _page(1, "L1", modifiers=["math", "table"])]

    segments = segment(pages)

    assert len(segments) == 1
    assert segments[0].modifiers == ["math", "table"]
