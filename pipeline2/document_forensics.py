"""
pipeline2/document_forensics.py
Real file-content forensics for uploaded PDFs/images - F2.2's original design
only inspected caller-declared metadata (dates the API request claimed);
this module actually opens the file bytes and looks for tampering signals.

Two independent, deterministic (non-ML) techniques, chosen for the same
reason as the rest of Pipeline 2 - explicability over black-box modelling:

1. PDF structural analysis (`extract_pdf_structure`): a PDF that was edited
   after being finalized (e.g. after a signature was added, or to change a
   figure) typically gets saved as an INCREMENTAL update rather than a full
   rewrite - the original content stays in the file, followed by a new
   revision appended after it. Each save leaves its own "%%EOF" marker, so
   counting them is a simple, well-known structural tell that something was
   changed post-hoc - independent of (and harder to spoof than) the
   creation/modification *dates* the file merely claims.

2. Error Level Analysis (`error_level_analysis`): re-compresses an image at a
   known JPEG quality and diffs it against the original. A region that was
   pasted in from elsewhere - a signature photographed separately, a copied
   stamp, a swapped photo - carries a different prior compression/noise
   history than the rest of the document, so it lights up differently under
   re-compression than genuine content does.

   Calibrated empirically against synthetic test cases (see
   pipeline2/README.md for the numbers, and how they were produced): neither
   region size nor raw intensity alone reliably separates a pasted signature
   from an ordinary line of text - a long, all-caps title can span MORE
   blocks than a small signature, and text edges are often noisier
   per-pixel than a clean pasted graphic. What did separate them: severity =
   blocks x mean_error. Regions are ranked by that combined score rather
   than passed through a single hard threshold, and only ones that stand out
   from the document's OWN other candidate regions (not a fixed universal
   number) are flagged - this is a ranking aid for a human reviewer, not a
   fraud verdict; the heatmap/bboxes are meant to be looked at, not trusted
   blindly.

   Consequence: this technique is NOT reliable for catching a single edited
   digit or word typed directly into the document (e.g. "5000" retouched to
   read "50000") - there's no separate compression history to detect in
   that case. That kind of tampering is better caught by the PDF structural
   check above (if it happened by editing a PDF) or by F2.3's Isolation
   Forest flagging the resulting amount as statistically implausible.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageChops

try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

try:
    import pymupdf
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False


# ELA tuning constants (see module docstring for why these values)
ELA_JPEG_QUALITY = 90
ELA_HOT_MULTIPLIER = 1.6      # a block counts as "hot" above p90 * this - candidate generation only
ELA_MIN_BLOCK_PX = 16         # block grid adapts to image size, never smaller than this
ELA_MIN_COMPONENT_BLOCKS = 2  # filters lone-block JPEG DCT-grid noise, nothing more
ELA_OUTLIER_SEVERITY_RATIO = 1.35  # a region is "flagged" if its severity exceeds this x the median


@dataclass
class SuspiciousRegion:
    bbox: tuple  # (x0, y0, x1, y1) in pixels
    blocks: int
    mean_error: float

    @property
    def severity(self) -> float:
        """Combined size x intensity score used for ranking - see module
        docstring for why neither factor alone is a reliable discriminator."""
        return self.blocks * self.mean_error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": list(self.bbox), "blocks": self.blocks,
            "mean_error": round(self.mean_error, 3), "severity": round(self.severity, 3),
        }


@dataclass
class ElaResult:
    flagged: bool
    regions: List[SuspiciousRegion] = field(default_factory=list)
    p90_baseline: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flagged": self.flagged,
            "regions": [r.to_dict() for r in self.regions],
            "p90_baseline": round(self.p90_baseline, 4),
        }


@dataclass
class PdfStructureResult:
    incremental_update_count: int
    producer: Optional[str]
    creator: Optional[str]
    creation_date: Optional[str]
    modification_date: Optional[str]
    page_count: int

    @property
    def edited_after_finalization(self) -> bool:
        """More than one save (i.e. more than one %%EOF) means the PDF was
        re-saved at least once after its first version existed."""
        return self.incremental_update_count > 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incremental_update_count": self.incremental_update_count,
            "edited_after_finalization": self.edited_after_finalization,
            "producer": self.producer,
            "creator": self.creator,
            "creation_date": self.creation_date,
            "modification_date": self.modification_date,
            "page_count": self.page_count,
        }


@dataclass
class DocumentForensicsResult:
    flags: List[str] = field(default_factory=list)
    pdf_structure: Optional[PdfStructureResult] = None
    ela: Optional[ElaResult] = None
    error: Optional[str] = None
    # Real dates extracted from the file itself (PDF metadata or image EXIF) -
    # for F2.2 to compare against declared_date instead of trusting a
    # caller-supplied claim. None when the file simply doesn't carry them.
    real_created_at: Optional[str] = None
    real_modified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flags": self.flags,
            "pdf_structure": self.pdf_structure.to_dict() if self.pdf_structure else None,
            "ela": self.ela.to_dict() if self.ela else None,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# PDF structural analysis
# ---------------------------------------------------------------------------

def count_incremental_updates(pdf_bytes: bytes) -> int:
    """Counts '%%EOF' markers in the raw PDF bytes. Each full or incremental
    save appends its own trailer ending in %%EOF, so more than one means the
    file was saved more than once - i.e. edited after its first version."""
    return pdf_bytes.count(b"%%EOF")


def extract_pdf_structure(pdf_bytes: bytes) -> PdfStructureResult:
    if not _PYPDF_AVAILABLE:
        raise RuntimeError("pypdf is not installed")

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    meta = reader.metadata or {}

    return PdfStructureResult(
        incremental_update_count=count_incremental_updates(pdf_bytes),
        producer=str(meta.producer) if meta.producer else None,
        creator=str(meta.creator) if meta.creator else None,
        creation_date=str(meta.creation_date) if meta.creation_date else None,
        modification_date=str(meta.modification_date) if meta.modification_date else None,
        page_count=len(reader.pages),
    )


def render_pdf_pages_to_images(pdf_bytes: bytes, max_pages: int = 3, dpi: int = 150) -> List[Image.Image]:
    if not _PYMUPDF_AVAILABLE:
        raise RuntimeError("pymupdf is not installed")

    images = []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        for page_index in range(min(max_pages, doc.page_count)):
            pix = doc[page_index].get_pixmap(matrix=matrix)
            images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    finally:
        doc.close()
    return images


# ---------------------------------------------------------------------------
# Error Level Analysis
# ---------------------------------------------------------------------------

def error_level_analysis(
    image: Image.Image,
    quality: int = ELA_JPEG_QUALITY,
    hot_multiplier: float = ELA_HOT_MULTIPLIER,
    min_component_blocks: int = ELA_MIN_COMPONENT_BLOCKS,
    outlier_severity_ratio: float = ELA_OUTLIER_SEVERITY_RATIO,
) -> ElaResult:
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")

    diff = ImageChops.difference(rgb, recompressed)
    gray = np.asarray(diff).astype(np.float32).mean(axis=2)

    w, h = rgb.size
    block = max(ELA_MIN_BLOCK_PX, min(w, h) // 40)
    ny, nx = h // block, w // block
    if ny < 2 or nx < 2:
        return ElaResult(flagged=False, regions=[], p90_baseline=0.0)

    grid = np.array([
        [gray[gy * block:(gy + 1) * block, gx * block:(gx + 1) * block].mean() for gx in range(nx)]
        for gy in range(ny)
    ])
    p90 = float(np.percentile(grid, 90))
    hot = grid > (p90 * hot_multiplier) if p90 > 0 else np.zeros_like(grid, dtype=bool)

    regions = _connected_hot_regions(hot, grid, block, min_component_blocks)
    flagged = _flag_severity_outliers(regions, outlier_severity_ratio)
    regions.sort(key=lambda r: r.severity, reverse=True)
    return ElaResult(flagged=flagged, regions=regions, p90_baseline=p90)


def _flag_severity_outliers(regions: List[SuspiciousRegion], ratio: float) -> bool:
    """A region is worth showing an inspector when it stands out from this
    document's OWN other candidate regions, not against a fixed universal
    number (documents vary too much in text density/font/DPI for one
    constant to generalize). Needs at least 2 regions to have a baseline to
    compare against - a lone candidate can't be judged relative to nothing."""
    if len(regions) < 2:
        return False
    severities = sorted((r.severity for r in regions), reverse=True)
    median = float(np.median(severities))
    if median <= 0:
        return False
    return severities[0] > median * ratio


def _connected_hot_regions(
    hot: np.ndarray, grid: np.ndarray, block: int, min_blocks: int
) -> List[SuspiciousRegion]:
    """4-connected components of `hot` blocks, filtered only to drop
    lone-block JPEG DCT-grid noise (min_blocks=2 by default) - real
    size/intensity discrimination happens afterwards via severity ranking,
    not here (see module docstring)."""
    ny, nx = hot.shape
    visited = np.zeros_like(hot, dtype=bool)
    regions: List[SuspiciousRegion] = []

    for gy in range(ny):
        for gx in range(nx):
            if not hot[gy, gx] or visited[gy, gx]:
                continue
            stack = [(gy, gx)]
            visited[gy, gx] = True
            component = []
            while stack:
                cy, cx = stack.pop()
                component.append((cy, cx))
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny_, nx_ = cy + dy, cx + dx
                    if 0 <= ny_ < ny and 0 <= nx_ < nx and hot[ny_, nx_] and not visited[ny_, nx_]:
                        visited[ny_, nx_] = True
                        stack.append((ny_, nx_))

            if len(component) >= min_blocks:
                ys = [c[0] for c in component]
                xs = [c[1] for c in component]
                mean_error = float(np.mean([grid[y, x] for y, x in component]))
                regions.append(SuspiciousRegion(
                    bbox=(min(xs) * block, min(ys) * block, (max(xs) + 1) * block, (max(ys) + 1) * block),
                    blocks=len(component),
                    mean_error=mean_error,
                ))

    return regions


# ---------------------------------------------------------------------------
# Image metadata (EXIF)
# ---------------------------------------------------------------------------

_EXIF_DATETIME_ORIGINAL_TAG = 36867  # DateTimeOriginal
_EXIF_DATETIME_TAG = 306             # DateTime (modification)


def extract_image_exif_dates(image: Image.Image) -> Dict[str, Optional[str]]:
    """Best-effort EXIF capture/modification date extraction. A phone photo
    of a paper document usually carries these; a downloaded/re-exported
    image (or one stripped by messaging-app compression) usually doesn't -
    absence isn't itself proof of anything, it just means F2.2 can't check
    dates it doesn't have (same honest "metadata_dates_missing" path as
    always, not a fabricated date)."""
    try:
        exif = image.getexif()
    except Exception:
        return {"created_at": None, "modified_at": None}

    def _fmt(tag: int) -> Optional[str]:
        raw = exif.get(tag)
        if not raw:
            return None
        # EXIF datetimes are "YYYY:MM:DD HH:MM:SS" - normalize the date separators
        try:
            date_part, time_part = raw.split(" ", 1)
            return f"{date_part.replace(':', '-')} {time_part}"
        except ValueError:
            return None

    return {
        "created_at": _fmt(_EXIF_DATETIME_ORIGINAL_TAG),
        "modified_at": _fmt(_EXIF_DATETIME_TAG) or _fmt(_EXIF_DATETIME_ORIGINAL_TAG),
    }


# ---------------------------------------------------------------------------
# Entry point: dispatch by file type
# ---------------------------------------------------------------------------

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


def analyze_document_bytes(file_bytes: bytes, filename: str) -> DocumentForensicsResult:
    """Top-level entry point: detects PDF vs image and runs the applicable
    checks. Never raises - forensic analysis is an enrichment on top of the
    existing metadata-based F2.2 check, not a hard dependency (same
    never-a-single-point-of-failure principle as the GNN in F2.7)."""
    flags: List[str] = []
    is_pdf = filename.lower().endswith(".pdf") or file_bytes[:5] == b"%PDF-"

    try:
        if is_pdf:
            structure = extract_pdf_structure(file_bytes)
            if structure.edited_after_finalization:
                flags.append("pdf_edited_after_finalization")

            ela_result = None
            try:
                pages = render_pdf_pages_to_images(file_bytes, max_pages=1)
                if pages:
                    ela_result = error_level_analysis(pages[0])
                    if ela_result.flagged:
                        flags.append("pasted_content_suspected")
            except RuntimeError:
                pass  # pymupdf unavailable - PDF structure check alone still ran

            return DocumentForensicsResult(
                flags=flags, pdf_structure=structure, ela=ela_result,
                real_created_at=structure.creation_date,
                real_modified_at=structure.modification_date,
            )

        # Treat anything else as an image
        image = Image.open(io.BytesIO(file_bytes))
        ela_result = error_level_analysis(image)
        if ela_result.flagged:
            flags.append("pasted_content_suspected")
        exif_dates = extract_image_exif_dates(image)
        return DocumentForensicsResult(
            flags=flags, ela=ela_result,
            real_created_at=exif_dates["created_at"],
            real_modified_at=exif_dates["modified_at"],
        )

    except Exception as exc:
        return DocumentForensicsResult(flags=[], error=f"forensics analysis failed: {exc}")
