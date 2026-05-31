import io
import os
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import fitz
import pytesseract
from PIL import Image
from app.config import PDF_MIN_TEXT_THRESHOLD_FOR_NO_OCR


def resolve_tesseract_cmd() -> str | None:
    configured = os.getenv("TESSERACT_CMD")
    if configured and os.path.exists(configured):
        return configured

    from_path = shutil.which("tesseract")
    if from_path:
        return from_path

    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in common_paths:
        if candidate and os.path.exists(candidate):
            return candidate

    return None


TESSERACT_CMD = resolve_tesseract_cmd()
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def is_scanned_pdf(text_length: int) -> bool:
    return text_length < PDF_MIN_TEXT_THRESHOLD_FOR_NO_OCR

def render_pdf_page_to_image(pdf_path: str, page_index: int, dpi: int = 200) -> Image.Image:
    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img_data = pix.tobytes("png")
        return Image.open(io.BytesIO(img_data))

class OCRProgressTracker:
    def __init__(self, total_pages: int):
        self.total_pages = total_pages
        self.completed_pages = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            self.completed_pages += 1
            print(f"Ingestion Progress | mode: OCR | pages: {self.completed_pages}/{self.total_pages} complete")

def process_page_ocr(pdf_path: str, page_index: int, tracker: OCRProgressTracker | None = None) -> dict:
    """Returns detailed per-page OCR result"""
    result = {
        "page_index": page_index,
        "text": "",
        "success": False,
        "render_time": 0.0,
        "ocr_time": 0.0
    }
    try:
        t0 = time.time()
        img = render_pdf_page_to_image(pdf_path, page_index)
        t1 = time.time()
        result["render_time"] = t1 - t0

        page_text = pytesseract.image_to_string(img)
        t2 = time.time()
        result["ocr_time"] = t2 - t1

        result["text"] = page_text
        result["success"] = True
    except Exception as e:
        print(f"Error OCRing page {page_index}: {e}")
        result["text"] = f"[Error processing page {page_index+1}]"

    if tracker:
        tracker.increment()

    return result

def run_ocr_parallel(pdf_path: str, max_workers: int = 4) -> tuple[str, int, list[int], dict]:
    with fitz.open(pdf_path) as doc:
        page_count = len(doc)

    failed_pages = []
    results = []
    total_render_time = 0.0
    total_ocr_time = 0.0

    tracker = OCRProgressTracker(page_count)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {executor.submit(process_page_ocr, pdf_path, i, tracker): i for i in range(page_count)}
        for future in future_to_page:
            res = future.result()
            results.append((res["page_index"], res["text"]))
            total_render_time += res["render_time"]
            total_ocr_time += res["ocr_time"]
            if not res["success"]:
                failed_pages.append(res["page_index"] + 1)

    # Deterministic sort
    results.sort(key=lambda x: x[0])

    full_text = ""
    for i, text in results:
        full_text += f"[Page {i+1}]\n{text}\n\n"

    granular_timings = {
        "ocr_render": round(total_render_time, 4),
        "ocr_recognize": round(total_ocr_time, 4)
    }

    return full_text, page_count, failed_pages, granular_timings

def clean_ocr_text(text: str) -> str:
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines)

def extract_text_with_ocr(pdf_path: str, max_workers: int = 4) -> dict:
    """
    Extracts text from PDF using OCR.
    Returns: {
        "text": str,
        "ocr_used": bool,
        "ocr_char_count": int,
        "ocr_page_count": int,
        "failed_pages": list[int],
        "granular_timings": dict,
        "error": str | None
    }
    """
    try:
        # Check if tesseract is available
        resolved_cmd = resolve_tesseract_cmd()
        if resolved_cmd:
            pytesseract.pytesseract.tesseract_cmd = resolved_cmd
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        return {
            "text": "",
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "failed_pages": [],
            "error": "OCR engine not available. Please install Tesseract or set TESSERACT_CMD."
        }
    except Exception as e:
        return {
            "text": "",
            "ocr_used": False,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "failed_pages": [],
            "error": f"OCR initialization failed: {str(e)}"
        }

    try:
        raw_text, page_count, failed_pages, granular_timings = run_ocr_parallel(pdf_path, max_workers=max_workers)
        cleaned_text = clean_ocr_text(raw_text)

        char_count = len(cleaned_text)

        res = {
            "text": cleaned_text,
            "ocr_used": True,
            "ocr_char_count": char_count,
            "ocr_page_count": page_count,
            "failed_pages": failed_pages,
            "granular_timings": granular_timings,
            "error": None
        }

        if char_count < PDF_MIN_TEXT_THRESHOLD_FOR_NO_OCR:
             res["error"] = "OCR failed: insufficient text extracted from scanned PDF."

        return res
    except Exception as e:
        return {
            "text": "",
            "ocr_used": True,
            "ocr_char_count": 0,
            "ocr_page_count": 0,
            "failed_pages": [],
            "error": f"OCR processing failed: {str(e)}"
        }
