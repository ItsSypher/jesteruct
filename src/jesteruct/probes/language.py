"""The language of a PDF text layer, and whether it reads as language at all, in any script (issue #7).

OpenLID-v3 (HPLT, GPL-3.0; built by scripts/openlid.py) names 194 languages and has a label, zxx_Zxxx, for text that
is no language. A layer is scored in chunks of about 80 characters weighted by their letters: its readability is the
letter-weighted probability of real language, which is near 0 for a garbled layer in any script and near 1 for text,
and its language is the one with the most weight. Two cheap guards run first, since the model sees letters, not how
they were extracted: control or undefined characters (a broken font encoding), and, in scripts written with spaces,
words that are single letters or run together. Measured against English common words, lid.176, CLD2, GlotLID and
others on the tune split and evalset/, it trusted the most born-digital layers and the fewest garbled ones.
"""

import json
import unicodedata
from functools import cache
from pathlib import Path

import fasttext
import regex

READABLE = 0.2  # readability from which a layer reads as text; born-digital tables and fragments sit at 0.2 to 0.5
_BAD_CHARS = 0.02  # control, unassigned or replacement characters per character
_ONE_LETTER = 0.5  # share of one-letter words: a layer extracted glyph by glyph
_LONG_WORDS = 0.6  # share of letters in words of 25 or more letters: a layer that lost its spaces
_MIN_LETTERS = 20  # fewer letters than this is too little to judge (a numeric table); the guards decide
_CHUNK = 80

NAMES: dict[str, str] = json.loads(Path(__file__).with_name("languages.json").read_text(encoding="utf-8"))
_LETTER = regex.compile(r"\p{L}")
_NOT_WORD = regex.compile(r"[^\p{L}\p{M}\s]")  # OpenLID's own preprocessing keeps letters and marks
_SPACE = regex.compile(r"\s+")
UNSPACED = regex.compile(r"[\p{Han}\p{Hiragana}\p{Katakana}\p{Thai}\p{Lao}\p{Khmer}\p{Myanmar}\p{Tibetan}]+")
_ALLOWED_CONTROLS = set("\t\n\r\f")


def check(path: str) -> str:
    """The model's path, expanded; a missing file stops the router at startup rather than on its first PDF page."""
    resolved = Path(path).expanduser()
    if not resolved.is_file():
        raise FileNotFoundError(f"no language model at {resolved}: fetch it with `make models`")
    return str(resolved)


@cache
def _model(path: str) -> fasttext.FastText._FastText:
    """Loaded once per probe process, only when it first reads a text layer (about 200 MB)."""
    fasttext.FastText.eprint = lambda *_, **__: None  # fastText warns on load about a deprecated API
    return fasttext.load_model(path)


def _chunks(text: str) -> list[str]:
    out, current = [], ""
    for line in text.splitlines():
        if line := line.strip():
            current = f"{current} {line}" if current else line
            if len(current) >= _CHUNK:
                out.append(current)
                current = ""
    if current:
        if out and len(current) < _CHUNK // 2:
            out[-1] += " " + current
        else:
            out.append(current)
    return out


def _guard(text: str) -> str:
    """Why a layer cannot be text, from its characters alone; "" when it may be."""
    bad = sum((unicodedata.category(c) in ("Cc", "Cn", "Cs") and c not in _ALLOWED_CONTROLS) or c == "�" for c in text)
    if bad >= _BAD_CHARS * max(1, len(text)):
        return "control or undefined characters"
    letters = len(_LETTER.findall(text))
    if sum(map(len, UNSPACED.findall(text))) > 0.3 * letters:
        return ""  # word structure means nothing in scripts written without spaces
    lengths = [n for word in text.split() if (n := len(_LETTER.findall(word)))]
    if lengths and sum(n == 1 for n in lengths) >= _ONE_LETTER * len(lengths):
        return "many one-letter fragments"
    if lengths and sum(n for n in lengths if n >= 25) >= _LONG_WORDS * sum(lengths):
        return "words run together without spaces"
    return ""


def identify(text: str, model_path: str) -> tuple[str, float | None, str]:
    """(language, readability, why it does not read as text). The language is an ISO 639-3 code, or "" when there
    is none; readability is None when there are too few letters to judge; the reason is "" when the layer reads."""
    text = text.replace("￾", "").replace("፡", " ")  # pdfium's soft hyphen; the Ethiopic word space
    if reason := _guard(text):
        return "", 0.0, reason
    weight = real = 0.0
    by_language: dict[str, float] = {}
    for chunk in _chunks(text):
        letters = len(_LETTER.findall(chunk))
        cleaned = _NOT_WORD.sub("", _SPACE.sub(" ", chunk).lower()).strip()
        if letters < 5 or not cleaned:
            continue
        (label,), (p,) = _model(model_path).predict(cleaned, k=1)
        weight += letters
        code = label.removeprefix("__label__").split("_")[0]
        if code != "zxx":
            real += letters * min(1.0, float(p))
            by_language[code] = by_language.get(code, 0.0) + letters * min(1.0, float(p))
    if weight < _MIN_LETTERS:
        return "", None, ""
    readability = round(real / weight, 3)
    top = max(by_language, key=by_language.__getitem__) if by_language else ""
    # a language only when it holds most of the weight: source code, say, reads as text but scatters over languages
    language = top if top and by_language[top] >= 0.5 * real else ""
    return language, readability, "" if readability >= READABLE else "does not read as text in any language"
