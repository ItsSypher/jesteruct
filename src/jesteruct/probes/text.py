"""Statistics that tell readable text from garbage, in any language: the language and readability of the text
(language.py), encoding codes, odd symbols, script, and how well two readings of one page agree."""

import re
import unicodedata

import regex

from ..models import TextStats
from .language import UNSPACED, identify

_WORD = regex.compile(r"[\p{L}\p{M}]{3,}")  # a word of three or more letters, in any script
_CID = re.compile(r"\(cid:\d+\)")


def _script(ch: str) -> str:
    name = unicodedata.name(ch, "")
    if "LATIN" in name:
        return "latin"
    if any(k in name for k in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL")):
        return "cjk"
    if "ARABIC" in name:
        return "arabic"
    if "CYRILLIC" in name:
        return "cyrillic"
    return "other"


def _mathy(ch: str) -> bool:
    """A mathematical symbol or operator (ASCII + = < > included), a Greek letter or a mathematical alphanumeric."""
    return unicodedata.category(ch) == "Sm" or "Ͱ" <= ch <= "Ͽ" or "\U0001d400" <= ch <= "\U0001d7ff"


def text_stats(text: str, lid_model: str | None = None) -> TextStats:
    """The statistics of a text; with `lid_model`, also its language and readability."""
    tokens = text.split()
    n = max(1, len(text))
    visible = [ch for ch in text if not ch.isspace()]
    scripts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            key = _script(ch)
            scripts[key] = scripts.get(key, 0) + 1
    letters = sum(scripts.values()) or 1
    language, readability, unreadable = identify(text, lid_model) if lid_model and text.strip() else ("", None, "")
    return TextStats(
        chars=len(text.strip()),
        cid_share=len(_CID.findall(text)) * 7 / n,
        odd_char_share=sum(unicodedata.category(ch) in ("Co", "Cn", "So") or ch == "�" for ch in text) / n,
        short_token_share=sum(len(t) < 2 for t in tokens) / max(1, len(tokens)),
        math_share=sum(map(_mathy, visible)) / max(1, len(visible)),
        script={k: round(v / letters, 2) for k, v in scripts.items()},
        language=language,
        readability=readability,
        unreadable=unreadable,
    )


def _units(text: str) -> set[str]:
    """Words of three or more letters in any script, and character pairs in scripts written without spaces."""
    text = text.lower()
    pairs = {run[i : i + 2] for run in UNSPACED.findall(text) for i in range(len(run) - 1)}
    return set(_WORD.findall(UNSPACED.sub(" ", text))) | pairs


def agreement(layer: str, ocr: str) -> float | None:
    """Jaccard similarity of the two readings' units; None when the layer has none."""
    a = _units(layer)
    if not a:
        return None
    b = _units(ocr)
    return round(len(a & b) / len(a | b), 3)
