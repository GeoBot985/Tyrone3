from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_EXCLUDES = {".git", ".venv", "venv", "__pycache__"}


def iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix().lower())


def format_section_header(root: Path, path: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return rel.replace("/", "\\")


def write_consolidated_files(root: Path, output_prefix: str, max_lines: int) -> list[Path]:
    py_files = iter_python_files(root)
    output_paths: list[Path] = []

    part = 1
    line_count = 0
    writer = None

    def open_part(index: int):
        out_path = root / f"{output_prefix}_{index:02d}.txt"
        output_paths.append(out_path)
        return out_path.open("w", encoding="utf-8", newline="\n")

    try:
        writer = open_part(part)
        for file_path in py_files:
            section_header = format_section_header(root, file_path)
            content_lines = file_path.read_text(encoding="utf-8").splitlines()
            section_size = 1 + len(content_lines) + 1

            if line_count > 0 and line_count + section_size > max_lines:
                writer.close()
                part += 1
                line_count = 0
                writer = open_part(part)

            writer.write(section_header + "\n")
            line_count += 1

            for line in content_lines:
                writer.write(line + "\n")
                line_count += 1

            writer.write("\n")
            line_count += 1
    finally:
        if writer is not None and not writer.closed:
            writer.close()

    return output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidate repo Python sources into numbered text files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan. Defaults to the parent of this script.",
    )
    parser.add_argument(
        "--output-prefix",
        default="consolidated_py",
        help="Output file prefix. Defaults to consolidated_py.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=5000,
        help="Maximum lines per output file, including section headers and separators.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    outputs = write_consolidated_files(root, args.output_prefix, args.max_lines)
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
