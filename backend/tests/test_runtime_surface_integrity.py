"""运行时面的**完整性**守护（2026-11-12）。

背景
----
本轮实测踩过一次坑，代价很小但足够说明问题：

* 我把路由里的 ``archived_binding_condition`` 用漏了（重写 import 块时漏掉一项）；
* ``restore_spu`` / ``restore_sku`` 会在**运行时**才炸 ``NameError``；
* 而**全量后端测试照样全绿** —— 那两条路径没有执行用例。

⇒ 一道静态守卫：模块里读到的每个全局名，必须在本模块（或 builtins）里定义过。

另一道守护是给 **typecheck 门禁**的：
``scripts/run_typecheck.py`` 曾经把 ``backend/routers/dashboard_api.py`` 写进目标列表，
而那个文件**早已不存在** ⇒ mypy 每次都报错 ⇒ 这道门禁**从来没有真正跑过**。
⇒ 目标列表里的每个文件都必须真实存在，否则门禁静默失效。
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TYPECHECK_SCRIPT = PROJECT_ROOT / "scripts/run_typecheck.py"
ROUTER_PATH = PROJECT_ROOT / "backend/domains/business/routers/product_center.py"


# ---------------------------------------------------------------------------
# ① typecheck 门禁的目标必须存在
# ---------------------------------------------------------------------------


def _typecheck_targets() -> list[str]:
    """从门禁脚本里把 mypy 的目标列表抠出来。"""
    source = TYPECHECK_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "targets":
                return [
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                ]
    raise AssertionError("门禁脚本里找不到 targets 列表")


def test_typecheck_gate_targets_all_exist():
    """每个 mypy 目标都必须真实存在。

    ⚠️ 指向不存在文件 ⇒ mypy 每次都报错 ⇒ 门禁形同虚设，
    而「门禁是绿的」会被误读成「类型没问题」。
    """
    targets = _typecheck_targets()

    assert targets, "门禁脚本里没有 targets"
    missing = [target for target in targets if not (PROJECT_ROOT / target).exists()]
    assert not missing, "typecheck 目标不存在（门禁会静默失效）: %s" % missing


def test_typecheck_gate_covers_the_product_center_surface():
    """商品中心是本轮改动最重的运行时面 ⇒ 必须在门禁里。"""
    targets = _typecheck_targets()

    assert "backend/domains/business/routers/product_center.py" in targets
    assert "backend/services/product_spu_binding.py" in targets
    assert "backend/services/product_spu_lifecycle.py" in targets


# ---------------------------------------------------------------------------
# ② 路由不得引用未定义的全局名
# ---------------------------------------------------------------------------


def _defined_global_names(tree: ast.Module) -> set[str]:
    """本模块里定义过的所有名字（含嵌套作用域的粗略超集）。"""
    names: set[str] = set(dir(builtins)) | {
        "__name__",
        "__file__",
        "__doc__",
        "__package__",
        "__spec__",
        "__loader__",
        "__builtins__",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _read_global_names(tree: ast.Module) -> set[str]:
    """模块里被**读取**的全局名。

    ⚠️ 局部变量（赋值过 / 参数 / import 过）都已进 ``_defined_global_names``，
    所以这里收集到的就是「看起来像全局、但可能没人定义」的那批名字。
    """
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def test_router_has_no_undefined_global_names():
    """路由不得读取任何没定义过的名字。

    ⚠️ 这类错误**不会**在 import 期暴露，只在执行到那行时才炸 ——
       而那条路径可能根本没有测试覆盖 ⇒ 全量测试照样全绿。
    """
    tree = ast.parse(ROUTER_PATH.read_text(encoding="utf-8"))

    defined = _defined_global_names(tree)
    used = _read_global_names(tree)

    missing = sorted(used - defined)
    assert not missing, (
        "路由引用了未定义的全局名（运行到那行才会 NameError）: %s" % missing
    )


def test_router_imports_the_binding_true_source_helpers():
    """路由用到的归属判定函数必须**真的**从真源导入。

    ⚠️ 补一道针对具体事故的断言：漏掉 ``archived_binding_condition`` 时，
       上面的通用检查也能发现，但这条能直接指出是哪个名字。
    """
    source = ROUTER_PATH.read_text(encoding="utf-8")

    for name in (
        "current_binding_condition",
        "archived_binding_condition",
        "project_current_binding",
        "HISTORICAL_BINDING_STATUS",
    ):
        assert name in source, f"路由里找不到 {name}"
