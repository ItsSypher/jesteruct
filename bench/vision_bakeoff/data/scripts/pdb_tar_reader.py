"""
Byte-range reader for the PureDocBench split tar archive on Hugging Face.

The full release (zhihengli-casia/puredocbench) ships only as a ~35 GiB tar
split into 10 parts on the Hub, with no per-file access and no dataset
viewer/parquet export. Rather than downloading the whole archive (which would
blow the <3GB total-download budget), this module treats the 10 parts as one
continuous byte stream and walks the tar structure using small HTTP Range
requests:

  - For entries we don't need, we only fetch the 512-byte USTAR header,
    compute the (padded) data size from it, and jump the cursor forward
    WITHOUT fetching the entry's data.
  - For entries we do need (a handful of GT jsons + ~24 page images), we
    issue one Range GET for exactly that entry's data.

This keeps total bytes transferred close to "what we actually use" instead
of "the whole archive", at the cost of many small sequential requests.
"""
from __future__ import annotations

import requests

BASE = "https://huggingface.co/datasets/zhihengli-casia/puredocbench/resolve/main/"

PARTS = [
    ("pdb_full.tar.part-000", 4089446400),
    ("pdb_full.tar.part-001", 4089446400),
    ("pdb_full.tar.part-002", 4089446400),
    ("pdb_full.tar.part-003", 4089446400),
    ("pdb_full.tar.part-004", 4089446400),
    ("pdb_full.tar.part-005", 4089446400),
    ("pdb_full.tar.part-006", 4089446400),
    ("pdb_full.tar.part-007", 4089446400),
    ("pdb_full.tar.part-008", 4089446400),
    ("pdb_full.tar.part-009", 802099200),
]


class RemoteSplitTar:
    def __init__(self):
        self.sess = requests.Session()
        self._cum = []
        total = 0
        for name, size in PARTS:
            self._cum.append((total, total + size, name))
            total += size
        self.total_size = total
        self.bytes_fetched = 0
        self.requests_made = 0

    def fetch_range(self, start: int, length: int) -> bytes:
        if length <= 0:
            return b""
        out = bytearray()
        pos = start
        remaining = length
        for s, e, name in self._cum:
            if remaining <= 0:
                break
            if pos >= e:
                continue
            if pos < s:
                break  # shouldn't happen; parts are contiguous
            local_start = pos - s
            local_len = min(remaining, e - pos)
            r = self.sess.get(
                BASE + name,
                headers={"Range": f"bytes={local_start}-{local_start + local_len - 1}"},
                timeout=60,
            )
            r.raise_for_status()
            out += r.content
            self.bytes_fetched += len(r.content)
            self.requests_made += 1
            pos += local_len
            remaining -= local_len
        return bytes(out)


def parse_octal(field: bytes) -> int:
    field = field.split(b"\0")[0].strip()
    if not field:
        return 0
    try:
        return int(field, 8)
    except ValueError:
        return 0


class TarWalker:
    """Sequential walker over the remote split tar, header-skip aware."""

    def __init__(self, tar: RemoteSplitTar):
        self.tar = tar
        self.cursor = 0
        self._pending_long_name = None

    def next_entry(self):
        """Return (name, size, data_offset) for the next entry, or None at EOF."""
        while True:
            hdr = self.tar.fetch_range(self.cursor, 512)
            if len(hdr) < 512 or hdr == b"\0" * 512:
                return None
            name_field = hdr[0:100].split(b"\0")[0].decode("utf-8", "replace")
            size = parse_octal(hdr[124:136])
            typeflag = hdr[156:157]
            prefix = hdr[345:500].split(b"\0")[0].decode("utf-8", "replace")
            data_offset = self.cursor + 512
            padded = ((size + 511) // 512) * 512
            self.cursor = data_offset + padded

            if typeflag == b"L":
                # GNU long-name entry: data is the real name of the *next* entry.
                data = self.tar.fetch_range(data_offset, size)
                self._pending_long_name = data.split(b"\0")[0].decode("utf-8", "replace")
                continue

            if self._pending_long_name is not None:
                name = self._pending_long_name
                self._pending_long_name = None
            else:
                name = (prefix + name_field) if prefix else name_field

            if typeflag in (b"5",):  # directory
                continue
            if typeflag not in (b"0", b"\0", b""):
                continue

            return (name, size, data_offset)

    def skip_to_prefix(self, prefix: str, stop_before: str | None = None):
        """Advance past entries until an entry name starts with `prefix`.

        Returns the entry (name, size, data_offset) that first matches, without
        consuming further entries. Raises RuntimeError if `stop_before` prefix
        is hit first (safety net against overshooting).
        """
        while True:
            save_cursor = self.cursor
            entry = self.next_entry()
            if entry is None:
                raise RuntimeError(f"EOF before finding prefix {prefix!r}")
            name = entry[0]
            if name.startswith(prefix):
                self.cursor = save_cursor  # rewind so caller can re-read via next_entry
                return entry
            if stop_before and name.startswith(stop_before):
                raise RuntimeError(f"hit stop prefix {stop_before!r} before {prefix!r}")

    def fetch_data(self, entry) -> bytes:
        _, size, offset = entry
        return self.tar.fetch_range(offset, size)
