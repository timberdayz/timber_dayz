"""发布即重检的**维度过滤**守护（2026-11-14）。

事故背景
--------

2026-11-14 14:32, 用户在治理面板保存 TikTok 订单月报模板三次,
接口返回 200、模板已成 v6/v7/v8, 但**该文件仍卡在「模板待更新」**,
直到 14:45 的定时巡检才被放行。

根因不是判定逻辑, 而是**维度过滤条件用错了值**:

* 文件 3059 的 ``catalog_files.sub_domain`` 是 ``NULL``（业务含义: 没有子类型）;
* 治理面板接口把空值渲染成字符串 ``"N/A"`` 返回给前端
  (``backend/domains/data_platform/routers/data_sync.py``:
  ``"sub_domain": sub_domain or "N/A"``);
* 前端保存模板时把这个**显示占位符原样回传**
  (``frontend/src/domains/data_platform/views/DataSyncTemplates.vue``:
  ``subDomain: template.sub_domain``);
* 发布即重检拿它当 SQL 条件查文件表 ⇒ ``sub_domain = 'N/A'``
  ⇒ 对 ``NULL`` **永远匹配不到** ⇒ 重检静默 0 命中、且一行日志都不打。

本文件锁住回归: 维度条件必须先归一, 且 0 命中必须留痕。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# 假 session: 只捕获语句, 不碰数据库
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> List[Any]:
        return list(self._rows)


class _FakeSession:
    """记录 ``execute`` 收到的语句。"""

    def __init__(self, rows: List[Any] | None = None) -> None:
        self.rows = list(rows or [])
        self.statements: List[Any] = []

    async def execute(self, statement: Any) -> _FakeResult:
        self.statements.append(statement)
        return _FakeResult(self.rows)


def _compiled_params(statement: Any) -> Dict[str, Any]:
    return dict(statement.compile().params)


# ---------------------------------------------------------------------------
# 1. 维度归一: 占位符不得进 SQL
# ---------------------------------------------------------------------------
def test_normalize_dimension_placeholder_maps_placeholders_to_none():
    from backend.services.template_matcher import normalize_dimension_placeholder

    for value in (
        "N/A",
        "n/a",
        " NA ",
        "none",
        "None",
        "null",
        "NULL",
        None,
        "",
        "   ",
    ):
        assert normalize_dimension_placeholder(value) is None, value

    # 真实维度值必须原样保留
    assert normalize_dimension_placeholder("agent") == "agent"
    assert normalize_dimension_placeholder("orders") == "orders"


@pytest.mark.asyncio
async def test_recheck_dimension_drops_na_placeholder_sub_domain():
    """``sub_domain='N/A'`` 不得变成 ``sub_domain = 'N/A'`` 这种永不命中的条件。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    fake = _FakeSession()
    summary = await TemplateRecheckService.recheck_dimension(
        fake,
        platform="tiktok",
        data_domain="orders",
        granularity="monthly",
        sub_domain="N/A",
        account=None,
    )

    assert summary == {
        "checked": 0,
        "released": 0,
        "still_blocked": 0,
        "file_ids": [],
    }

    params = _compiled_params(fake.statements[0])
    # 归一后为空 ⇒ 不加该维度条件(与 sub_domain=None 同一口径)
    assert not [name for name in params if "sub_domain" in name], params
    # 任何形态的占位符都不得进查询参数
    assert "N/A" not in [str(value) for value in params.values()], params


@pytest.mark.asyncio
async def test_recheck_dimension_keeps_real_sub_domain_condition():
    """真实维度值仍要作为条件(不能被归一吞掉)。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    fake = _FakeSession()
    await TemplateRecheckService.recheck_dimension(
        fake,
        platform="tiktok",
        data_domain="services",
        granularity="daily",
        sub_domain="agent",
        account=None,
    )

    params = _compiled_params(fake.statements[0])
    assert [name for name in params if "sub_domain" in name], params
    assert "agent" in [str(value) for value in params.values()], params


@pytest.mark.asyncio
async def test_recheck_dimension_normalizes_account_placeholder():
    """账号占位符同样要归一(模板 account 为空时不限账号)。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    fake = _FakeSession()
    await TemplateRecheckService.recheck_dimension(
        fake,
        platform="tiktok",
        data_domain="orders",
        granularity="monthly",
        sub_domain=None,
        account="N/A",
    )

    params = _compiled_params(fake.statements[0])
    assert not [name for name in params if "account" in name], params


# ---------------------------------------------------------------------------
# 2. 0 命中必须留痕(否则"漏检"与"本来就没有"长得一模一样)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recheck_dimension_logs_when_no_pending_files():
    """0 命中必须留痕。

    用 mock 直接断言 logger 调用 —— 仓库的 logger 自己接管了输出
    (``propagate`` 关闭), ``caplog`` 收不到。
    """
    from unittest.mock import patch

    from backend.services.template_recheck_service import TemplateRecheckService

    fake = _FakeSession()
    with patch("backend.services.template_recheck_service.logger") as fake_logger:
        await TemplateRecheckService.recheck_dimension(
            fake,
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain="N/A",
            account=None,
        )

    assert fake_logger.info.call_count >= 1, "0 命中时没有留下任何日志"
    first_arg = str(fake_logger.info.call_args_list[0].args[0])
    assert "[TemplateRecheck]" in first_arg, first_arg
    assert "无待更新文件" in first_arg, first_arg


# ---------------------------------------------------------------------------
# 3. 保存接口必须把重检结果带回(Pydantic 不再静默丢弃)
# ---------------------------------------------------------------------------
def test_template_save_data_keeps_recheck_field():
    """``recheck`` 曾经被 Pydantic 静默丢弃 ⇒ 前端永远拿不到三态。"""
    from backend.schemas.field_mapping_template import TemplateSaveData

    payload = TemplateSaveData(
        template_id=1,
        template_name="tiktok_orders__monthly_v1",
        version=1,
        operation="created",
        save_mode="new_version",
        recheck={"checked": 1, "released": 1, "still_blocked": 0, "file_ids": [1]},
    )
    assert payload.recheck is not None
    assert payload.recheck["released"] == 1
    assert "recheck" in payload.model_dump()


def test_template_save_data_recheck_defaults_to_none():
    from backend.schemas.field_mapping_template import TemplateSaveData

    payload = TemplateSaveData(
        template_id=1,
        template_name="tiktok_orders__monthly_v1",
        version=1,
        operation="created",
        save_mode="new_version",
    )
    assert payload.recheck is None


# ---------------------------------------------------------------------------
# 4. 覆盖统计: 「需要更新」行也必须带文件级结论
# ---------------------------------------------------------------------------
def test_needs_update_rows_carry_file_level_conclusion():
    """过去文件级结论只写在「已覆盖」行 ⇒ 前端在「需要更新」行拿不到。"""
    source = (
        REPO_ROOT / "backend" / "domains" / "data_platform" / "routers" / "data_sync.py"
    ).read_text(encoding="utf-8")

    marker = "needs_update_list.append("
    assert marker in source
    block = source.split(marker, 1)[1]
    block = block[: block.find("\n            )", 0)]
    for field in (
        "sample_template_status",
        "sample_update_required",
        "sample_governance_status",
        "sample_update_reason",
    ):
        assert f'"{field}"' in block, f"needs_update 行缺少 {field}"
