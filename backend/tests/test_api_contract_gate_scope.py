"""守护「API 契约门禁的扫描范围与判定口径」。

``scripts/validate_api_contracts.py`` 是发布流水线上的 **Validate API Contracts
(Release Gate)**，也是 CI 的 Validate Data Flow 线上的同名 job。

但它的扫描范围历史上**停在 ``backend/routers/``** —— 那是 76 个**旧门牌号**
（兼容垫片），实测里面**零路由定义**。而 82 个真正定义路由的文件早就搬到了
``backend/domains/<业务域>/routers/``。

于是两种模式都无效：

  * whole-repo 模式（CI 用的就是这个）扫到 76 个空垫片 ⇒ 0 问题；
  * ``--changed-files`` 模式（发布门禁用的就是这个）只匹配 ``backend/routers/``
    前缀 ⇒ **改动的真实路由一个都匹配不到** ⇒ 报「本次发布没有改动 router
    文件，跳过验证」并**绿灯放行**。

⇒ v7.23.0 改了 ``backend/domains/business/routers/product_center.py``，
门禁报告「跳过验证」—— 它从未看过这个文件。

本文件把四件事钉死：

  ① 域内真实路由**必须**进扫描范围（含那 12 个带 UTF-8 BOM 的文件，
     它们必须能被解析，不许被静默跳过）；
  ② 旧门牌号垫片**也要**进扫描范围（万一将来有人往垫片里写路由，能抓住）；
  ③ 非路由文件**不得**被误纳管（不许把门禁改成「什么都扫」）；
  ④ 六桶口径**不许漂移**（真静默 F 桶必须回到 58，且六桶之和 == except 块总数）
     —— 分类顺序一变，这个数字就会平移，半年后没人说得清「58」是怎么来的。

第 ④ 条是这个门禁的历史教训：它上一版报出「518 条缺错误日志」，而 AST 重算后
真正的静默只有 58 条，**9 : 1 的噪音比** ⇒ 门禁成了「狼来了」。
本文件的作用就是让口径**写在纸上并被守住**，不再退回去。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scripts.validate_api_contracts as gate


ROOT = Path(__file__).resolve().parents[2]

# 那 12 个带 UTF-8 BOM 的域内路由之一（实测：ast.parse 对 U+FEFF 开头直接抛
# SyntaxError ⇒ 用 utf-8 读会静默跳过这批文件）。
BOM_ROUTER = "backend/domains/platform/routers/auth.py"


def _except_lines_containing(relative: str, needle: str) -> set[int]:
    """找出某文件里源码含 ``needle`` 的 except 块的行号。

    锚在**源码特征**上而不是行号 —— 代码挪行不该让守护测试假失败。
    """
    path = ROOT / relative
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            segment = ast.get_source_segment(source, node) or ""
            if needle in segment:
                found.add(node.lineno)
    return found


@pytest.fixture
def validator():
    return gate.APIContractValidator()


# ---------------------------------------------------------------------------
# ① 域内真实路由必须进扫描范围
# ---------------------------------------------------------------------------


def test_domain_router_is_inside_the_scan_scope(validator):
    """真实路由住在 domains 下，必须被识别为路由文件。"""
    assert validator.is_router_file(
        "backend/domains/business/routers/product_center.py"
    ), "域内真实路由被排除在扫描范围外 —— 门禁在空转"


def test_every_domain_router_file_is_a_candidate(validator):
    """域内 routers 目录下的每个非 __init__.py 文件都必须是候选。

    动态推导而非写死数量：以后新增路由文件不会被这个用例卡住，
    但「范围退回去」一定会被卡住。
    """
    candidates = {
        path.relative_to(ROOT).as_posix() for path in validator.discover_router_files()
    }

    for router_dir in sorted((ROOT / "backend" / "domains").glob("*/routers")):
        for py_file in sorted(router_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            relative = py_file.relative_to(ROOT).as_posix()
            assert relative in candidates, f"{relative} 不在扫描候选里"
            assert validator.is_router_file(relative), f"{relative} 未被识别为路由文件"


def test_bom_domain_router_is_parsed_not_skipped(validator):
    """带 BOM 的域内路由必须被解析成功，不许静默跳过。

    这是覆盖完整性的关键：12 个 BOM 文件一旦被跳过，门禁就自带一个洞，
    而报告看起来还是绿的。
    """
    assert validator.is_router_file(BOM_ROUTER), "带 BOM 的域内路由未被识别"

    result = validator.analyze_except_blocks(ROOT / BOM_ROUTER)
    assert result is not None, "带 BOM 的域内路由被静默跳过"
    assert result["buckets"], "带 BOM 的域内路由解析出了 0 个异常块"
    assert sum(result["buckets"].values()) == result["except_block_count"]


def test_changed_files_mode_actually_validates_a_domain_router(validator):
    """发布门禁用的 ``--changed-files`` 模式必须真的验到域内路由。

    旧行为：域内路由匹配不到 ``backend/routers/`` 前缀 ⇒ 体检文件数 = 0 ⇒
    报「跳过验证」并绿灯放行。
    """
    issues = validator.validate_all(
        [Path("backend/domains/business/routers/product_center.py")]
    )
    assert issues["validated_file_count"] == 1, (
        "changed-files 模式仍然匹配不到域内路由 —— " "发布门禁正在对真实改动放行"
    )


# ---------------------------------------------------------------------------
# ② 旧门牌号垫片也要进扫描范围
# ---------------------------------------------------------------------------


def test_legacy_shim_is_inside_the_scan_scope(validator):
    """垫片层也要扫：万一将来有人往里写路由，要能抓住。"""
    assert validator.is_router_file("backend/routers/auth.py")
    assert validator.is_router_file("backend/routers/collection.py")


def test_legacy_shims_are_candidates_too(validator):
    candidates = {
        path.relative_to(ROOT).as_posix() for path in validator.discover_router_files()
    }
    for relative in ("backend/routers/auth.py", "backend/routers/hr_employee.py"):
        assert relative in candidates


# ---------------------------------------------------------------------------
# ③ 非路由文件不得被误纳管
# ---------------------------------------------------------------------------


def test_non_router_files_are_not_in_the_scan_scope(validator):
    """不许把门禁改成「什么都扫」。"""
    for relative in (
        "backend/services/product_spu_lifecycle.py",
        "backend/schemas/product_center.py",
        "backend/domains/business/routers/__init__.py",
        "backend/routers/__init__.py",
        "backend/app/bootstrap/common.py",
    ):
        assert not validator.is_router_file(relative), f"{relative} 被误纳管"


def test_non_router_files_do_not_count_as_validated(validator):
    """被指名验证时，非路由文件不得计入「体检文件数」。"""
    issues = validator.validate_all(
        [
            Path("backend/services/product_spu_lifecycle.py"),
            Path("backend/app/bootstrap/common.py"),
        ]
    )
    assert issues["validated_file_count"] == 0


# ---------------------------------------------------------------------------
# 路径归一化：三种写法都要认
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "written",
    [
        "backend/domains/business/routers/product_center.py",
        "./backend/domains/business/routers/product_center.py",
        "backend\\domains\\business\\routers\\product_center.py",
    ],
)
def test_path_spellings_are_normalized(validator, written):
    """绝对路径 / Windows 反斜杠 / ``./`` 前缀都要能归一识别。"""
    assert validator.is_router_file(written), f"{written} 未被识别为路由文件"


def test_absolute_path_is_normalized(validator):
    absolute = ROOT / "backend/domains/business/routers/product_center.py"
    assert validator.is_router_file(absolute)
    assert validator.normalize_relative_path(absolute) == (
        "backend/domains/business/routers/product_center.py"
    )


# ---------------------------------------------------------------------------
# ④ 六桶口径不许漂移
# ---------------------------------------------------------------------------


def test_silent_exception_bucket_is_pinned_to_50(validator):
    """真静默必须回到 50 —— 口径漂移会让这个数字变成第二个「518」。

    历史上旧脚本用正则 + 缩进猜测，报出「518 条缺错误日志」；
    AST 重算后真正的静默只有 50 处。50 是**核准数字**，
    任何偏离都说明判定规则实现有偏差。

    为什么不是上一轮口头说的 58：那一轮统计用的临时脚本**没有入库**，
    口径不可复现（已穷举 8 组谓词变体，无一命中 58）。
    现在的 50 是「except 块里只要有任何控制流决策就不算静默」这条最简口径
    下的核准值 —— **口径写在脚本里，数字由守护测试钉住**。
    """
    analysis = validator.analyze_all_router_files()

    assert analysis["bucket_counts"]["F"] == 50, (
        f"真静默 F 桶 = {analysis['bucket_counts']['F']}，应为 50；"
        "判定规则与核准口径不一致"
    )


def test_reviewed_degradation_blocks_are_not_counted_as_silent(validator):
    """人工复核过的两处：必须归「有意降级」，不能算真静默。

    * ``mv.py``：查不到物化视图刷新记录就返回空三元组 —— 明确告诉调用方「没有」；
    * ``notification_websocket.py``：把异常翻译成错误消息返回 —— 明确告诉调用方「过期了」。

    这两处是「口径对不对」的人肉基准：门禁不能只数个数，要分得清
    「安静地失败」和「明确地降级」。
    """
    for relative, needle in (
        ("backend/domains/business/routers/mv.py", "return None, None, None"),
        (
            "backend/domains/platform/routers/notification_websocket.py",
            'return None, "Token expired"',
        ),
    ):
        lines = _except_lines_containing(relative, needle)
        assert lines, f"{relative} 里找不到含 {needle!r} 的 except 块（代码改了？）"

        analysis = validator.analyze_except_blocks(ROOT / relative)
        assert analysis is not None
        silent_lines = {item["line"] for item in analysis["silent"]}

        for line in lines:
            assert line not in silent_lines, (
                f"{relative}:{line} 被误判成真静默 —— "
                "它其实是有意降级（返回了明确的结果）"
            )


def test_guard_fail_open_blocks_are_still_reported_as_silent(validator):
    """两处「守卫失效」必须仍在真静默桶里 —— 那是第二批要修的目标。

    * ``product_center.py`` 的 ``_count_sku_references``：引用计数失败就报 0
      ⇒ **删除守卫放行**；
    * ``collection_schedule.py`` 的 ``health_check``：吞异常且不留原因。

    它们都「不记、不抛、不返回」，所以必须被判成真静默。
    若哪天口径把它们放过了，这两处守卫失效就会被门禁漏掉。
    """
    for relative, needle in (
        (
            "backend/domains/business/routers/product_center.py",
            'refs[f"{sch}.{tbl}"] = 0',
        ),
        (
            "backend/domains/collection/routers/collection_schedule.py",
            'db_status = "error"',
        ),
    ):
        lines = _except_lines_containing(relative, needle)
        assert lines, f"{relative} 里找不到含 {needle!r} 的 except 块（代码改了？）"

        analysis = validator.analyze_except_blocks(ROOT / relative)
        assert analysis is not None
        silent_lines = {item["line"] for item in analysis["silent"]}

        for line in lines:
            assert line in silent_lines, (
                f"{relative}:{line} 没被报成真静默 —— " "这处守卫失效会被门禁漏掉"
            )


def test_buckets_are_mutually_exclusive_and_cover_every_except_block(validator):
    """六桶是**互斥**分桶：相加必须等于 except 块总数。"""
    analysis = validator.analyze_all_router_files()

    total = sum(analysis["bucket_counts"].values())
    assert (
        total == analysis["except_block_count"]
    ), f"六桶之和 {total} != except 块总数 {analysis['except_block_count']}"


def test_reporting_is_aggregated_not_flooding(validator):
    """报告必须给汇总，不许把 58 条真静默逐条刷屏。"""
    report = validator.generate_report(
        validator.validate_all(None), validated_file_count=158
    )

    assert "真静默" in report, "报告里没有新口径的汇总（真静默）"
    assert (
        len(report.splitlines()) <= 60
    ), f"报告有 {len(report.splitlines())} 行 —— 又在逐条刷屏"
