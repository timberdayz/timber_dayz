#!/usr/bin/env python3
"""
根目录Markdown白名单检查

允许的根目录MD文件：README.md, CHANGELOG.md, API_CONTRACT.md。
其他MD文件需移动到 docs/。
"""

from pathlib import Path
import sys


ALLOWED = {"README.md", "CHANGELOG.md", "API_CONTRACT.md", "FIELD_DICTIONARY_REFERENCE.md"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    md_files = [p.name for p in root.glob("*.md")]
    violations = [f for f in md_files if f not in ALLOWED]
    if violations:
        print("[ERROR] 根目录存在不允许的Markdown文件:\n  - " + "\n  - ".join(violations))
        print("请将文档移动到 docs/ 或加入白名单策略后再提交。")
        return 1
    print("[OK] 根目录Markdown白名单检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())


