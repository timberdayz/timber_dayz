"""Contract test for the frontend API method gate (``scripts/validate_frontend_api_methods.py``).

Background:
    The gate used to extract method definitions with a greedy ``[^)]*`` regex, so a
    parameter list containing parentheses (e.g. a Chinese comment such as
    ``(两级勾选的结果)``) truncated the match and made an existing method look
    undefined -> false positive that blocked the release pipeline.

    The fix masks comments/strings and matches the closing parenthesis by depth.
    These tests lock that behaviour in so the gate cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_frontend_api_methods import FrontendAPIMethodValidator


def _write_api(tmp_path: Path, content: str) -> Path:
    api_file = tmp_path / "index.js"
    api_file.write_text(content, encoding="utf-8")
    return api_file


def test_method_with_parenthesised_comment_in_parameters_is_detected(tmp_path):
    """参数列表里的中文注释带括号时，方法仍应被识别为已定义。"""
    api_file = _write_api(
        tmp_path,
        """
        export default {
          // 保存模板
          async saveTemplate({
            mappings,
            // [*] 版本级核心字段清单(两级勾选的结果)。
            coreFields = null
          }) {
            return mappings
          }
        }
        """,
    )

    methods = FrontendAPIMethodValidator().extract_api_methods(api_file)

    assert "saveTemplate" in methods


def test_method_with_nested_call_in_default_parameter_is_detected(tmp_path):
    """默认参数里带嵌套函数调用时，括号深度匹配仍应正确闭合。"""
    api_file = _write_api(
        tmp_path,
        """
        export default {
          async buildRows(options = makeOptions(1, 2)) {
            return options
          }
        }
        """,
    )

    methods = FrontendAPIMethodValidator().extract_api_methods(api_file)

    assert "buildRows" in methods


def test_plain_call_inside_body_is_not_treated_as_method_definition(tmp_path):
    """函数体里的普通调用不应被当成方法定义。"""
    api_file = _write_api(
        tmp_path,
        """
        export default {
          async loadData() {
            const res = await request(url)
            return res
          }
        }
        """,
    )

    methods = FrontendAPIMethodValidator().extract_api_methods(api_file)

    assert "loadData" in methods
    assert "request" not in methods


def test_string_literal_containing_paren_is_masked(tmp_path):
    """字符串字面量里的括号不应干扰参数边界。"""
    api_file = _write_api(
        tmp_path,
        """
        export default {
          async fetchList(path = "/a(b)c") {
            return path
          }
        }
        """,
    )

    methods = FrontendAPIMethodValidator().extract_api_methods(api_file)

    assert "fetchList" in methods


def test_real_api_file_defines_save_template():
    """真实 API 封装层里 ``saveTemplate`` 必须被识别（历史误报点）。"""
    validator = FrontendAPIMethodValidator()
    methods = validator.extract_api_methods(
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "index.js"
    )

    assert "saveTemplate" in methods
    assert len(methods) > 100


@pytest.mark.parametrize("keyword", ["if", "for", "while", "catch", "delete"])
def test_js_keywords_are_not_collected_as_methods(tmp_path, keyword):
    """JS 关键字不得被当成方法名（它们只是控制流，不是 API 方法）。"""
    api_file = _write_api(
        tmp_path,
        """
        export default {
          async run() {
            %s (true) {
              return 1
            }
          }
        }
        """
        % keyword,
    )

    methods = FrontendAPIMethodValidator().extract_api_methods(api_file)

    assert keyword not in methods
