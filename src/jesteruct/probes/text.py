"""Statistics that tell readable text from garbage: common-word share, encoding codes, odd symbols, script, and how
well two readings of one page agree."""

import re
import unicodedata

from ..models import TextStats

_WORD = re.compile(r"[A-Za-z]{2,}")
_AGREEMENT_WORD = re.compile(r"[A-Za-z]{3,}")
_CID = re.compile(r"\(cid:\d+\)")
_COMMON = set(
    "the of and to in a is that for it as was with be by on not he this are or his from at which but have an they "
    "you were her she there been one all we their has would when who will more if no out so said what up its about "
    "into than them can only other new some could time these two may then do first any my now such like our over "
    "man me even most made after also did many before must through back years where much your way well down should "
    "because each just those people how too little state good very make world still own see men work long get here "
    "between both life being under never day same another know while last might us great old year off come since "
    "against go came right used take three".split()
)


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


def text_stats(text: str) -> TextStats:
    tokens = text.split()
    words = _WORD.findall(text)
    n = max(1, len(text))
    scripts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            key = _script(ch)
            scripts[key] = scripts.get(key, 0) + 1
    letters = sum(scripts.values()) or 1
    return TextStats(
        chars=len(text.strip()),
        cid_share=len(_CID.findall(text)) * 7 / n,
        odd_char_share=sum(unicodedata.category(ch) in ("Co", "Cn", "So") or ch == "�" for ch in text) / n,
        short_token_share=sum(len(t) < 2 for t in tokens) / max(1, len(tokens)),
        common_word_share=sum(w.lower() in _COMMON for w in words) / max(1, len(words)),
        script={k: round(v / letters, 2) for k, v in scripts.items()},
    )


def agreement(layer: str, ocr: str) -> float | None:
    """Jaccard similarity of the lower-cased words of three or more letters; None when the layer has no such words."""
    a = {w.lower() for w in _AGREEMENT_WORD.findall(layer)}
    if not a:
        return None
    b = {w.lower() for w in _AGREEMENT_WORD.findall(ocr)}
    return round(len(a & b) / len(a | b), 3)
