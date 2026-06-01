import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
TEMP_UPLOADS_DIR = os.path.join(PROJECT_ROOT, "temp_uploads")
RAG_UPLOADS_DIR = os.path.join(PROJECT_ROOT, "rag_uploads")
RAG_DB_PATH = os.path.join(PROJECT_ROOT, "rag_v2.db")

# RAG Configuration Constants for Spec 012

# Weights for hybrid ranking
VECTOR_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3

# Search and retrieval limits
CANDIDATE_POOL_SIZE = 500
PER_DOC_CAP = 8
SINGLE_DOC_CANDIDATE_POOL_SIZE = 200
SINGLE_DOC_PER_DOC_CAP = 24
ENUMERATION_TOP_K = 20
ENUMERATION_PER_DOC_CAP = 50
ENUMERATION_LEXICAL_MATCH_CAP = 100

# Database path
DB_PATH = RAG_DB_PATH

# Grounding Defaults (Spec 018)
DEFAULT_MODEL = "granite4:3b"
DEFAULT_MODE = "chat"
AGENT_PURPOSE = "General assistant with chat, document, and personal modes"
DEFAULT_LOCATION = "unknown"  # Can be overridden by env or specific config
DEFAULT_TIMEZONE = None  # If None, use system timezone

# Ingestion Concurrency (Spec 021)
INGESTION_MAX_WORKERS = min(4, os.cpu_count() or 1)
INGESTION_EMBED_MAX_WORKERS = min(4, os.cpu_count() or 1)

# Ingestion Extraction (Spec 022)
ENABLE_MARKITDOWN = True
PDF_MIN_TEXT_THRESHOLD_FOR_NO_OCR = 500

# Upload Support (Spec 023)
SUPPORTED_UPLOAD_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".md",
)
SUPPORTED_UPLOAD_TYPES_DISPLAY = "PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, MD."

# Spreadsheet / Layout Extraction (Spec 024)
SPREADSHEET_HEADER_SCAN_LIMIT = 10
LAYOUT_COLUMN_GAP_THRESHOLD = 8
LAYOUT_SHORT_LINE_MAX = 80

# Document Coverage / Confidence (Spec 025)
DOCUMENT_NARROW_TOP_K = 3
DOCUMENT_COVERAGE_TOP_K = 12
DOCUMENT_MAX_COVERAGE_CHUNKS = 20
DOCUMENT_COVERAGE_SINGLE_DOC_PER_DOC_CAP = 20
DOCUMENT_COVERAGE_MULTI_DOC_PER_DOC_CAP = 8
DOCUMENT_COVERAGE_SCORE_DROP_THRESHOLD = 0.12
DOCUMENT_COVERAGE_CONSECUTIVE_DROP_LIMIT = 2
DOCUMENT_MIN_USEFUL_SCORE = 0.18

CONFIDENCE_HIGH_THRESHOLD = 0.45
CONFIDENCE_MEDIUM_THRESHOLD = 0.25
