import sys
import os

# Add Demo5 root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
demo5_root = os.path.abspath(os.path.join(current_dir, "../"))
if demo5_root not in sys.path:
    sys.path.append(demo5_root)

from rag.ocr_service import is_scanned_pdf, clean_ocr_text

def test_is_scanned_pdf():
    assert is_scanned_pdf(100) == True
    assert is_scanned_pdf(600) == False
    print("test_is_scanned_pdf passed")

def test_clean_ocr_text():
    raw_text = "  line 1  \n\n  line 2  \n  "
    cleaned = clean_ocr_text(raw_text)
    assert cleaned == "line 1\nline 2"
    print("test_clean_ocr_text passed")

if __name__ == "__main__":
    test_is_scanned_pdf()
    test_clean_ocr_text()
