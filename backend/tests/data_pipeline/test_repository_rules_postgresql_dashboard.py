"""仓库规则文件对 PostgreSQL 看板架构的说明守护。

⚠️ 规则入口只有一个
--------------------
* ``AGENTS.md`` 是**唯一活动规则入口**;
* ``CLAUDE.md`` 已于 2026-05-22(commit ``f79b2593``「feat:规则大改」)收敛成
  「薄适配器」—— 只指向 ``AGENTS.md`` 与 ``docs/*``, 不再复述运行时架构;
* ``.cursorrules`` 与 ``.cursor/rules/skill-integration.mdc`` 在同一个提交里被
  **删除**, 且 ``AGENTS.md`` 明确写了它们「不作为活动规则源」
  ⇒ 不再把它们当规则文件来校验。
"""

from pathlib import Path


def test_repository_rule_files_reference_postgresql_dashboard_architecture():
    files = {
        "AGENTS.md": [
            "Dashboard",
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "Metabase",
        ],
        "CLAUDE.md": [
            "AGENTS.md",
            "docs/DEVELOPMENT_RULES/README.md",
            "docs/architecture/README.md",
        ],
        "docs/DEVELOPMENT_RULES/README.md": [
            "PostgreSQL",
            "semantic",
            "mart",
            "api",
            "dashboard",
        ],
    }

    for path_str, required_terms in files.items():
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")
        for term in required_terms:
            assert term in text


def test_retired_cursor_rule_files_are_not_active_rule_sources():
    """退役的游标规则文件不得复活, 且 AGENTS.md 要写明它们不是规则源。"""
    assert not Path(".cursorrules").exists()
    assert not Path(".cursor/rules/skill-integration.mdc").exists()

    agents_text = Path("AGENTS.md").read_text(encoding="utf-8", errors="replace")
    assert ".cursorrules" in agents_text
    assert ".cursor/rules/*" in agents_text
