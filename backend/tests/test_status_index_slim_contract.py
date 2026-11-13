"""Contract test: 批次 F-2 —— Plans 状态索引（STATUS.md）的瘦身契约。

起因（2026-11-13，Walter 问「我们是不是越做越重了」）：

``docs/superpowers/plans/STATUS.md`` 当时是 **1,659 行 / 27 个章节**的混合体：
一半是「当前还没结的事」，另一半是**已经完结批次的历史流水账**（每个上线批次
都往里追加一大节）。后果有三个：

1. 真源被淹没 —— 新人（和未来的自己）翻 1,600 行才能找到「现在该干什么」；
2. 同一段历史只有一份真源的要求（律 1）被稀释 —— 章节散在各处，指来指去；
3. 台账自己成了「越做越重」的证据。

批次 F-2 的处置：**就地瘦身**（路径不变，CHANGELOG.md 有三处引用它），
只保留三样东西 —— **当前未结表**、**仍被外部引用的章节**、**进行中的批次**；
历史整体归档到 ``docs/superpowers/plans/archive/``，**内容逐字节保留、零删改**。

这份守护锁住瘦身成果，防止它重新长胖：

- STATUS.md 行数不得超过上限；
- 「当前未结」表的数据行不得超过 10 行；
- 归档文件必须存在、够长、且**逐条包含**被移走的每一个章节；
- 同一段历史只能有一处真源：被归档的章节标题不许再出现在 STATUS.md 里；
- CHANGELOG.md 引用到的章节名必须仍然可达；
- 这份守护自己必须进 CI 根契约清单（没人调用的守护不是守护）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = PROJECT_ROOT / "docs" / "superpowers" / "plans"
STATUS = PLANS_DIR / "STATUS.md"
ARCHIVE = PLANS_DIR / "archive" / "STATUS-2026-11-13-full-history.md"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

GUARD_RELATIVE = "backend/tests/test_status_index_slim_contract.py"

#: STATUS.md 的行数上限（瘦身后约 250 行，留出后续批次的余量）。
MAX_STATUS_LINES = 400

#: 「当前未结」表的数据行上限。
MAX_OPEN_ITEMS = 10

#: 归档文件至少要有这么多行（瘦身前是 1,659 行；低于此值说明历史丢了）。
MIN_ARCHIVE_LINES = 1500

#: 批次 F-2 移进归档的章节标题。逐条列出来，不靠正则猜。
ARCHIVED_SECTION_TITLES = (
    "Project Simplification (Phases 1–6)",
    "Shop Identity & Session Reuse (2026-11)",
    "Session Profile-Only Architecture (2026-11)",
    "Shop Identity Future-Proofing & Observability (2026-11)",
    "Batch 0 Reconciliation (2026-11)",
    "店铺身份「保未来」守护落地（2026-11-11）",
    "律 3 落地：候选集副本改为「从正本取数」（2026-11-11）",
    "v7.21.0 发布与部署后实测（2026-11-11）",
    "容器侧云端隧道地址修正（2026-11-11）",
    "PowerShell env 文件读取的编码修正（2026-11-11）",
    "采集任务状态 SSOT 收敛 + 文件系统护栏 + 日/周粒度废弃重采（2026-11-11）",
    "v7.22.0 上线 + 采集机真实采集实跑验收（2026-11-11）",
    "v7.23.0 上线 + 商品中心款货归属收敛 + 隧道看门狗（2026-11-12 ~ 11-13）",
    "API 契约门禁：扫描范围空转 + 告警口径失真（2026-11-13）",
    "v7.24.0 上线：门禁第一次真的看了路由代码（2026-11-13）",
    "安全发现：公开仓库里跟踪着一份「生产密码」文件（2026-11-13 补跑时发现）",
    "SSH 访问真源文档 + 守护测试（2026-11-13）",
    "商品中心 SKU 资料页 SPU 缺陷：方案已出，待拍板（2026-11-13）",
    "批次 A / B / C 全部实施完成（2026-11-13，本会话）",
    "v7.25.0 上线：商品中心 SPU 缺陷收口 + 接口去重挂载 + 密钥门禁补强（2026-11-13）",
    "本地同步云端 v7.26.0 + 双镜像一致性收尾（2026-11-13）",
    "批次 D：`.ps1` 编码约定被 v7.25.0 / v7.26.0 两批打破（2026-11-13）",
    "批次 E：Docker 残留治理 + testcontainers 收敛（2026-11-13）",
)

#: CHANGELOG.md 引用到的、必须仍然可达的章节名。
CHANGELOG_REFERENCED_SECTIONS = (
    "已知未落地项",
    "新增三个 CI 坑",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _headings(text: str) -> List[str]:
    """文件里的全部二级标题（去掉 ``## `` 前缀）。"""
    return [
        line[3:].strip()
        for line in text.splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    ]


def _open_items_table_rows(text: str) -> List[str]:
    """「当前未结」表的数据行（不含表头与分隔行）。"""
    rows: List[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = "当前未结" in line
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):
            continue
        if cells[0] in {"#", "序号"}:
            continue
        rows.append(stripped)
    return rows


# --------------------------------------------------------------------------
# 守护 1：STATUS.md 不能重新长胖
# --------------------------------------------------------------------------


def test_status_index_exists():
    assert STATUS.exists(), "状态索引必须在原路径存在: docs/superpowers/plans/STATUS.md"


def test_status_index_is_slim_enough():
    """行数上限 —— 防止「每个批次往里追加一大节」的老毛病复发。"""
    lines = len(_read(STATUS).splitlines())
    assert lines <= MAX_STATUS_LINES, (
        "STATUS.md 有 {0} 行，超过上限 {1} 行 —— 已完结的内容请归档，"
        "别再往索引里追加历史流水账（归档目录：docs/superpowers/plans/archive/）".format(
            lines, MAX_STATUS_LINES
        )
    )


def test_open_items_table_is_bounded():
    """「当前未结」表最多 10 行 —— 超过就说明「未结」在膨胀。"""
    rows = _open_items_table_rows(_read(STATUS))
    assert rows, "STATUS.md 里找不到「当前未结」表"
    assert (
        len(rows) <= MAX_OPEN_ITEMS
    ), "「当前未结」表有 {0} 行，超过上限 {1} 行 —— " "已经完结的请移进归档或勾掉，别让它一直挂着".format(
        len(rows), MAX_OPEN_ITEMS
    )


# --------------------------------------------------------------------------
# 守护 2：历史必须完整归档（不能借「瘦身」之名删信息）
# --------------------------------------------------------------------------


def test_archive_file_exists():
    assert ARCHIVE.exists(), "归档文件不存在: {0} —— 历史不许在瘦身时丢失".format(
        ARCHIVE.relative_to(PROJECT_ROOT)
    )


def test_archive_file_is_not_truncated():
    lines = len(_read(ARCHIVE).splitlines())
    assert (
        lines >= MIN_ARCHIVE_LINES
    ), "归档文件只有 {0} 行，低于下限 {1} 行 —— 历史被截断了？".format(
        lines, MIN_ARCHIVE_LINES
    )


@pytest.mark.parametrize("title", ARCHIVED_SECTION_TITLES)
def test_archived_section_is_in_archive(title: str):
    """被移走的每一个章节都必须逐字出现在归档文件里。"""
    headings = _headings(_read(ARCHIVE))
    assert title in headings, "归档文件里找不到章节「{0}」".format(title)


@pytest.mark.parametrize("title", ARCHIVED_SECTION_TITLES)
def test_archived_section_is_not_still_in_status_index(title: str):
    """同一段历史只能有一处真源 —— 不许同时留在索引里。"""
    headings = _headings(_read(STATUS))
    assert (
        title not in headings
    ), (
        "章节「{0}」既在归档文件里、又留在 STATUS.md 里 —— "
        "同一段历史只能有一处真源（律 1）".format(title)
    )


def test_archive_keeps_head_and_tail_of_the_original():
    """归档文件必须保留原文的首尾（证明是整体搬走，不是重新誊写）。"""
    text = _read(ARCHIVE)
    assert (
        "- Phase 1: `docs/superpowers/plans/2026-04-30-project-simplification-phase1-plan.md`"
        in text
    ), "归档文件丢失了原文开头 —— 归档必须是整体搬走，不是重新誊写"
    assert (
        "- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`"
        in text
    ), "归档文件丢失了原文结尾 —— 归档必须是整体搬走，不是重新誊写"


# --------------------------------------------------------------------------
# 守护 3：外部引用必须仍然可达
# --------------------------------------------------------------------------


@pytest.mark.parametrize("section", CHANGELOG_REFERENCED_SECTIONS)
def test_changelog_referenced_section_is_still_reachable(section: str):
    """CHANGELOG.md 引用到的章节名必须仍在 STATUS.md 里（就地瘦身，不许改名）。"""
    headings = _headings(_read(STATUS))
    assert (
        section in headings
    ), "CHANGELOG.md 引用的章节「{0}」在 STATUS.md 里不见了 —— " "STATUS.md 只能就地瘦身，不许改名或移动".format(
        section
    )


def test_status_index_path_is_unchanged():
    """路径不许变 —— CHANGELOG.md 有三处引用这个路径。"""
    changelog = _read(CHANGELOG)
    assert (
        "docs/superpowers/plans/STATUS.md" in changelog
    ), "CHANGELOG.md 里找不到 STATUS.md 的引用（引用可能已被改动）"
    assert (
        STATUS.parent.name == "plans"
    ), "STATUS.md 必须留在 docs/superpowers/plans/ 下"


# --------------------------------------------------------------------------
# 守护 4：这份守护自己必须进 CI 清单
# --------------------------------------------------------------------------


def test_guard_itself_is_in_ci_root_contract_list():
    """没人调用的守护不是守护。"""
    ci_text = _read(CI_WORKFLOW)
    assert (
        GUARD_RELATIVE in ci_text
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(GUARD_RELATIVE)


def test_archive_directory_is_not_git_ignored():
    """归档目录不能被 .gitignore 排除（否则「归档」等于「丢失」）。"""
    gitignore = PROJECT_ROOT / ".gitignore"
    if not gitignore.exists():
        return
    suspicious = []
    for line in _read(gitignore).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "plans/archive" in stripped or stripped.rstrip("/") in {
            "archive",
            "docs",
            "plans",
        }:
            suspicious.append(stripped)
    assert (
        not suspicious
    ), ".gitignore 里的 {0} 会把归档目录排除掉 ⇒ 归档等于丢失".format(suspicious)
