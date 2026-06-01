from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import RAG_DB_PATH
from eval.build_index import build_index
from eval.common import DB_PATH as EVAL_DB_PATH


def seed_demo() -> dict[str, object]:
    os.environ.setdefault("OLLAMA_FAKE", "1")
    result = build_index()
    target_db = Path(RAG_DB_PATH)
    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EVAL_DB_PATH, target_db)
    result["demo_db_path"] = str(target_db)
    result["copied_from_eval_db"] = str(EVAL_DB_PATH)
    return result


def main() -> int:
    result = seed_demo()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    print()
    print("Demo corpus is ready. Start the app with OLLAMA_FAKE=1 for deterministic screenshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
