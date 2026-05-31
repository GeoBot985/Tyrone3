import pytest
from app.utils.token_utils import estimate_tokens

def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0

def test_estimate_tokens_short():
    assert estimate_tokens("abc") == 1 # ceil(3/4) = 1
    assert estimate_tokens("abcd") == 1 # ceil(4/4) = 1

def test_estimate_tokens_long():
    assert estimate_tokens("a" * 10) == 3 # ceil(10/4) = 3
    assert estimate_tokens("a" * 400) == 100 # ceil(400/4) = 100
