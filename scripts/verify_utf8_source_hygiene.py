"""
Verify UTF-8 source hygiene for changed text files.

By default, this script scans repository-tracked files changed from HEAD.
Specific files or directories can be passed as positional arguments.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEXT_EXTENSIONS = {
    ".vue",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".html",
    ".py",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
}
STRICT_TEMPLATE_EXTENSIONS = {".vue", ".html"}
KNOWN_MOJIBAKE_TOKENS = [
    "鎵",
    "鍙",
    "閲",
    "歿{",
    "?/div>",
    "?/span>",
    "?/el-",
    "?/p>",
]


def iter_changed_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[Path] = []
    for raw_line in result.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        path = PROJECT_ROOT / raw_line
        if path.is_file():
            files.append(path)
    return files


def iter_explicit_paths(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in args:
        target = (PROJECT_ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if target.is_file():
            files.append(target)
            continue
        if target.is_dir():
            for path in target.rglob("*"):
                if path.is_file():
                    files.append(path)
    return files


def should_scan(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def is_known_legacy_doc(path: Path, text: str) -> bool:
    if "docs" not in path.parts:
        return False
    marker = "legacy reference with encoding damage"
    return marker in text.lower()


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"not valid UTF-8: {exc}")
        return errors

    if "\ufffd" in text:
        errors.append("contains Unicode replacement character U+FFFD")

    if is_known_legacy_doc(path, text):
        return errors

    if path.suffix.lower() in STRICT_TEMPLATE_EXTENSIONS:
        for token in KNOWN_MOJIBAKE_TOKENS:
            if token in text:
                errors.append(f'contains mojibake token "{token}"')

    return errors


def main(argv: list[str]) -> int:
    explicit_args = argv[1:]
    candidates = iter_explicit_paths(explicit_args) if explicit_args else iter_changed_files()
    scan_targets = sorted({path for path in candidates if should_scan(path)})

    if not scan_targets:
        print("[PASS] No text files require UTF-8 hygiene checks.")
        return 0

    failures: list[tuple[Path, list[str]]] = []
    for path in scan_targets:
        errors = validate_file(path)
        if errors:
            failures.append((path, errors))

    if failures:
        print("[FAIL] UTF-8 source hygiene check failed:")
        for path, errors in failures:
            rel = path.relative_to(PROJECT_ROOT)
            print(f"  - {rel}")
            for error in errors:
                print(f"    * {error}")
        return 1

    print(f"[PASS] UTF-8 source hygiene verified for {len(scan_targets)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
