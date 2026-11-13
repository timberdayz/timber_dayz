"""Contract test: 批次 F-1 —— CI 减重契约（关噪音步骤 + 收窄采集组件 lint）。

背景（2026-11-13 逐个实测，书面结论见 ``docs/superpowers/plans/STATUS.md``
的「批次 F」节）：

CI 的 ``test`` job 里有 45 个硬门禁 + 14 个「只告警」步骤。只告警步骤的特征是
``continue-on-error: true`` 或命令自带 ``|| true`` / ``|| echo``
⇒ **无论成败都不改变流水线结果**。逐个跑过之后，其中 6 个是纯噪音（理由逐条写在
:data:`REMOVED_ADVISORY_STEPS` 里）。

这份守护锁三件事：

1. 那 6 个步骤**不许再回来** —— 它们曾经让人误以为「流水线绿 = 全部检查过了」。
2. 真硬门禁**不许被顺手删掉** —— 减重不等于放松。
3. 采集组件 lint 的扫描范围必须收窄到 ``modules/platforms/**``（规则本意范围），
   而且**门禁强度不变**：仍然是 ``--fail-on none`` 告警模式，不在本次偷偷升级成
   硬门禁（升级属加固方向，另记待办由业务负责人拍板）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

GUARD_RELATIVE = "backend/tests/test_ci_weight_reduction_contract.py"

#: 批次 F-1 移除的只告警步骤。每一项都写明「实测为什么它是噪音」。
REMOVED_ADVISORY_STEPS: Dict[str, str] = {
    "Type checking (critical modules only)": (
        "mypy modules/core/ 实测 440 errors / 13 个文件，全部是动态 ORM 基类误报"
        "（Invalid base class Base）；命令自带 `|| true`，从不让流水线红。"
    ),
    "Database Design Rules Validation": (
        "scripts/validate_code_compliance.py 是空壳：只打印一段说明文字，退出码 0，"
        "不做任何实际检查。"
    ),
    "Run contract tests": (
        "legacy contract_tests.py 三选一循环：web_interface_manager 持续失败"
        "（依赖已不存在的 frontend_streamlit），失败被 `|| echo` 吞掉。"
    ),
    "Run unified health check": (
        "自报「健康检查失败的应用: ['web_interface_manager']」却仍然报通过 —— "
        "既不挡错，又制造「检查过了」的错觉。"
    ),
    "Check for known vulnerabilities": (
        "`safety check` 上游已废弃（CI 自己的注释就写着 deprecated），"
        "输出被 continue-on-error 吞掉；真正的漏洞门禁是 `Safety diff gate`（硬门禁，保留）。"
    ),
    "Check for large files": (
        "命中的 65 个大文件全在本地产物目录（backups/ temp/ docker_volume_backup/ "
        ".playwright-mcp/），**不在 git 跟踪范围** ⇒ CI 上必然 0 命中；"
        "而且 find 的输出被 while 循环吞成 echo，整条命令退出码恒为 0。"
    ),
}

#: 必须保留的真硬门禁（减重不等于放松）。
KEPT_HARD_GATES = (
    "Check for secrets in code",
    "Safety diff gate (PR only, fail on new vulns)",
    "Check project structure",
    "Run Bandit security scan",
)

#: 明确「故意保留」的步骤（继续只告警，但各有理由）。
KEPT_BY_DESIGN = (
    "Clean up leftover test containers",
    "Install Playwright browsers",
    "Validate configurations",
)

LINT_STEP_NAME = "Collection component lint"


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


def _ci_text() -> str:
    assert CI_WORKFLOW.exists(), "CI workflow 不存在: {}".format(CI_WORKFLOW)
    return CI_WORKFLOW.read_text(encoding="utf-8", errors="replace")


def _step_blocks(text: str) -> Dict[str, List[str]]:
    """把 ci.yml 拆成 ``{步骤名: 该步骤的文本块}``。

    步骤边界 = ``- name:`` 或 ``- uses:`` 开头的行；其余行（含 ``run: |`` 的多行
    内容、``if:`` / ``continue-on-error:`` 等）都归到当前步骤。
    """
    blocks: Dict[str, List[str]] = {}
    current_name: Optional[str] = None
    current_lines: List[str] = []
    for line in text.splitlines():
        matched = re.match(r"^\s*-\s+name:\s*(.+?)\s*$", line)
        if matched:
            if current_name is not None:
                blocks[current_name] = current_lines
            current_name = matched.group(1).strip().strip("'\"")
            current_lines = [line]
            continue
        if re.match(r"^\s*-\s+uses:", line):
            if current_name is not None:
                blocks[current_name] = current_lines
            current_name = None
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks[current_name] = current_lines
    return blocks


def _step_names(text: str) -> List[str]:
    """ci.yml 里出现过的全部步骤名。"""
    names = []
    for line in text.splitlines():
        matched = re.match(r"^\s*-\s+name:\s*(.+?)\s*$", line)
        if matched:
            names.append(matched.group(1).strip().strip("'\""))
    return names


# --------------------------------------------------------------------------
# 守护 1：那 6 个噪音步骤不许再回来
# --------------------------------------------------------------------------


@pytest.mark.parametrize("step_name", sorted(REMOVED_ADVISORY_STEPS))
def test_removed_advisory_step_is_not_in_ci(step_name: str):
    """被移除的只告警步骤不许再出现在 CI 里。

    理由必须同时写在纸面（:data:`REMOVED_ADVISORY_STEPS`）与守护里 —— 否则
    半年后有人「顺手加回来」，又会多一个只告警、从不改变结果的步骤。
    """
    names = _step_names(_ci_text())
    assert (
        step_name not in names
    ), "步骤「{0}」是批次 F-1 移除的纯噪音步骤，不该再出现。实测理由：{1}".format(
        step_name, REMOVED_ADVISORY_STEPS[step_name]
    )


# --------------------------------------------------------------------------
# 守护 2：真硬门禁不许被顺手删掉
# --------------------------------------------------------------------------


@pytest.mark.parametrize("step_name", KEPT_HARD_GATES)
def test_hard_gate_is_still_in_ci(step_name: str):
    """减重是删噪音，不是放松门禁。"""
    names = _step_names(_ci_text())
    assert step_name in names, "硬门禁步骤「{0}」被删掉了 —— 减重不等于放松".format(
        step_name
    )


@pytest.mark.parametrize("step_name", KEPT_BY_DESIGN)
def test_kept_by_design_step_is_still_in_ci(step_name: str):
    """这几步是**故意**保留的只告警步骤，各有理由，不许在减重时被误删。"""
    names = _step_names(_ci_text())
    assert (
        step_name in names
    ), "步骤「{0}」是明确保留的（各有理由），不许在减重时被误删".format(step_name)


# --------------------------------------------------------------------------
# 守护 3：采集组件 lint 收窄到 modules/platforms/**，门禁强度不变
# --------------------------------------------------------------------------


def _lint_step_block() -> str:
    blocks = _step_blocks(_ci_text())
    assert LINT_STEP_NAME in blocks, "CI 里找不到步骤「{0}」".format(LINT_STEP_NAME)
    return "\n".join(blocks[LINT_STEP_NAME])


def test_collection_lint_step_still_exists():
    """收窄范围不等于删掉这一步。"""
    assert LINT_STEP_NAME in _step_names(_ci_text())


def test_collection_lint_scope_is_narrowed_to_platform_components():
    """扫描范围必须收窄到 ``modules/platforms/**``（规则本意范围）。

    2026-11-13 实测：CI 把「本次改动的全部 Python 文件」喂给采集组件 lint，
    于是 backend/ tests/ modules/ 里的普通业务代码也被套上「采集组件」规则，
    全仓报出 454 行告警 —— 而这些告警既不属于该规则的本意范围，也从不改变
    流水线结果（``--fail-on none``）。
    """
    block = _lint_step_block()
    assert (
        "--scope platforms" in block
    ), "采集组件 lint 必须用 `--scope platforms` 收窄到 modules/platforms/**：\n{0}".format(block)


def test_collection_lint_gate_strength_is_unchanged():
    """门禁强度不变：仍然是告警模式（``--fail-on none``）。

    ⚠️ 收窄范围 ≠ 升级门禁。把只告警步骤升成硬门禁属**加固方向**，由业务负责人
    另行拍板；本批只做减法。
    """
    block = _lint_step_block()
    assert (
        "--fail-on none" in block
    ), "采集组件 lint 必须保持告警模式（--fail-on none），本批不擅自升成硬门禁：\n{0}".format(block)


# --------------------------------------------------------------------------
# 守护 4：书面记录（律 1 —— 真源只能一个，而且必须写在纸上）
# --------------------------------------------------------------------------


def test_ci_points_to_the_written_record():
    """ci.yml 必须指向书面结论，否则「为什么删」只存在于某个人的记忆里。"""
    text = _ci_text()
    assert "批次 F-1" in text, "ci.yml 里没有指向批次 F-1 书面记录的指针"
    assert "STATUS.md" in text, "ci.yml 里没有指向 STATUS.md 的指针"


def test_written_record_exists_and_covers_removed_steps():
    """书面记录必须真的存在，且逐条写明被移除的步骤。"""
    record = PROJECT_ROOT / "docs" / "superpowers" / "plans" / "STATUS.md"
    assert record.exists(), "STATUS.md 不存在"
    text = record.read_text(encoding="utf-8", errors="replace")
    assert "批次 F" in text, "STATUS.md 里没有「批次 F」这一节"
    for step_name in sorted(REMOVED_ADVISORY_STEPS):
        assert (
            step_name in text
        ), "STATUS.md 里没有写明被移除的步骤「{0}」—— 纸面记录必须逐条齐全".format(
            step_name
        )


# --------------------------------------------------------------------------
# 守护 5：这份守护自己必须进 CI 清单
# --------------------------------------------------------------------------


def test_guard_itself_is_in_ci_root_contract_list():
    """没人调用的守护不是守护。"""
    text = _ci_text()
    assert (
        GUARD_RELATIVE in text
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(GUARD_RELATIVE)


# --------------------------------------------------------------------------
# 守护 6：--scope 的真实行为（不是只看 YAML 文本）
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lint_cli():
    """加载 scripts/lint_collection_components.py。"""
    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import lint_collection_components

    return lint_collection_components


def _unavailable_loader():
    """模拟 DB 不可用（CI 根契约环境里没有 PG）。"""
    from backend.services.collection_component_lint import StableRecordUnavailable

    raise StableRecordUnavailable("测试环境没有数据库")


def _platform_component() -> Path:
    """仓库里真实存在的采集组件文件（必须落在 modules/platforms/** 内）。"""
    for candidate in sorted((PROJECT_ROOT / "modules" / "platforms").rglob("*.py")):
        if "archive" in candidate.parts:
            continue
        return candidate
    raise AssertionError("仓库里找不到 modules/platforms/** 下的采集组件文件")


def test_scope_platforms_keeps_collection_components(lint_cli, capsys):
    """范围内文件必须被扫到（收窄不能把该查的也查没了）。"""
    path = _platform_component()

    lint_cli.main(
        ["--paths", str(path), "--scope", "platforms", "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert "扫描文件数: 1" in output, "范围内文件被误过滤掉了：\n{0}".format(output)


def test_scope_platforms_drops_out_of_scope_files(lint_cli, capsys, tmp_path):
    """范围外文件（backend/ 下的普通业务代码）必须被过滤掉。"""
    outside = tmp_path / "ordinary_business_code.py"
    outside.write_text("def handler():\n    return 1\n", encoding="utf-8")

    lint_cli.main(
        ["--paths", str(outside), "--scope", "platforms", "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert "扫描文件数: 0" in output, "范围外文件没有被过滤：\n{0}".format(output)


def test_scope_platforms_drops_repo_files_outside_platforms(lint_cli, capsys):
    """仓库内、但不在 modules/platforms/ 下的文件同样要被过滤。"""
    outside = PROJECT_ROOT / "backend" / "services" / "collection_component_lint.py"

    lint_cli.main(
        ["--paths", str(outside), "--scope", "platforms", "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert "扫描文件数: 0" in output, "范围外的仓库文件没有被过滤：\n{0}".format(output)


def test_default_scope_keeps_previous_behaviour(lint_cli, capsys, tmp_path):
    """默认（不传 --scope）必须保持旧行为 —— 不能顺手改掉本地用法。"""
    outside = tmp_path / "ordinary_business_code.py"
    outside.write_text("def handler():\n    return 1\n", encoding="utf-8")

    lint_cli.main(
        ["--paths", str(outside), "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert "扫描文件数: 1" in output, "默认行为被改了：\n{0}".format(output)
