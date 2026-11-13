"""Contract test: the cleanup script must actually be **wired into a flow**.

Background (measured 2026-11-13):
    ``scripts/cleanup_test_containers.py`` existed since 2026-10 and had a full
    contract test of its own -- but **nothing ever called it**.  The only
    references in the repo were the script's own docstring and its own test.

    Result: 11 anonymous postgres volumes (736 MB) accumulated between
    2026-11-09 and 2026-11-13, in bursts (6 of them inside 72 seconds on
    2026-11-11) -- every one of them a container that was killed before its
    ``atexit`` hook could run, with no cleanup step afterwards.

    This is the same shape as the 2026-11-13 ``.ps1`` encoding incident: a
    convention written on paper, a guard that exists, and **no mechanism that
    makes them run**.  A guard nobody invokes is not a guard.

What this file locks in:
    1. The cleanup script must be invoked by at least one executable flow --
       either the pytest session teardown (``backend/tests/conftest.py``) or a
       CI workflow step.
    2. The invocation must use ``--apply`` -- a dry-run invocation cleans
       nothing.
    3. The invocation must not be free to fail the build: cleanup is
       best-effort, so it must not break the test run it is attached to.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = "scripts/cleanup_test_containers.py"
SCRIPT = PROJECT_ROOT / SCRIPT_REL

CONFTEST = PROJECT_ROOT / "backend" / "tests" / "conftest.py"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: Every place that is allowed to trigger the cleanup.
CANDIDATE_FLOWS = (
    ("pytest session teardown", CONFTEST),
    ("CI workflow", CI_WORKFLOW),
)


def _invocations(path: Path) -> List[str]:
    """Lines in ``path`` that reference the cleanup script."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = []
    for line in text.splitlines():
        if "cleanup_test_containers" in line:
            hits.append(line)
    return hits


def test_cleanup_script_exists():
    assert SCRIPT.exists(), "清理脚本必须存在: {0}".format(SCRIPT_REL)


def test_cleanup_script_is_invoked_by_at_least_one_flow():
    """**核心守护**：清理脚本必须被至少一个可执行流程调用。

    ⚠️ 2026-11-13 实测：脚本存在、守护也存在，但没有任何流程调用它 ⇒
    11 天里攒了 11 个匿名卷（736 MB）。⇒ "在仓库里"不等于"会被执行"。
    """
    invoked = []
    for label, path in CANDIDATE_FLOWS:
        if _invocations(path):
            invoked.append(label)
    assert invoked, (
        "清理脚本 {0} 没有被任何流程调用 —— 它只会静静躺着，残留照样堆积。"
        " 至少要有一处: backend/tests/conftest.py 的 session 收尾钩子，"
        "或 .github/workflows/ci.yml 的清理步骤。".format(SCRIPT_REL)
    )


def test_invocation_actually_applies_the_cleanup():
    """调用必须带 ``--apply`` —— 只报告不清理等于没调用。"""
    lines: List[str] = []
    for _label, path in CANDIDATE_FLOWS:
        lines.extend(_invocations(path))
    assert lines, "没有找到任何调用点"
    applying = [line for line in lines if "--apply" in line and not _is_commented(line)]
    assert (
        applying
    ), "清理脚本的调用点必须带 --apply, 否则只是 dry-run(什么都不会删): {0}".format(
        lines
    )


def test_invocation_does_not_break_the_test_run():
    """清理是 best-effort —— 不得让测试/流水线因为清理失败而红。

    清理脚本自己的退出码在有残留时是 0(成功)、无残留时也是 0；
    但调用点仍不应把它当成硬门禁：清理失败不该掩盖真实的测试失败。
    """
    for label, path in CANDIDATE_FLOWS:
        for line in _invocations(path):
            if "--apply" in line and _is_commented(line):
                continue
            # 允许显式忽略退出码（例如 `|| true` / `check=False`），
            # 但不允许它成为失败源。
            assert not re.search(
                r"\|\|\s*exit\s+1", line
            ), "{0} 里的清理调用不得用 `|| exit 1` 把清理失败变成测试失败: {1}".format(
                label, line.strip()
            )


def test_guard_test_itself_is_collected_by_ci():
    """这份守护必须进 CI 清单 —— 否则它和被守护的脚本一样只是摆设。"""
    assert CI_WORKFLOW.exists(), "CI workflow 不存在"
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8", errors="replace")
    relative = "backend/tests/test_cleanup_test_containers_wired_contract.py"
    assert (
        relative in ci_text
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(relative)


def _sessionfinish_body() -> str:
    """取出 conftest 里 pytest_sessionfinish 钩子的函数体。"""
    text = CONFTEST.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"def\s+pytest_sessionfinish\b.*?(?=\ndef\s+|\n@|\Z)", text, re.DOTALL
    )
    assert match, "backend/tests/conftest.py 里没有 pytest_sessionfinish 钩子"
    return match.group(0)


def test_sessionfinish_hook_actually_invokes_the_script():
    """conftest 的收尾钩子必须**真的调用**清理脚本（而不是只留一句注释）。

    ⚠️ 2026-11-13 实测踩到的坑：只断言"文件里提到了脚本"是不够 ——
    一句注释也能骗过它。所以这里断言的是**可执行形态**：钩子里必须出现
    ``subprocess.run`` + 脚本路径 + ``--apply``。
    """
    body = _sessionfinish_body()
    assert "subprocess.run" in body, "收尾钩子没有真正执行任何东西"
    assert "cleanup_test_containers" in body, "收尾钩子没有调用清理脚本"
    assert "--apply" in body, "收尾钩子调用清理脚本时必须带 --apply"


def test_sessionfinish_hook_is_best_effort():
    """清理失败**不得**让测试会话变红 —— 不能掩盖真实的测试失败。"""
    body = _sessionfinish_body()
    assert "except" in body, "收尾钩子必须吞掉清理异常（best-effort）"
    assert "check=False" in body, "收尾钩子必须用 check=False —— 清理失败不应抛异常"


def _is_commented(line: str) -> bool:
    """该行是否为纯注释（注释里的示例不算真实调用）。"""
    stripped = line.strip()
    return stripped.startswith("#") or stripped.startswith("*")
