"""审计 + 守卫：并发上下文里共享数据库会话的写法。

为什么要有这条
--------------
SQLAlchemy 的 ``AsyncSession`` **不是并发安全的**。同一个 session 被多个协程同时用，
一个协程的 ``commit()`` 会撞上另一个协程的 ``execute()`` / ``close()``，抛出::

    sqlalchemy.exc.IllegalStateChangeError:
    Method 'close()' can't be called here; method 'commit()' is already in progress

线上真实事故（2026-10-26 14:11~14:12）：
``GET /api/data-sync/governance/stats`` 连续 4 次 500，
页面上的「数据治理概览」整片变成 ``--``，连累「同步全部可同步文件」按钮被禁用。

判定规则
--------
1. **请求级会话变量**（会被多个协程共享，共享即错）：
   - 形参里类型注解是 ``AsyncSession``，或默认值里出现 ``get_async_db``
   - 局部赋值 ``X = <类名>(<请求级会话变量>)`` → X **间接持有**该会话
2. 在 ``asyncio.gather(...)`` / ``asyncio.create_task(...)`` 的实参里
   引用了请求级会话变量（含间接持有）→ 报错
3. 局部 ``X = AsyncSessionLocal()`` 属于**独立会话**，不算请求级会话（豁免）

用法::

    python scripts/check_async_session_concurrency.py            # 审计 + 非零退出
    python scripts/check_async_session_concurrency.py --report   # 只出报告，不退出非零
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("backend", "modules", "scripts")

CONCURRENCY_CALLS = {
    "gather",
    "create_task",
    "ensure_future",
    "run_coroutine_threadsafe",
}
SESSION_FACTORY_NAMES = {"AsyncSessionLocal", "SessionLocal", "sessionmaker"}
SESSION_PARAM_HINTS = ("db", "session", "_db", "_session", "database_session")


def _is_session_factory(node: ast.AST) -> bool:
    """``AsyncSessionLocal()`` / ``SessionLocal()`` → 独立会话工厂。"""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in SESSION_FACTORY_NAMES
        if isinstance(func, ast.Attribute):
            return func.attr in SESSION_FACTORY_NAMES
    return False


def _is_request_session_source(node: ast.AST) -> bool:
    """表达式是否可能拿到**请求级**会话（Depends 注入的）。"""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"get_async_db", "get_db"}:
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"get_async_db", "get_db"}:
            return True
    return False


def _mentions_request_session(node: ast.AST) -> bool:
    return any(_is_request_session_source(child) for child in ast.walk(node))


class FunctionScanner(ast.NodeVisitor):
    """单函数内的并发调用审计。"""

    def __init__(self, filename: str, asyncio_names: set[str] | None = None) -> None:
        self.filename = filename
        # 文件里 `from asyncio import gather, create_task` 导入的名字
        self.asyncio_names = asyncio_names or set()
        self.findings: list[tuple[int, str, str]] = []

    # -- 变量分类 --------------------------------------------------------
    def _collect_session_vars(self, func: ast.AST) -> tuple[set[str], set[str]]:
        """返回 (直接持有的会话变量, 间接持有会话的对象变量)。"""
        direct: set[str] = set()
        indirect: set[str] = set()

        args_node = getattr(func, "args", None)
        if args_node is not None:
            positional = list(args_node.posonlyargs) + list(args_node.args)
            defaults = list(args_node.defaults)
            offset = len(positional) - len(defaults)
            for index, arg in enumerate(positional):
                default_node = defaults[index - offset] if index >= offset else None
                annotation = ast.unparse(arg.annotation) if arg.annotation else ""
                if "AsyncSession" in annotation or (
                    default_node is not None and _mentions_request_session(default_node)
                ):
                    direct.add(arg.arg)
                elif any(hint in arg.arg.lower() for hint in SESSION_PARAM_HINTS):
                    direct.add(arg.arg)
            for arg, default_node in zip(
                list(args_node.kwonlyargs), list(args_node.kw_defaults)
            ):
                annotation = ast.unparse(arg.annotation) if arg.annotation else ""
                if "AsyncSession" in annotation or (
                    default_node is not None and _mentions_request_session(default_node)
                ):
                    direct.add(arg.arg)
                elif any(hint in arg.arg.lower() for hint in SESSION_PARAM_HINTS):
                    direct.add(arg.arg)

        for node in ast.walk(func):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if _is_session_factory(node.value):
                continue  # 独立会话，不共享
            if _mentions_request_session(node.value):
                direct.add(target.id)
                continue
            # X = SomeService(db) → 间接持有
            if isinstance(node.value, ast.Call):
                args_src = node.value.args + [kw.value for kw in node.value.keywords]
                if any(
                    isinstance(arg, ast.Name) and arg.id in direct for arg in args_src
                ):
                    indirect.add(target.id)
        return direct, indirect

    # -- 并发调用 --------------------------------------------------------
    def _audit_concurrency_call(self, node: ast.AST, func: ast.AST) -> None:
        direct, indirect = self._collect_session_vars(func)
        shared = direct | indirect
        if not shared:
            return
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func_name = ""
            is_asyncio_call = False
            if isinstance(call.func, ast.Attribute):
                func_name = call.func.attr
                # 只认 `asyncio.xxx(...)` —— 业务里常有同名函数（如 create_task）
                is_asyncio_call = (
                    isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "asyncio"
                )
            elif isinstance(call.func, ast.Name):
                func_name = call.func.id
                is_asyncio_call = call.func.id in self.asyncio_names
            if not is_asyncio_call or func_name not in CONCURRENCY_CALLS:
                continue
            for arg in list(call.args) + [kw.value for kw in call.keywords]:
                for child in ast.walk(arg):
                    if isinstance(child, ast.Name) and child.id in shared:
                        kind = "直接" if child.id in direct else "间接"
                        self.findings.append(
                            (
                                child.lineno,
                                func_name,
                                f"{kind}持有请求级会话的变量 '{child.id}' "
                                f"被并发调用 {func_name}() 使用",
                            )
                        )
                        break

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._audit_concurrency_call(node, node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._audit_concurrency_call(node, node)
        self.generic_visit(node)


def iter_python_files(roots: Sequence[str] = SCAN_ROOTS) -> Iterable[Path]:
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(
                part in {"__pycache__", ".venv", "node_modules"} for part in path.parts
            ):
                continue
            yield path


def _collect_asyncio_imports(tree: ast.AST) -> set[str]:
    """文件里 `from asyncio import gather` 导入的并发原语名字。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            for alias in node.names:
                if alias.name in CONCURRENCY_CALLS:
                    names.add(alias.asname or alias.name)
    return names


def _display_path(path: Path) -> str:
    """仓库内显示相对路径，仓库外显示绝对路径（别让调用方炸在 relative_to 上）。"""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def audit_file(path: Path) -> list[tuple[int, str, str]]:
    try:
        source = io.open(path, encoding="utf-8").read()
    except OSError:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    scanner = FunctionScanner(_display_path(path), _collect_asyncio_imports(tree))
    scanner.visit(tree)
    return scanner.findings


def main() -> int:
    parser = argparse.ArgumentParser(description="审计并发共享数据库会话的写法")
    parser.add_argument("--report", action="store_true", help="只出报告，不以非零退出")
    args = parser.parse_args()

    total = 0
    for path in iter_python_files():
        findings = audit_file(path)
        if not findings:
            continue
        total += len(findings)
        print(f"{path.relative_to(REPO_ROOT)}")
        for lineno, func_name, message in findings:
            print(f"  {lineno}: [{func_name}] {message}")

    print()
    print(f"并发共享数据库会话：共 {total} 处")
    if total and not args.report:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
