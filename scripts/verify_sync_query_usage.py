#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁：禁止在异步上下文里使用同步 ORM Query API（``db.query(...)``）。

背景（SSOT）
------------
仓库的数据库访问存在两份真相：同步 ``Session`` 与异步 ``AsyncSession``。
业务函数过去只声明「我收一个 db」，不声明「我要求哪一种 db」，
于是同一个函数被同步脚本和 async 路由同时复用，session 模型必然错配，
表现为 ``'AsyncSession' object has no attribute 'query'``。

本门禁把这条约定变成机器可判定的规则：

R1  ``async def`` 函数体内不得出现 ``.query(...)``。
R2  ``async def`` 函数不得调用「内含 ``.query(...)`` 的同步函数」
    （跨文件调用同样会被捕获）。

违规即退出码非零（fail-closed），除非该调用点被显式登记进
``ALLOWED_SYNC_CALLS`` 并写明理由。

用法
----
    python scripts/verify_sync_query_usage.py            # 检查 backend/ 与 scripts/
    python scripts/verify_sync_query_usage.py --root .   # 指定仓库根目录
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# 测试目录：不参与门禁
TEST_DIR_NAMES = {"tests", "test", "testing"}
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}

# 显式豁免登记：{相对路径: {函数名: 理由}}
# 新增豁免必须写清理由；空理由视为无效豁免（门禁会报错）。
ALLOWED_SYNC_CALLS: dict[str, dict[str, str]] = {
    # 说明：这些调用点来自同步脚本/CLI 入口，本身就在同步上下文，
    # 通过 run_in_threadpool / run_in_executor 进入，不构成 async 上下文错配。
}


@dataclass
class FuncDef:
    rel: str
    qualname: str
    short_name: str
    is_async: bool
    lineno: int
    has_query: bool = False
    calls: list[tuple[str, int]] = field(default_factory=list)  # (被调短名, 行号)


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


def _collect_funcs(
    path: Path, rel: str
) -> tuple[list[FuncDef], list[tuple[FuncDef, int]]]:
    """返回 (函数列表, [(函数, .query( 行号)])。"""
    try:
        src = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
    except Exception as exc:  # noqa: BLE001
        print(f"[parse-error] {rel}: {exc}", file=sys.stderr)
        return [], []

    funcs: list[FuncDef] = []
    query_hits: list[tuple[FuncDef, int]] = []

    def visit(node: ast.AST, stack: list[FuncDef]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join([f.short_name for f in stack] + [child.name])
                fd = FuncDef(
                    rel=rel,
                    qualname=qual,
                    short_name=child.name,
                    is_async=isinstance(child, ast.AsyncFunctionDef),
                    lineno=child.lineno,
                )
                funcs.append(fd)
                stack.append(fd)
                visit(child, stack)
                stack.pop()
                continue
            if isinstance(child, ast.Call):
                fn = child.func
                if isinstance(fn, ast.Attribute) and fn.attr == "query":
                    if stack:
                        top = stack[-1]
                        top.has_query = True
                        query_hits.append((top, child.lineno))
                    else:
                        print(
                            f"[module-level-query] {rel}:{child.lineno} 模块级 .query() 调用",
                            file=sys.stderr,
                        )
                callee = None
                if isinstance(fn, ast.Attribute):
                    callee = fn.attr
                elif isinstance(fn, ast.Name):
                    callee = fn.id
                if callee and stack:
                    stack[-1].calls.append((callee, child.lineno))
            visit(child, stack)

    visit(tree, [])
    return funcs, query_hits


def _collect_await_calls(path: Path, rel: str) -> list[FuncDef]:
    """收集所有 async def（用于 R2 调用方判定）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    out: list[FuncDef] = []

    def visit(node: ast.AST, stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join(stack + [child.name])
                out.append(
                    FuncDef(
                        rel=rel,
                        qualname=qual,
                        short_name=child.name,
                        is_async=isinstance(child, ast.AsyncFunctionDef),
                        lineno=child.lineno,
                    )
                )
                visit(child, stack + [child.name])
                continue
            visit(child, stack)

    visit(tree, [])
    return out


def scan(root: Path, targets: list[str]) -> tuple[list[str], int]:
    files = _iter_source_files(root, targets)
    all_funcs: list[FuncDef] = []
    query_hits: list[tuple[FuncDef, int]] = []
    async_funcs: list[FuncDef] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        if _is_test_path(path, root):
            continue
        funcs, hits = _collect_funcs(path, rel)
        all_funcs.extend(funcs)
        query_hits.extend(hits)
        async_funcs.extend(f for f in funcs if f.is_async)

    # 短名 -> 含 .query( 的同步函数（可能有同名歧义，交由豁免登记消解）
    sync_query_names: dict[str, list[FuncDef]] = {}
    for fd in all_funcs:
        if fd.has_query and not fd.is_async:
            sync_query_names.setdefault(fd.short_name, []).append(fd)

    violations: list[str] = []

    # R1：async def 内直接 .query(
    for fd, lineno in query_hits:
        if fd.is_async:
            violations.append(
                f"R1 async函数内使用同步查询: {fd.rel}:{lineno}  ({fd.qualname})"
            )

    # R2：async def 调用含 .query( 的同步函数
    for af in async_funcs:
        for callee, lineno in af.calls:
            if callee not in sync_query_names:
                continue
            for target in sync_query_names[callee]:
                allow = ALLOWED_SYNC_CALLS.get(target.rel, {}).get(target.qualname)
                if allow:
                    continue
                violations.append(
                    f"R2 async函数调用同步查询函数: {af.rel}:{lineno}  "
                    f"{af.qualname}() -> {target.rel}:{target.qualname}()"
                )
                break

    # 豁免有效性
    for rel, entries in ALLOWED_SYNC_CALLS.items():
        for qual, reason in entries.items():
            if not reason.strip():
                violations.append(f"R3 无效豁免（缺理由）: {rel}::{qual}")

    return violations, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 ORM Query API 使用门禁")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help="扫描目标目录（可重复），默认 backend/ 与 scripts/",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets = args.target or ["backend", "scripts"]
    violations, scanned = scan(root, targets)

    print(f"[sync-query-gate] 扫描 {scanned} 个文件")
    if violations:
        print(f"[sync-query-gate] 发现 {len(violations)} 处违规：")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("[sync-query-gate] OK：未发现异步上下文使用同步查询")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
