#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁：异步任务必须走统一出口，且必须真正关闭数据库连接池。

背景（SSOT）
------------
2026-11-09 生产只读调查发现：生产库 80 个连接槽位**全部打满**且只增不减
（最近 60 分钟新建 45 条，最早一条存活 8 小时 27 分钟，最后一条 SQL 是
``COMMIT;`` —— 事务已提交，连接本身没关）。

根因是「连接收尾」这件事没有唯一真相：

* Celery 同步任务每次调用都新建事件循环，asyncpg 连接绑定在创建它的循环上；
* 旧做法 ``async_engine.sync_engine.dispose(close=False)`` 只是把连接池「软
  丢弃」，**不关闭底层 TCP 连接**，连接随后滞留在数据库服务端白占槽位；
* 而循环结束后连接已无法被正常关闭——想补关都关不掉。

正确做法只有一条：在**循环还活着的时候**真正关闭引擎
（``await async_engine.dispose()``，等价于 ``close=True``）。
本门禁把这条约定变成机器可判定的规则：

R1  ``backend/`` 与 ``modules/`` 的运行时代码里不得出现裸 ``asyncio.run(...)``
    ——只允许出现在 ``backend/utils/async_task_runner.py``（统一出口）内部。
R2  不得出现 ``dispose(close=False)``（软丢弃＝不关连接）
    ——只允许出现在 ``backend/models/database.py`` 的兜底函数内。
R3  不得调用 ``reset_async_engine_pool_for_new_loop``
    ——它只是兜底，业务代码必须走统一出口。
R4  不得出现「自建会话不关闭」：``AsyncSessionLocal()`` 直接赋给变量时，
    必须在**同一个函数**的 ``finally`` 里 ``await <变量>.close()``
    ——async 引擎已改用 NullPool（连接随会话归还即关闭），
    漏关会话＝直接漏一条数据库连接。

违规即退出码非零（fail-closed），除非被显式登记进 ``ALLOWED_ASYNCIO_RUN``
或 ``ALLOWED_UNCLOSED_SESSIONS`` 并写明理由；豁免缺理由视为无效豁免
（门禁自身报错）。

用法
----
    python scripts/verify_async_loop_cleanup.py            # 检查 backend/ 与 modules/
    python scripts/verify_async_loop_cleanup.py --root .   # 指定仓库根目录
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

# 测试目录：不参与门禁
TEST_DIR_NAMES = {"tests", "test", "testing"}
SKIP_DIR_NAMES = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build"}

#: 唯一允许出现裸 asyncio.run( 的文件（统一出口本身）
RUNNER_FILE = "backend/utils/async_task_runner.py"

#: 唯一允许出现 dispose(close=False) 的文件（兜底函数所在处）
DISPOSE_SOFT_FILE = "backend/models/database.py"

#: 兜底函数名：业务代码不得调用
RESET_FUNC_NAME = "reset_async_engine_pool_for_new_loop"

#: 会话工厂名（R5 判定用）
SESSION_FACTORY_NAME = "AsyncSessionLocal"

# 显式豁免登记：{相对路径: {行号: 理由}}
# 新增豁免必须写清理由；空理由视为无效豁免（门禁会报错）。
ALLOWED_ASYNCIO_RUN: dict[str, dict[int, str]] = {
    # 说明：一次性 CLI / 冒烟脚本，进程退出时 socket 由操作系统回收，
    # 不存在长驻进程里的连接累积问题。
}

#: R5 豁免登记：{相对路径: {行号: 理由}}
ALLOWED_UNCLOSED_SESSIONS: dict[str, dict[int, str]] = {}


def _is_test_path(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(part in TEST_DIR_NAMES for part in rel.parts)


def _iter_source_files(root: Path, targets: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        base = (root / target).resolve()
        if base.is_file():
            files.append(base)
            continue
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP_DIR_NAMES for part in p.parts):
                continue
            files.append(p)
    return sorted(set(files))


def _call_name(node: ast.Call) -> str | None:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _nearest_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


def _awaited_close_names(node: ast.AST) -> set[str]:
    """收集该节点内所有 ``await <名字>.close()`` 里的变量名。"""
    names: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Await):
            continue
        value = sub.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        if not isinstance(func, ast.Attribute) or func.attr != "close":
            continue
        if isinstance(func.value, ast.Name):
            names.add(func.value.id)
    return names


def _unclosed_session_hits(tree: ast.AST, rel: str) -> list[str]:
    """R5：找出「自建会话却没在 finally 里关闭」的地方。

    判定口径：``X = AsyncSessionLocal()`` 形式（不是 ``async with``），
    且**最近的所在函数**里没有 ``finally`` 块执行 ``await X.close()``。
    """
    parents = _parent_map(tree)
    hits: list[str] = []

    for node in ast.walk(tree):
        value = None
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            value = node.value
            targets = [node.target]
        else:
            continue

        func = value.func
        if not (isinstance(func, ast.Name) and func.id == SESSION_FACTORY_NAME):
            continue

        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if not names:
            continue

        func_scope = _nearest_function(node, parents)
        if func_scope is None:
            continue

        closed_in_finally: set[str] = set()
        for sub in ast.walk(func_scope):
            if isinstance(sub, ast.Try) and sub.finalbody:
                for stmt in sub.finalbody:
                    closed_in_finally |= _awaited_close_names(stmt)

        if names & closed_in_finally:
            continue

        hits.append(f"{rel}:{node.lineno}")

    return hits


def _scan_file(path: Path, rel: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """返回 (裸 asyncio.run 命中, dispose(close=False) 命中, reset 函数调用命中, 会话未关闭命中)。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        print(f"[parse-error] {rel}: {exc}", file=sys.stderr)
        return [], [], [], []

    run_hits: list[str] = []
    soft_dispose_hits: list[str] = []
    reset_hits: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        fn = node.func
        # asyncio.run(...)
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr == "run"
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "asyncio"
        ):
            run_hits.append(f"{rel}:{node.lineno}")
            continue

        # dispose(close=False)
        if _call_name(node) == "dispose":
            for kw in node.keywords:
                if kw.arg == "close" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    soft_dispose_hits.append(f"{rel}:{node.lineno}")
                    break

        # reset_async_engine_pool_for_new_loop(...)
        if _call_name(node) == RESET_FUNC_NAME:
            reset_hits.append(f"{rel}:{node.lineno}")

    session_hits = _unclosed_session_hits(tree, rel)

    return run_hits, soft_dispose_hits, reset_hits, session_hits


def scan(root: Path, targets: list[str]) -> tuple[list[str], int]:
    files = _iter_source_files(root, targets)
    violations: list[str] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        if _is_test_path(path, root):
            continue

        run_hits, soft_hits, reset_hits, session_hits = _scan_file(path, rel)

        for hit in run_hits:
            line_no = int(hit.rsplit(":", 1)[1])
            if rel == RUNNER_FILE:
                continue
            reason = ALLOWED_ASYNCIO_RUN.get(rel, {}).get(line_no, "")
            if reason.strip():
                continue
            violations.append(
                f"R1 裸 asyncio.run(: {hit} —— 请改用 backend.utils.async_task_runner.run_async_task"
            )

        for hit in soft_hits:
            if rel == DISPOSE_SOFT_FILE:
                continue
            violations.append(
                f"R2 dispose(close=False) 不关闭连接: {hit} —— 请改用 await async_engine.dispose()"
            )

        for hit in reset_hits:
            if rel == DISPOSE_SOFT_FILE:
                continue
            violations.append(
                f"R3 调用兜底函数 {RESET_FUNC_NAME}(): {hit} —— 请改用 run_async_task"
            )

        for hit in session_hits:
            line_no = int(hit.rsplit(":", 1)[1])
            reason = ALLOWED_UNCLOSED_SESSIONS.get(rel, {}).get(line_no, "")
            if reason.strip():
                continue
            violations.append(
                f"R5 会话未关闭: {hit} —— AsyncSessionLocal() 自建的会话必须在 "
                "同一函数的 finally 里 await <变量>.close()"
            )

    # 豁免有效性：登记了但没理由 = 无效豁免
    for rel, entries in ALLOWED_ASYNCIO_RUN.items():
        for line_no, reason in entries.items():
            if not reason.strip():
                violations.append(f"R4 无效豁免（缺理由）: {rel}:{line_no}")

    for rel, entries in ALLOWED_UNCLOSED_SESSIONS.items():
        for line_no, reason in entries.items():
            if not reason.strip():
                violations.append(f"R4 无效豁免（缺理由）: {rel}:{line_no}")

    return violations, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="异步循环收尾门禁")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help="扫描目标目录（可重复），默认 backend/ 与 modules/",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets = args.target or ["backend", "modules"]
    violations, scanned = scan(root, targets)

    print(f"[async-loop-gate] 扫描 {scanned} 个文件")
    if violations:
        print(f"[async-loop-gate] 发现 {len(violations)} 处违规：")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("[async-loop-gate] OK：异步任务均走统一出口并真正关闭连接池")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
