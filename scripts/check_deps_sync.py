"""Fail if pyproject.toml runtime deps and requirements.txt drift apart.

pyproject.toml declares the runtime dependency set (mostly unpinned), while
requirements.txt pins those same packages for reproducible Docker builds. This
check compares the normalized package *names* so a pin/decl divergence or a
forgotten add/remove is caught by the release gate instead of shipping silently.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _normalize(name: str) -> str:
    return re.split(r"[<>=!\[]", name.strip(), maxsplit=1)[0].strip().lower().replace("_", "-")


def _pyproject_runtime_deps() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {_normalize(line) for line in data["project"].get("dependencies", []) if line.strip()}


def _requirements_names() -> set[str]:
    names: set[str] = set()
    for raw in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.add(_normalize(line))
    return names


def main() -> int:
    py = _pyproject_runtime_deps()
    req = _requirements_names()
    missing_from_req = sorted(py - req)
    extra_in_req = sorted(req - py)
    if not missing_from_req and not extra_in_req:
        print("dependencies in sync")
        return 0
    print("dependency drift detected:")
    if missing_from_req:
        print("  in pyproject.toml but missing from requirements.txt:")
        for name in missing_from_req:
            print(f"    - {name}")
    if extra_in_req:
        print("  in requirements.txt but missing from pyproject.toml:")
        for name in extra_in_req:
            print(f"    - {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
