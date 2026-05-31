import os


def extract_with_markitdown(path: str) -> dict:
    """
    Thin wrapper around MarkItDown extraction.

    Returns:
    {
        "text": str,
        "success": bool,
        "error": str | None,
        "file_type": str,
        "method": "markitdown",
    }
    """
    ext = os.path.splitext(path)[1].lower()
    file_type = ext.lstrip(".") or "unknown"

    if not os.path.exists(path):
        return {
            "text": "",
            "success": False,
            "error": f"File not found: {path}",
            "file_type": file_type,
            "method": "markitdown",
        }

    try:
        from markitdown import MarkItDown
    except Exception as exc:
        return {
            "text": "",
            "success": False,
            "error": f"MarkItDown is unavailable: {exc}",
            "file_type": file_type,
            "method": "markitdown",
        }

    try:
        result = MarkItDown().convert(path)
        text = getattr(result, "text_content", "") or ""
        return {
            "text": text,
            "success": True,
            "error": None,
            "file_type": file_type,
            "method": "markitdown",
        }
    except Exception as exc:
        return {
            "text": "",
            "success": False,
            "error": str(exc),
            "file_type": file_type,
            "method": "markitdown",
        }
