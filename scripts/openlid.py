# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["fasttext==0.9.3", "httpx>=0.28"]
# ///
"""How the text-layer language model was built: OpenLID-v3, product-quantised from 1.2 GB to 159 MB.

    uv run scripts/openlid.py OUT       # about two minutes and 3 GB of RAM; fastText compiles from source on Linux

Everything uses the file this built on macOS arm64, published as the release openlid-v3-pq1 (`make models` fetches
it): quantising on another platform changes its last bits, which changed the evidence on 7 of 422 dev text layers.
HPLT publishes only the full model, and every process that reads PDF text layers would hold 1.3 GB of it, so it is
quantised without retraining and keeping every word (a 200k-word cut let twice as many garbled layers through).
"""

import hashlib
import sys
import tempfile
from pathlib import Path

import fasttext
import httpx

REVISION = "6b9560483e17e42f48d86cebf22b4b58dffeaa70"
URL = f"https://huggingface.co/HPLT/OpenLID-v3/resolve/{REVISION}/openlid-v3.bin"
SHA256 = "01ec5bbf85975c52673c52b3d8585bc4cc0e4eb4636ad5591467bab56b118821"


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "~/.cache/jesteruct/openlid-v3.ftz").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        full = Path(work) / "openlid-v3.bin"
        digest = hashlib.sha256()
        with httpx.stream("GET", URL, follow_redirects=True, timeout=600) as r, full.open("wb") as fh:
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise SystemExit(f"{URL} does not match its pinned sha256")
        model = fasttext.load_model(str(full))
        model.quantize(cutoff=0, retrain=False, qnorm=True, dsub=2)
        model.save_model(str(out))
    print(f"{out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
