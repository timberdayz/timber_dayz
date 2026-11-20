"""校验 sea-metrics-language skill 两份副本字节一致。

律 3 要求派生层口径机器可验证；"哪一份是正本"靠人读文档无法验证，
因此把"两份必须一致"固化成脚本。

Usage:
    python scripts/verify_team_skills_sync.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    (
        REPO_ROOT / "docs" / "team-skills" / "sea-metrics-language",
        REPO_ROOT / "team-skills-bundle" / "sea-metrics-language",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    problems: list[str] = []
    for left, right in PAIRS:
        left_files = {p.relative_to(left).as_posix() for p in left.rglob("*") if p.is_file()}
        right_files = {p.relative_to(right).as_posix() for p in right.rglob("*") if p.is_file()}
        for missing in sorted(left_files - right_files):
            problems.append(f"missing in {right}: {missing}")
        for missing in sorted(right_files - left_files):
            problems.append(f"missing in {left}: {missing}")
        for rel in sorted(left_files & right_files):
            lh = _sha256(left / rel)
            rh = _sha256(right / rel)
            if lh != rh:
                problems.append(f"content differs: {rel} ({lh[:8]} != {rh[:8]})")
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        return 1
    print("[OK] sea-metrics-language 两份副本一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
