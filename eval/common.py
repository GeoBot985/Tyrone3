from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
CACHE_DIR = EVAL_DIR / ".cache"
DB_PATH = EVAL_DIR / "eval.db"
GOLDEN_PATH = EVAL_DIR / "golden.jsonl"
GRADER_PROMPT_PATH = EVAL_DIR / "grader_prompt.txt"

STABLE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "tyrone3.eval.corpus")


def ensure_eval_dirs() -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def rel_corpus_key(path: str | Path) -> str:
    rel = Path(path)
    if rel.is_absolute():
        rel = rel.relative_to(ROOT)
    return rel.as_posix()


def stable_doc_id(path: str | Path) -> str:
    return str(uuid.uuid5(STABLE_NAMESPACE, rel_corpus_key(path)))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


def hash_payload(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_path(name: str, payload: Any) -> Path:
    return CACHE_DIR / f"{name}-{hash_payload(payload)}.json"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@contextlib.contextmanager
def temporary_eval_db(db_path: Path | str) -> Iterator[None]:
    path = str(db_path)
    patch_targets = [
        ("app.config", "RAG_DB_PATH", path),
        ("app.config", "DB_PATH", path),
        ("rag.db", "RAG_DB_PATH", path),
        ("rag.personal_db", "RAG_DB_PATH", path),
        ("app.services.rag_service", "DB_PATH", path),
        ("app.services.ingest_service", "RAG_DB_PATH", path),
        ("app.services.personal_service", "DB_PATH", path),
    ]
    modules: list[tuple[object, str, Any]] = []
    for module_name, attr, value in patch_targets:
        module = importlib.import_module(module_name)
        modules.append((module, attr, getattr(module, attr)))
        setattr(module, attr, value)
    try:
        yield
    finally:
        for module, attr, original in modules:
            setattr(module, attr, original)
