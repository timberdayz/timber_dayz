#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比较开发与生产 Nginx 配置中的 location 路由差异。
用于部署前确认 dev/prod 路由一致，避免上线后 404 或行为不一致。

使用: python scripts/compare_nginx_configs.py
"""

import re
import sys
from pathlib import Path


def extract_locations(conf_content: str) -> set:
    """从 Nginx 配置中提取 location 的路径或正则（归一化后）。"""
    locations = set()
    # location /path 或 location ~ regex 或 location = /exact
    for m in re.finditer(
        r"location\s+(?:=\s*|~\s*|~\*\s*)?([^\s{]++)",
        conf_content,
    ):
        raw = m.group(1).strip()
        # 去掉注释所在行后面的内容
        if "#" in raw:
            raw = raw.split("#")[0].strip()
        if raw:
            locations.add(raw)
    return locations


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    dev_path = project_root / "nginx" / "nginx.dev.conf"
    prod_path = project_root / "nginx" / "nginx.prod.conf"

    if not dev_path.exists():
        print(f"[WARN] 未找到: {dev_path}")
        return 0
    if not prod_path.exists():
        print(f"[WARN] 未找到: {prod_path}")
        return 0

    dev_loc = extract_locations(dev_path.read_text(encoding="utf-8", errors="ignore"))
    prod_loc = extract_locations(prod_path.read_text(encoding="utf-8", errors="ignore"))

    only_dev = dev_loc - prod_loc
    only_prod = prod_loc - dev_loc

    print("[INFO] Nginx 配置对比 (nginx.dev.conf vs nginx.prod.conf)")
    print(f"  dev  location 数量: {len(dev_loc)}")
    print(f"  prod location 数量: {len(prod_loc)}")

    if only_prod:
        print(f"\n[WARNING] 仅在 prod 中的 location（上线后有，本地无）:")
        for x in sorted(only_prod):
            print(f"  - {x}")
    if only_dev:
        print(f"\n[WARNING] 仅在 dev 中的 location（本地有，prod 无）:")
        for x in sorted(only_dev):
            print(f"  - {x}")

    if not only_dev and not only_prod:
        print("\n[OK] 两边 location 集合一致")
        return 0

    print("\n[提示] 若差异为预期（如 /metabase/ 仅生产），可忽略；否则请同步 nginx 配置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
