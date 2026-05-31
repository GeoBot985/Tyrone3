import math

def estimate_tokens(text: str | None) -> int:
    """
    Simple character-based token estimation.
    estimated_tokens = ceil(len(text) / 4)
    If text is empty or None, return 0.
    """
    if not text:
        return 0
    return math.ceil(len(text) / 4)
