# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["httpx>=0.28", "jesteruct"]
#
# [tool.uv.sources]
# jesteruct = { path = "../..", editable = true }
# ///
"""Labeller B: a model of another family than the router's (Gemini) and labeller A's (Claude), through OpenRouter.

    uv run evalset/fresh/label_model.py qualify MODEL [MODEL ...] [--pages N] [--effort E]  # vs evalset/'s labels
    uv run evalset/fresh/label_model.py run MODEL PACKETS [--effort E]                      # label every batch

The chosen labeller: `run openai/gpt-6-luna-pro PACKETS --effort high` (prefix OPENROUTER_API_KEY= to use .env).

It sees exactly what labeller A sees: one packet image and the packet's rubric, and answers with a JSON code and a
short reason. `qualify` renders evalset/'s 98 curated pages the way the router does and compares; `run` appends its
opinions to labels.jsonl as labeller b. Every response is cached under .cache/label_model/, so reruns are free, and
spend is capped from each response's usage.cost: QUALIFY_CAP over all qualification calls, RUN_CAP over the full run.
"""

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import httpx
import labels

HERE = Path(__file__).parent
REPO = HERE.parent.parent
CACHE = HERE / ".cache" / "label_model"
IDS = HERE / ".cache" / "packet_ids.json"
QUALIFY_CAP, RUN_CAP = 0.60, 4.00
WORKERS = 8
PROMPT_VERSION = "b1"
URL = "https://openrouter.ai/api/v1/chat/completions"


def _key() -> str:
    """The OpenRouter key: the environment's when set and non-empty, else the repository's .env."""
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    for line in (REPO / ".env").read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY" and value.strip():
            return value.strip().strip("\"'")
    raise SystemExit("no OPENROUTER_API_KEY in the environment or .env")


def _prompt(rubric: str) -> str:
    return (
        labels.rubric(rubric) + "\nJudge the image only by what it shows."
        " Answer with a JSON object: the code, and why in English in under 15 words."
    )


def request(model: str, rubric: str, jpeg: bytes, effort: str) -> dict:
    schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "enum": list(labels.CODES[rubric])}, "why": {"type": "string"}},
        "required": ["code", "why"],
        "additionalProperties": False,
    }
    image = base64.b64encode(jpeg).decode()
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _prompt(rubric)},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Label this page."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                ],
            },
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "label", "strict": True, "schema": schema}},
        "reasoning": {"effort": effort},
        "provider": {"require_parameters": True},
        "usage": {"include": True},
    }


def _answer(response: dict, rubric: str) -> dict | None:
    """The code and reason in a response, or None. Some models wrap the object in a one-element list."""
    try:
        answer = json.loads(response["choices"][0]["message"]["content"])
        if isinstance(answer, list) and len(answer) == 1:
            answer = answer[0]
        if answer["code"] in labels.CODES[rubric]:
            return {"code": answer["code"], "why": " ".join(str(answer["why"]).split())}
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return None


class CapReached(Exception):
    pass


class Labeller:
    """Cached, spend-capped calls. The ledger of a phase is the cost of every response cached under it."""

    def __init__(self, phase: str, cap: float, effort: str) -> None:
        self.phase, self.cap, self.effort = phase, cap, effort
        self.dir = CACHE / phase
        self.dir.mkdir(parents=True, exist_ok=True)
        self.spent = sum(json.loads(p.read_text())["cost"] for p in self.dir.glob("*/*.json"))
        self.reserved = 0.0
        self.worst: dict[str, float] = {}
        self.lock = threading.Lock()
        self.client = httpx.Client(timeout=180, headers={"Authorization": f"Bearer {_key()}"})

    def label(self, model: str, rubric: str, jpeg: bytes) -> dict:
        """{"code", "why", "cost"}; code is None when the model gave no valid answer in three tries."""
        body = request(model, rubric, jpeg, self.effort)
        digest = hashlib.sha256(json.dumps([PROMPT_VERSION, body], sort_keys=True).encode()).hexdigest()
        cost = 0.0
        for attempt in range(3):
            path = self.dir / model.replace("/", "__") / f"{digest}-{attempt}.json"
            if not path.exists():
                self._call(model, body, path)
            record = json.loads(path.read_text())
            cost += record["cost"]
            if answer := _answer(record["response"], rubric):
                return {**answer, "cost": cost}
        return {"code": None, "why": "", "cost": cost}

    def _call(self, model: str, body: dict, path: Path) -> None:
        with self.lock:  # reserve the dearest call seen so far, so parallel calls cannot overshoot the cap
            guess = self.worst.get(model, 0.02)
            if self.spent + self.reserved + guess > self.cap:
                raise CapReached(f"{self.phase}: ${self.spent:.4f} spent, the next call could pass ${self.cap:.2f}")
            self.reserved += guess
        try:
            for attempt in range(6):
                r = self.client.post(URL, json=body)
                if r.status_code == 200 and not r.json().get("error"):
                    break
                if r.status_code not in (429, 500, 502, 503, 504) and r.status_code != 200:
                    raise RuntimeError(f"{model}: {r.status_code} {r.text[:300]}")
                time.sleep(2 + 4 * attempt)
            else:
                raise RuntimeError(f"{model}: no answer after retries ({r.status_code} {r.text[:200]})")
            data = r.json()
            cost = float((data.get("usage") or {}).get("cost") or 0.0)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "cost": cost, "response": data}))
        finally:
            with self.lock:
                self.reserved -= guess
        with self.lock:
            self.spent += cost
            self.worst[model] = max(self.worst.get(model, 0.0), cost * 1.5)


def _map(fn, items: list) -> list:
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, items))


# ---------------------------------------------------------------- qualification on evalset/


def qualification_pages() -> list[dict]:
    """evalset/'s pages as the router renders them, with the rubric their curated label belongs to; a page that two
    cases share (an OCR-layer copy, a garbled-layer override) is asked once per rubric."""
    from jesteruct.probes import image, pdf

    out, seen = [], set()
    evalset = REPO / "evalset"
    for line in (evalset / "cases.jsonl").read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        case = json.loads(line)
        path = str(evalset / case["file"])
        if path.endswith(".pdf"):
            jpeg = image.render_pdf_page(pdf.page(path, case["page"]))
        else:
            jpeg = image.image_page(path, case["page"])
        rubric = "layout" if set(case["gt"]) <= {"L1", "L2"} else "capture"
        if (rubric, digest := hashlib.sha256(jpeg).hexdigest()) not in seen:
            seen.add((rubric, digest))
            out.append({"id": case["id"], "gt": case["gt"], "rubric": rubric, "jpeg": jpeg})
    return out


def _subset(pages: list[dict], n: int) -> list[dict]:
    """n pages taken round-robin over the (rubric, label) strata, each stratum in a fixed hash order."""
    strata: dict[str, list[dict]] = {}
    for p in sorted(pages, key=lambda p: hashlib.sha256(p["id"].encode()).hexdigest()):
        strata.setdefault(f"{p['rubric']} {'/'.join(p['gt'])}", []).append(p)
    order = [s[i] for i in range(max(map(len, strata.values()))) for s in strata.values() if i < len(s)]
    return order[:n]


def qualify(models: list[str], n: int | None, effort: str) -> None:
    pages = qualification_pages()
    pages = _subset(pages, n) if n else pages
    labeller = Labeller("qualify", QUALIFY_CAP, effort)
    print(f"{len(pages)} pages; ${labeller.spent:.4f} of ${QUALIFY_CAP:.2f} spent before this run")
    for model in models:
        try:
            answers = _map(lambda p, m=model: labeller.label(m, p["rubric"], p["jpeg"]), pages)
        except CapReached as e:
            print(f"{model}: stopped, {e}")
            return
        rows = []
        for p, a in zip(pages, answers, strict=True):
            lanes = labels.CODES[p["rubric"]].get(a["code"], []) if a["code"] else []
            rows.append(
                {
                    "model": model,
                    "id": p["id"],
                    "rubric": p["rubric"],
                    "gt": p["gt"],
                    **a,
                    "agree": bool(lanes) and set(lanes) <= set(p["gt"]),
                    "exact": lanes == p["gt"],
                }
            )
        report = HERE / ".cache" / "qualification" / f"{model.replace('/', '__')}-{effort}.jsonl"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        parts = []
        for rubric in labels.CODES:
            mine = [r for r in rows if r["rubric"] == rubric]
            if mine:
                agree, exact = sum(r["agree"] for r in mine), sum(r["exact"] for r in mine)
                parts.append(f"{rubric} {agree}/{len(mine)} agree, {exact} exact")
        cost = sum(r["cost"] for r in rows) / len(rows)
        failed = sum(r["code"] is None for r in rows)
        print(
            f"{model} ({effort}): {'; '.join(parts)}; ${cost:.5f} a page; {failed} without an answer;"
            f" ${labeller.spent:.4f} spent"
        )


# ---------------------------------------------------------------- the full run


def run(model: str, packets: Path, effort: str) -> None:
    ids = json.loads(IDS.read_text())
    images = sorted(packets.rglob("*.jpg"))
    labeller = Labeller("run", RUN_CAP, effort)
    print(f"{len(images)} images; ${labeller.spent:.4f} of ${RUN_CAP:.2f} spent before this run")

    def one(path: Path) -> dict:
        page = ids[path.stem]
        return {"key": page["key"], **labeller.label(model, page["rubric"], path.read_bytes())}

    try:
        answers = _map(one, images)
    except CapReached as e:
        raise SystemExit(f"stopped: {e}") from None
    missing = [a["key"] for a in answers if a["code"] is None]
    if missing:
        raise SystemExit(f"{len(missing)} pages without a valid answer, for example {missing[:3]}; nothing recorded")
    added = labels.append(
        HERE / "labels.jsonl", ({"key": a["key"], "labeller": "b", "code": a["code"], "why": a["why"]} for a in answers)
    )
    print(f"{added} opinions added as labeller b; ${labeller.spent:.4f} spent in all")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    q = commands.add_parser("qualify", help="agreement with evalset/'s curated labels")
    q.add_argument("models", nargs="+")
    q.add_argument("--pages", type=int, help="a stratified subset of this many pages")
    r = commands.add_parser("run", help="label every batch under a packet directory, as labeller b")
    r.add_argument("model")
    r.add_argument("packets", type=Path)
    for command in (q, r):
        command.add_argument("--effort", default="low", help="reasoning effort (OpenRouter), for example low or none")
    args = parser.parse_args()
    if args.command == "qualify":
        qualify(args.models, args.pages, args.effort)
    else:
        run(args.model, args.packets, args.effort)


if __name__ == "__main__":
    main()
