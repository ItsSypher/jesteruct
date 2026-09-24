"""Contracts shared by every stage: intake → probes → decisions → manifest (the public output, schema v1)."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Lane = Literal["L0", "L1", "L2", "L3", "L4", "L5", "LQ", "LH"]
LANES: dict[str, str] = {
    "L0": "native office or text format",
    "L1": "born-digital, simple",
    "L2": "born-digital, complex (tables, math, code, columns)",
    "L3": "clean scan or image",
    "L4": "degraded scan, camera photo or fax",
    "L5": "mostly handwritten",
    "LQ": "quarantine",
    "LH": "human review",
}
# Capability order for the processing ladder; LQ and LH sit outside it.
LANE_RANK: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}

DocKind = Literal["pdf", "image", "office", "text", "email", "archive", "unknown"]


class Doc(BaseModel):
    """One routable document. Containers expand into child Docs that point at their parent."""

    sha256: str
    name: str
    path: str  # local file with this document's bytes
    kind: DocKind
    mime: str
    size: int
    page_count: int = 0
    parent_sha: str | None = None
    quarantine: str | None = None  # reason code when intake rejects the document


class PageRef(BaseModel):
    doc_path: str
    index: int
    kind: Literal["pdf", "image"]


class TextStats(BaseModel):
    chars: int = 0
    cid_share: float = 0.0
    odd_char_share: float = 0.0
    short_token_share: float = 0.0
    common_word_share: float = 0.0
    script: dict[str, float] = Field(default_factory=dict)


class ImageQuality(BaseModel):
    sharpness: float
    contrast: float
    noise: float
    bilevel_share: float
    background_mean: float
    border_mean: float
    border_std: float
    colour: float


class PdfFacts(BaseModel):
    image_coverage: float
    invisible_text: bool
    producer: str = ""
    math_font: bool = False
    mono_font: bool = False
    columns: Literal[1, 2] | None = None  # None when there is too little text to tell


class LayoutFacts(BaseModel):
    """Regions a layout model found on the page image."""

    model: str
    counts: dict[str, int] = Field(default_factory=dict)  # regions per label
    area: dict[str, float] = Field(default_factory=dict)  # share of the page area per label, at most 1
    columns: Literal[1, 2] | None = None  # from the text regions; None when there are none


class OcrResult(BaseModel):
    text: str
    confidence: float
    lines: int
    backend: str


class PageEvidence(BaseModel):
    """Everything the cheap probes measured on one page."""

    ref: PageRef
    image: ImageQuality
    pdf: PdfFacts | None = None
    layout: LayoutFacts | None = None  # None when the layout model failed
    text: str = ""  # embedded text layer (PDF) or OCR text (image), capped against hostile files
    text_stats: TextStats = Field(default_factory=TextStats)
    ocr: OcrResult | None = None  # fresh OCR, run when the text layer is missing or not trusted
    ocr_stats: TextStats | None = None
    ocr_agreement: float | None = None  # word overlap of a PDF text layer with the fresh OCR text


class VisionFacts(BaseModel):
    capture: str
    legibility: str
    handwriting: str
    content: dict[str, bool]
    script: str


class PageRoute(BaseModel):
    index: int
    lane: Lane
    candidate_lane: Lane  # the policy's lane before review or quarantine overrides
    path_p: float  # product of the answers along the policy path
    answers: dict[str, float] = Field(default_factory=dict)  # raw Jev answers, kept for calibration
    modifiers: list[str] = Field(default_factory=list)
    degradation: float | None = None
    continuation: float | None = None
    vision: VisionFacts | None = None
    reasons: list[str] = Field(default_factory=list)
    thumb_key: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)


class Segment(BaseModel):
    start: int
    end: int  # inclusive
    lane: Lane
    modifiers: list[str] = Field(default_factory=list)


class Versions(BaseModel):
    router: str
    evidence: str
    policy: str
    questions: str  # hash of the Jev question set
    jev_model: str
    jev_served: str | None = None
    vision_model: str
    ocr_backend: str


class Manifest(BaseModel):
    schema_version: Literal["1"] = "1"
    doc: Doc
    route_key: str
    versions: Versions
    pages: list[PageRoute]
    segments: list[Segment]
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


JobStatus = Literal["queued", "running", "done", "failed"]


class DocEntry(BaseModel):
    doc_sha: str
    name: str
    parent_sha: str | None = None
    manifest_key: str
    lanes: dict[str, int] = Field(default_factory=dict)  # page count per lane


class JobIndex(BaseModel):
    """What a job produced: one manifest per (child) document."""

    job_id: str
    status: JobStatus
    input_key: str
    documents: list[DocEntry] = Field(default_factory=list)
    error: str | None = None
    deliveries: int = 0
