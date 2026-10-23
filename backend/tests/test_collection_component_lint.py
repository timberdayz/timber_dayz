# -*- coding: utf-8 -*-
"""采集组件 lint 引擎逐规则测试（批次 3）。

覆盖：
- 既有 9 条代码级规则与录制器行为一致（type 集合 + 关键文案）
- 新增 8 条规则（A4 表）各自的「应报 / 应放行」
- 豁免机制（行内 / 文件级 / 无效豁免）
- AST 扩展的吞异常判定
- 无 DB 环境下仓库级规则的显式跳过
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.services.collection_component_lint import (
    StableComponentRecord,
    StableRecordUnavailable,
    analyze_component_file,
    analyze_python_code,
    analyze_stable_records,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


# --------------------------------------------------------------------------
# 测试辅助
# --------------------------------------------------------------------------


def _write_component(tmp_path: Path, name: str, source: str) -> Path:
    """把组件源码写到标准平台目录结构下。"""
    path = tmp_path / "modules" / "platforms" / "miaoshou" / "components" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _rules(result: dict) -> set[str]:
    """结果里的全部规则名。"""
    return {item["type"] for item in result["errors"]} | {
        item["type"] for item in result["warnings"]
    }


def _messages(result: dict, rule: str) -> list[str]:
    """指定规则的提示文案。"""
    items = list(result["errors"]) + list(result["warnings"])
    return [item["message"] for item in items if item["type"] == rule]


def _oversized_function_source(body_lines: int = 60) -> str:
    """生成一个超长函数源码。"""
    body = "\n".join(f"    value_{index} = {index}" for index in range(body_lines))
    return "def big():\n" + body + "\n"


def _oversized_class_source(body_lines: int = 520) -> str:
    """生成一个超长类源码。"""
    body = "\n".join(f"    attr_{index} = {index}" for index in range(body_lines))
    return "class Big:\n" + body + "\n"


COMPONENT_WITH_REPORT_STEP = '''"""示例组件。"""

from modules.components.base import ComponentBase


class SampleComponent(ComponentBase):
    platform = "miaoshou"
    component_type = "export"

    async def run(self, page):
        self.logger.info("开始执行")
        await self.report_step("step_start", "sample")
        await page.wait_for_selector("#result", state="visible", timeout=5000)
        return None
'''

COMPONENT_WITHOUT_REPORT_STEP = '''"""示例组件。"""

from modules.components.base import ComponentBase


class SampleComponent(ComponentBase):
    platform = "miaoshou"
    component_type = "export"

    async def run(self, page):
        await page.wait_for_selector("#result", state="visible", timeout=5000)
        return None
'''

COMPONENT_WITH_LOGGER = '''"""示例组件。"""

from modules.components.base import ComponentBase


class SampleComponent(ComponentBase):
    platform = "miaoshou"
    component_type = "export"

    async def run(self, page):
        self.logger.info("开始执行")
        await page.wait_for_selector("#result", state="visible", timeout=5000)
        return None
'''

NAVIGATION_SINGLE_SIGNAL = '''"""导航组件。"""

from modules.components.base import ComponentBase


class MiaoshouNavigation(ComponentBase):
    platform = "miaoshou"
    component_type = "navigation"

    async def run(self, page):
        await page.wait_for_selector("#result", state="visible", timeout=5000)
        return None
'''

NAVIGATION_DOUBLE_SIGNAL = '''"""导航组件。"""

from modules.components.base import ComponentBase


class MiaoshouNavigation(ComponentBase):
    platform = "miaoshou"
    component_type = "navigation"

    async def run(self, page):
        await page.wait_for_selector("#result", state="visible", timeout=5000)
        if page.url != "https://example.com/orders":
            return None
        return None
'''

RETRY_WITHOUT_BUDGET = '''"""示例组件。"""

from modules.components.base import ComponentBase


class SampleComponent(ComponentBase):
    platform = "miaoshou"
    component_type = "export"

    async def run(self, page):
        await page.click("#submit")
        return None
'''

RETRY_WITH_TIMEOUT_CONSTANT = '''"""示例组件。"""

from modules.components.base import ComponentBase

TIMEOUT_MS = 5000


class SampleComponent(ComponentBase):
    platform = "miaoshou"
    component_type = "export"

    async def run(self, page):
        await page.click("#submit")
        return None
'''


# --------------------------------------------------------------------------
# 既有 9 条规则：与录制器行为一致
# --------------------------------------------------------------------------


LEGACY_ERROR_SAMPLE = """import time


async def run(page):
    await page.wait_for_timeout(1200)
    await time.sleep(1)
    if await page.locator("tr").count() > 0 and await page.locator("tr").first.is_visible():
        pass
    try:
        await page.click("#x")
    except Exception:
        pass
    row = page.locator("tr").first
"""

LEGACY_WARNING_SAMPLE = """import asyncio


async def run(page):
    # 固定等待: 动画结束
    await page.wait_for_timeout(1200)
    # 固定等待: 验证码回传后等待跳转
    await asyncio.sleep(2.0)
    # 业务语义: 第N项固定为最新记录，允许 first-nth-justified
    row = page.locator("tr").first
"""


def test_legacy_error_rules_keep_type_names_and_messages():
    """既有 error 规则的 type 名与关键文案一字未改。"""
    result = analyze_python_code(LEGACY_ERROR_SAMPLE)

    assert {item["type"] for item in result["errors"]} == {
        "wait_for_timeout_usage",
        "fixed_sleep_usage",
        "count_is_visible_pattern",
        "swallow_exception_pattern",
        "first_nth_usage",
    }
    assert result["warnings"] == []
    assert result["errors"][0]["message"] == (
        "检测到 1 处无理由 wait_for_timeout。请改为条件等待，或补充明确固定等待原因注释。"
    )
    assert result["errors"][1]["message"] == (
        "检测到 1 处无理由固定 sleep。请优先使用条件等待；若确需固定延时，请注释说明原因。"
    )
    assert result["errors"][2]["message"] == (
        "检测到 count()+is_visible() 单次判断。请改为 expect()/wait_for() 可重试等待。"
    )
    assert result["errors"][3]["message"] == (
        "检测到 except Exception: pass。请改为记录上下文并返回可诊断错误，避免静默继续。"
    )
    assert result["errors"][4]["message"] == (
        "检测到 2 处无注释依据的 .first/.nth。请先收敛作用域，或补充业务语义注释后再使用。"
    )


def test_legacy_warning_rules_keep_type_names_and_messages():
    """既有 warning 规则的 type 名与关键文案一字未改。"""
    result = analyze_python_code(LEGACY_WARNING_SAMPLE)

    assert result["errors"] == []
    assert {item["type"] for item in result["warnings"]} == {
        "wait_for_timeout_with_reason",
        "fixed_sleep_with_reason",
        "first_nth_with_reason",
    }
    assert result["warnings"][0]["message"] == (
        "检测到 1 处有理由的 wait_for_timeout。建议评估是否可进一步改为条件等待。"
    )
    assert result["warnings"][1]["message"] == (
        "检测到 1 处有理由固定 sleep。建议评估是否可替换为条件等待。"
    )
    assert result["warnings"][2]["message"] == (
        "检测到 1 处有注释依据的 .first/.nth，请确认该场景确有业务顺序语义。"
    )


def test_legacy_result_shape_is_type_and_message_only():
    """录制器依赖的返回形状仍是 {"type", "message"}。"""
    result = analyze_python_code(LEGACY_ERROR_SAMPLE)

    for item in result["errors"] + result["warnings"]:
        assert set(item.keys()) == {"type", "message"}


def test_analyze_python_code_reports_syntax_error():
    """语法错误仍走 syntax_error 分支。"""
    result = analyze_python_code("def broken(:\n")

    assert [item["type"] for item in result["errors"]] == ["syntax_error"]
    assert result["warnings"] == []


def test_analyze_python_code_empty_input_returns_empty_lists():
    """空输入不产生任何命中。"""
    result = analyze_python_code("")

    assert result == {"errors": [], "warnings": []}


# --------------------------------------------------------------------------
# A4 规则 1：missing_report_step
# --------------------------------------------------------------------------


def test_missing_report_step_is_reported(tmp_path: Path):
    """组件类没有 report_step 调用时必须报错。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    result = analyze_component_file(path)

    assert "missing_report_step" in _rules(result)
    assert any(
        item["type"] == "missing_report_step" and item["severity"] == "error"
        for item in result["errors"]
    )


def test_missing_report_step_is_not_reported_when_called(tmp_path: Path):
    """文件里存在 report_step 调用时放行。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITH_REPORT_STEP)

    result = analyze_component_file(path)

    assert "missing_report_step" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 2：missing_logger_usage
# --------------------------------------------------------------------------


def test_missing_logger_usage_is_reported(tmp_path: Path):
    """组件类从不使用 self.logger / self._log 时告警。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    result = analyze_component_file(path)

    assert "missing_logger_usage" in _rules(result)
    assert any(
        item["type"] == "missing_logger_usage" and item["severity"] == "warning"
        for item in result["warnings"]
    )


def test_missing_logger_usage_is_not_reported_when_logger_used(tmp_path: Path):
    """出现 self.logger 时放行。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITH_LOGGER)

    result = analyze_component_file(path)

    assert "missing_logger_usage" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 3：oversized_function
# --------------------------------------------------------------------------


def test_oversized_function_is_reported(tmp_path: Path):
    """函数超过 50 行时报错。"""
    path = _write_component(tmp_path, "big_export.py", _oversized_function_source())

    result = analyze_component_file(path)

    assert "oversized_function" in _rules(result)


def test_oversized_function_is_not_reported_for_short_function(tmp_path: Path):
    """函数不超过 50 行时放行。"""
    path = _write_component(tmp_path, "small_export.py", _oversized_function_source(40))

    result = analyze_component_file(path)

    assert "oversized_function" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 4：oversized_class
# --------------------------------------------------------------------------


def test_oversized_class_is_reported(tmp_path: Path):
    """类超过 500 行时报错。"""
    path = _write_component(tmp_path, "big_class.py", _oversized_class_source())

    result = analyze_component_file(path)

    assert "oversized_class" in _rules(result)


def test_oversized_class_is_not_reported_for_small_class(tmp_path: Path):
    """类不超过 500 行时放行。"""
    path = _write_component(tmp_path, "small_class.py", _oversized_class_source(400))

    result = analyze_component_file(path)

    assert "oversized_class" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 5：missing_stable_component_record
# --------------------------------------------------------------------------


def test_missing_stable_component_record_is_reported(tmp_path: Path):
    """canonical 组件没有 stable 记录时报错。"""
    path = _write_component(tmp_path, "inventory_export.py", COMPONENT_WITH_REPORT_STEP)

    result = analyze_component_file(path, stable_records=[])

    assert "missing_stable_component_record" in _rules(result)
    assert any(
        "miaoshou/inventory_export" in item["message"] for item in result["errors"]
    )


def test_missing_stable_component_record_is_not_reported_when_recorded(
    tmp_path: Path,
):
    """存在同名 stable 记录时放行。"""
    path = _write_component(tmp_path, "inventory_export.py", COMPONENT_WITH_REPORT_STEP)
    records = [
        StableComponentRecord(
            component_name="miaoshou/inventory_export",
            file_path="modules/platforms/miaoshou/components/inventory_export.py",
        )
    ]

    result = analyze_component_file(path, stable_records=records)

    assert "missing_stable_component_record" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 6：stable_points_to_archived_file
# --------------------------------------------------------------------------


def test_stable_points_to_archived_file_is_reported(tmp_path: Path):
    """stable 记录指向 archive/ 目录时报错。"""
    records = [
        StableComponentRecord(
            component_name="miaoshou/inventory_snapshot_export",
            file_path="modules/platforms/miaoshou/archive/inventory_snapshot_export.py",
        )
    ]

    result = analyze_stable_records(records)

    assert "stable_points_to_archived_file" in _rules(result)


def test_stable_points_to_archived_file_is_not_reported_for_existing_file(
    tmp_path: Path,
):
    """stable 记录指向真实存在的文件时放行。"""
    target = tmp_path / "modules" / "platforms" / "miaoshou" / "components" / "login.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# ok\n", encoding="utf-8")
    records = [
        StableComponentRecord(
            component_name="miaoshou/login",
            file_path="modules/platforms/miaoshou/components/login.py",
        )
    ]

    result = analyze_stable_records(records, project_root=tmp_path)

    assert "stable_points_to_archived_file" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 7：single_signal_navigation
# --------------------------------------------------------------------------


def test_single_signal_navigation_is_reported(tmp_path: Path):
    """导航组件只有一种就绪信号时告警。"""
    path = _write_component(tmp_path, "navigation.py", NAVIGATION_SINGLE_SIGNAL)

    result = analyze_component_file(path)

    assert "single_signal_navigation" in _rules(result)


def test_single_signal_navigation_is_not_reported_with_two_signals(tmp_path: Path):
    """导航组件具备两种就绪信号时放行。"""
    path = _write_component(tmp_path, "navigation.py", NAVIGATION_DOUBLE_SIGNAL)

    result = analyze_component_file(path)

    assert "single_signal_navigation" not in _rules(result)


# --------------------------------------------------------------------------
# A4 规则 8：missing_retry_budget
# --------------------------------------------------------------------------


def test_missing_retry_budget_is_reported(tmp_path: Path):
    """既无 timeout 常量也无 RetryStrategy 时告警。"""
    path = _write_component(tmp_path, "sample_export.py", RETRY_WITHOUT_BUDGET)

    result = analyze_component_file(path)

    assert "missing_retry_budget" in _rules(result)


def test_missing_retry_budget_is_not_reported_with_timeout_constant(tmp_path: Path):
    """存在 timeout 常量声明时放行。"""
    path = _write_component(tmp_path, "sample_export.py", RETRY_WITH_TIMEOUT_CONSTANT)

    result = analyze_component_file(path)

    assert "missing_retry_budget" not in _rules(result)


# --------------------------------------------------------------------------
# 豁免机制
# --------------------------------------------------------------------------


def test_inline_ignore_exempts_the_violation_on_that_line(tmp_path: Path):
    """行内豁免放行该行所在的违规（注释写在违规语句的上一行）。"""
    source = (
        "# lint:ignore[oversized_function] —— 已排期拆分，见 V2 计划\n"
        "def big():\n"
        + "\n".join(f"    value_{index} = {index}" for index in range(60))
        + "\n"
    )
    path = _write_component(tmp_path, "big_export.py", source)

    result = analyze_component_file(path)

    assert "oversized_function" not in _rules(result)
    assert "invalid_ignore_comment" not in _rules(result)


def test_inline_ignore_as_trailing_comment_exempts_the_violation(tmp_path: Path):
    """行尾注释形态的行内豁免同样放行。"""
    source = (
        "def big():  # lint:ignore[oversized_function] —— 已排期拆分，见 V2 计划\n"
        + "\n".join(f"    value_{index} = {index}" for index in range(60))
        + "\n"
    )
    path = _write_component(tmp_path, "big_export.py", source)

    result = analyze_component_file(path)

    assert "oversized_function" not in _rules(result)
    assert "invalid_ignore_comment" not in _rules(result)


def test_inline_ignore_above_except_handler_exempts_swallow(tmp_path: Path):
    """设计稿 §5.1 的示例形态：注释写在 except 语句的上一行也能放行。"""
    source = (
        "async def run(page):\n"
        "    try:\n"
        "        await page.click('#x')\n"
        "    # lint:ignore[swallow_exception_pattern] —— 探测型候选，失败即换下一个\n"
        "    except Exception:\n"
        "        continue\n"
    )
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "swallow_exception_pattern" not in _rules(result)
    assert "invalid_ignore_comment" not in _rules(result)


def test_file_ignore_exempts_the_whole_file(tmp_path: Path):
    """文件级豁免对整个文件生效。"""
    source = (
        "# lint:ignore-file[missing_report_step] —— 历史组件，暂无步骤上报\n"
        + COMPONENT_WITHOUT_REPORT_STEP
    )
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "missing_report_step" not in _rules(result)
    assert "invalid_ignore_comment" not in _rules(result)


def test_file_ignore_after_module_docstring_is_accepted(tmp_path: Path):
    """文件级豁免放在模块 docstring 之后同样生效。"""
    source = (
        '"""示例组件。"""\n'
        "# lint:ignore-file[missing_report_step] —— 历史组件，暂无步骤上报\n"
        + COMPONENT_WITHOUT_REPORT_STEP.split('"""示例组件。"""', 1)[1]
    )
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "missing_report_step" not in _rules(result)
    assert "invalid_ignore_comment" not in _rules(result)


def test_inline_ignore_without_reason_is_invalid(tmp_path: Path):
    """行内豁免没写理由时报 invalid_ignore_comment。"""
    source = (
        "def big():\n"
        "    # lint:ignore[oversized_function]\n"
        + "\n".join(f"    value_{index} = {index}" for index in range(60))
        + "\n"
    )
    path = _write_component(tmp_path, "big_export.py", source)

    result = analyze_component_file(path)

    assert "invalid_ignore_comment" in _rules(result)
    assert "oversized_function" in _rules(result)


def test_inline_ignore_with_short_reason_is_invalid(tmp_path: Path):
    """行内豁免理由少于 4 个字符时报 invalid_ignore_comment。"""
    source = (
        "def big():\n"
        "    # lint:ignore[oversized_function] 拆分\n"
        + "\n".join(f"    value_{index} = {index}" for index in range(60))
        + "\n"
    )
    path = _write_component(tmp_path, "big_export.py", source)

    result = analyze_component_file(path)

    assert "invalid_ignore_comment" in _rules(result)
    assert "oversized_function" in _rules(result)


def test_file_ignore_without_reason_is_invalid(tmp_path: Path):
    """文件级豁免没写理由时报 invalid_ignore_comment。"""
    source = "# lint:ignore-file[missing_report_step]\n" + COMPONENT_WITHOUT_REPORT_STEP
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "invalid_ignore_comment" in _rules(result)
    assert "missing_report_step" in _rules(result)


# --------------------------------------------------------------------------
# AST 扩展：吞异常
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler_body",
    [
        "        pass",
        "        continue",
        "        return None",
    ],
)
def test_ast_extension_detects_swallowed_exceptions(tmp_path: Path, handler_body: str):
    """AST 扩展覆盖 pass / continue / return 三种吞异常写法。"""
    source = (
        "async def run(page):\n"
        "    try:\n"
        "        await page.click('#x')\n"
        "    except Exception:\n"
        f"{handler_body}\n"
    )
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "swallow_exception_pattern" in _rules(result)


def test_ast_extension_allows_propagating_exception(tmp_path: Path):
    """重新抛出的 except 不算吞异常。"""
    source = (
        "async def run(page):\n"
        "    try:\n"
        "        await page.click('#x')\n"
        "    except Exception as exc:\n"
        "        raise RuntimeError('失败') from exc\n"
    )
    path = _write_component(tmp_path, "sample_export.py", source)

    result = analyze_component_file(path)

    assert "swallow_exception_pattern" not in _rules(result)


def test_code_level_rule_keeps_regex_behavior(tmp_path: Path):
    """录制器路径仍用原正则判定（只覆盖 pass 形态，行为零变化）。"""
    code = "try:\n    pass\nexcept Exception:\n    continue\n"

    result = analyze_python_code(code)

    assert "swallow_exception_pattern" not in _rules(result)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cli():
    """加载 scripts/lint_collection_components.py。"""
    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import lint_collection_components

    return lint_collection_components


def _unavailable_loader():
    """模拟 DB 不可用。"""
    raise StableRecordUnavailable("测试环境没有数据库")


def test_cli_reports_skip_line_when_database_unavailable(cli, tmp_path: Path, capsys):
    """DB 不可用时打印明确的 skip 行，且不产生仓库级命中。"""
    path = _write_component(tmp_path, "inventory_export.py", COMPONENT_WITH_REPORT_STEP)

    exit_code = cli.main(
        ["--paths", str(path), "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[SKIP]" in output
    assert "missing_stable_component_record" in output
    assert "stable_points_to_archived_file" in output


def test_cli_accepts_space_separated_paths(cli, tmp_path: Path, capsys):
    """--paths 能直接吃 CI 的空格分隔列表格式。"""
    first = _write_component(
        tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP
    )
    second = _write_component(
        tmp_path, "other_export.py", COMPONENT_WITHOUT_REPORT_STEP
    )

    exit_code = cli.main(
        ["--paths", f"{first} {second}", "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert str(first) in output
    assert str(second) in output
    assert "扫描文件数: 2" in output


def test_cli_json_output_is_machine_readable(cli, tmp_path: Path, capsys):
    """--format json 输出可被解析。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    cli.main(
        ["--paths", str(path), "--format", "json", "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["scanned_files"] == 1
    assert "missing_report_step" in payload["summary"]["by_rule"]
    assert payload["skipped"][0]["rules"] == [
        "missing_stable_component_record",
        "stable_points_to_archived_file",
    ]


def test_cli_fail_on_error_returns_exit_code_one(cli, tmp_path: Path, capsys):
    """命中 error 时退出码为 1。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    exit_code = cli.main(
        ["--paths", str(path), "--fail-on", "error"],
        loader=_unavailable_loader,
    )
    capsys.readouterr()

    assert exit_code == 1


def test_cli_fail_on_none_returns_zero(cli, tmp_path: Path, capsys):
    """--fail-on none 时即使有 error 也返回 0。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    exit_code = cli.main(
        ["--paths", str(path), "--fail-on", "none"],
        loader=_unavailable_loader,
    )
    capsys.readouterr()

    assert exit_code == 0


def test_cli_severity_filter_only_reports_errors(cli, tmp_path: Path, capsys):
    """--severity error 时只报告 error 级命中。"""
    path = _write_component(tmp_path, "sample_export.py", COMPONENT_WITHOUT_REPORT_STEP)

    cli.main(
        [
            "--paths",
            str(path),
            "--severity",
            "error",
            "--format",
            "json",
            "--fail-on",
            "none",
        ],
        loader=_unavailable_loader,
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["warnings"] == []
    assert payload["summary"]["warnings"] == 0
