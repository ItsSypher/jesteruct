import sys

import pytest

from jesteruct.probes import ocr


@pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS only")
def test_auto_uses_rapidocr_when_apple_vision_does_not_answer(monkeypatch):
    monkeypatch.setattr(ocr, "_apple_answers", lambda: False)
    assert ocr.resolve_backend("auto") == "rapid"
    monkeypatch.setattr(ocr, "_apple_answers", lambda: True)
    assert ocr.resolve_backend("auto") == "apple"
    assert ocr.resolve_backend("rapid") == "rapid"  # an explicit backend is never second-guessed
