"""
pipeline2/ocr.py — Best-effort text extraction from uploaded images (photos
of invoices/factures, including handwritten ones) via Tesseract OCR.

Why this exists: /documents/intake could already pull text out of PDFs
(pymupdf's text layer), but a PHOTOGRAPHED document - which is exactly what
a handwritten facture is - has no text layer at all, so it always got zero
text and had to be matched to a dossier by filename alone. This closes that
gap using local OCR (no new API key/provider needed).

Honesty about what this can and can't do (same principle as the ELA
analysis in document_forensics.py - don't overclaim a heuristic's
reliability): Tesseract is a printed-text OCR engine. It reads printed
invoice fields (business name, printed amounts, dates) reasonably well.
Genuine cursive handwriting is NOT reliably recognized by Tesseract or any
free local OCR engine - a handwritten amount may come out wrong or empty.
This module is a real improvement (photographed PRINTED invoices, and the
printed portions of a mixed printed/handwritten form, now get read at all,
where before they got nothing), not a claim that handwriting itself becomes
reliably machine-readable. If handwriting recognition needs to be reliable,
that requires a vision-capable LLM, which is not available on the current
Groq account (checked its /v1/models list directly: text-chat, Whisper STT
and Orpheus TTS models only, no image-input model).

Degrades to an empty string on any failure (Tesseract not installed on a
given machine, language data missing, corrupt image, etc.) - OCR is an
enrichment on top of filename-based matching, never a hard dependency.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

_LOCAL_TESSDATA = Path(__file__).resolve().parent / "tessdata"
_WINDOWS_DEFAULT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

_configured = False
_available = False


def _configure() -> bool:
    """Locates the tesseract binary once per process. Returns whether OCR is
    usable at all on this machine."""
    global _configured, _available
    if _configured:
        return _available
    _configured = True

    try:
        import pytesseract
    except ImportError:
        logger.info("OCR desactivee : le paquet pytesseract n'est pas installe.")
        return False

    exe = shutil.which("tesseract") or (str(_WINDOWS_DEFAULT_EXE) if _WINDOWS_DEFAULT_EXE.exists() else None)
    if exe is None:
        logger.info(
            "OCR desactivee : le moteur Tesseract n'est pas installe sur cette machine "
            "(voir pipeline2/README.md pour l'installer)."
        )
        return False

    pytesseract.pytesseract.tesseract_cmd = exe
    _available = True
    return True


def _tessdata_config() -> str:
    """Points Tesseract at this repo's bundled language data (fra+ara+eng) if
    present, so results don't depend on what happens to be installed
    system-wide on a given machine."""
    if _LOCAL_TESSDATA.is_dir():
        return f"--tessdata-dir {_LOCAL_TESSDATA}"
    return ""


def extract_text_from_image(image: Image.Image) -> str:
    """Best-effort OCR of an image. Empty string if OCR isn't usable or
    nothing was recognized - never raises."""
    if not _configure():
        return ""
    try:
        import pytesseract

        return pytesseract.image_to_string(
            image.convert("RGB"), lang="fra+eng+ara", config=_tessdata_config()
        ).strip()
    except Exception as exc:
        logger.warning("OCR: echec de la reconnaissance de texte (%s).", exc)
        return ""


def is_available() -> bool:
    return _configure()
