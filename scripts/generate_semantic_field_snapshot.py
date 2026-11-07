#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成前端用的「标准字段定义快照」。

背景
----
批次 D 的目标是让标准字段定义**只有一份**(后端
:mod:`backend.services.semantic_field_registry`), 前端不再抄。

但前端在浏览器里需要**同步**拿到这份定义(渲染下拉框、查别名索引),
而接口是异步的 ⇒ 这里生成一份**快照**作为:

1. 前端的**兜底**数据(接口还没回来 / 接口挂了, 页面不至于空白);
2. node 端脚本测试的 fixture;
3. 前后端归一化口径的锁链(快照里带 ``normalization_samples``)。

这份快照是**生成物**, 不是人手维护的副本 ——
``backend/tests/data_pipeline/test_semantic_translation_guardrails.py``
会重新生成一遍并逐字段比对, 漂了就红。

用法::

    python scripts/generate_semantic_field_snapshot.py            # 写入快照
    python scripts/generate_semantic_field_snapshot.py --check    # 只校验漂移
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SNAPSHOT_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "data_platform"
    / "utils"
    / "semanticFieldRegistrySnapshot.js"
)


def _js_header(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "/**\n"
        " * 标准字段定义快照 —— **自动生成, 请勿手工编辑**。\n"
        " *\n"
        " * 生成命令::\n"
        " *\n"
        " *     python scripts/generate_semantic_field_snapshot.py\n"
        " *\n"
        " * 漂移守护::\n"
        " *\n"
        " *     backend/tests/data_pipeline/test_semantic_translation_guardrails.py\n"
        " *\n"
        " * [*] 批次 D: 这份快照以前是前端 ``headerBindings.js`` 里手抄的 360 行,\n"
        " *     已经和后端漂了(缺 domain/required、label 与别名对不上)。\n"
        " *     现在它是**生成物**, 后端是唯一口径。\n"
        " */\n"
        "export const SEMANTIC_FIELD_REGISTRY_SNAPSHOT = " + body + "\n"
        "\n"
        "export default SEMANTIC_FIELD_REGISTRY_SNAPSHOT\n"
    )


def build_payload() -> Dict[str, Any]:
    from backend.services.semantic_field_registry import build_semantic_field_snapshot_payload

    payload = build_semantic_field_snapshot_payload()
    payload["generated_at"] = ""
    payload["generated_by"] = "scripts/generate_semantic_field_snapshot.py"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="生成前端标准字段定义快照")
    parser.add_argument("--check", action="store_true", help="只校验是否漂移, 不写文件")
    args = parser.parse_args()

    payload = build_payload()
    rendered = _js_header(payload)

    if args.check:
        if not SNAPSHOT_PATH.exists():
            print(f"[FAIL] 快照不存在: {SNAPSHOT_PATH}")
            return 1
        # [*] 按**字节**比较, 不用 read_text ——
        #     read_text 会把 CRLF 归一化成 LF, 于是「换行符漂移」这种问题
        #     在 --check 里**看不见**。快照是生成物, 必须逐字节可复现。
        current = SNAPSHOT_PATH.read_bytes()
        expected = rendered.encode("utf-8")
        if current != expected:
            if current.replace(b"\r\n", b"\n") == expected:
                print(
                    "[FAIL] 快照内容一致, 但换行符是 CRLF(仓库约定 LF); "
                    "请运行 python scripts/generate_semantic_field_snapshot.py 重写"
                )
            else:
                print("[FAIL] 快照与后端定义已漂移, 请运行 python scripts/generate_semantic_field_snapshot.py")
            return 1
        print("[OK] 快照与后端定义一致")
        return 0

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # [*] 显式 newline="\n": Windows 上 write_text 默认写 CRLF,
    #     而仓库的 .gitattributes 规定 ``*.js text eol=lf`` ⇒ 必须写 LF。
    SNAPSHOT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"[OK] 已写入快照: {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
