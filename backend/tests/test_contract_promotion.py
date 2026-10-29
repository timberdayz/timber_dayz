"""契约晋升 —— 模板升级后, 被旧契约钉死的文件必须能自动放行。

背景
----
D7 的「契约优先」设计: 文件按**采集当时生效的那一版模板**解释, 模板升级**不自动**
让历史文件改用新版。这个设计是为了区分:

* **源文件结构变了** —— 需要人工更新模板
* **我们自己升级了模板** —— 不是源文件问题

但它有一个**未被覆盖的场景**: 采集那一刻模板就已经解释不了这个文件
(源文件结构先于模板发生了变化)。此时契约指向的模板**从此再也不可能**解释这个文件,
于是:

* 判定永远停在「结构漂移」
* 用户唯一能做的补救(把新字段补进模板并发布新版本)**完全不产生效果**
* 文件永远进不了入库队列

实测(tiktok/analytics/monthly, 2026-10-29): 文件 29 列(含「商品卡 GMV」),
契约指向 v6(28 列) ⇒ 永久漂移; 用户发布 v8(29 列, 与文件 **exact match**)
后**仍然**永久漂移 —— 因为契约没变, 用户做对了却看不到任何效果。

本文件锁死的不变量:
1. 契约基准漂移 + 当前已发布模板能解释 + **模板是事后追平的** => 放行 + 晋升信号
2. 契约基准漂移 + 当前已发布模板也解释不了 => 保持「待更新」(绝不误放行)
3. 契约基准漂移 + 当前已发布模板能解释, 但模板**早于**契约采集 => 仍阻断
   (D7 的「模板升级不自动让历史文件改用新版」不被破坏)
4. 契约基准本来就精确匹配 => 不走回退
5. 非契约基准(接管)不走回退
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.services.data_sync_status_semantics import (
    TEMPLATE_BASELINE_CONTRACT,
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    TEMPLATE_BASELINE_CURRENT,
)
from backend.services.data_sync_template_status_service import (
    DataSyncTemplateStatusService,
)
from backend.services.template_contract_service import (
    CONTRACT_SOURCE_PROMOTION,
    build_template_contract,
    promote_template_contract,
    read_template_contract,
)

T0 = datetime(2026, 10, 29, 7, 27, 49, tzinfo=timezone.utc)


# ── 测试替身 ─────────────────────────────────────────────────────────


def _template(template_id, version, *, columns=None, created_at=None):
    return SimpleNamespace(
        id=template_id,
        version=version,
        template_name=f"tpl_v{version}",
        status="published",
        header_row=8,
        header_columns=list(columns or []),
        created_at=created_at or T0,
        updated_at=created_at or T0,
    )


class _StubMatcher:
    """按模板 ID 给出不同结论 —— 模拟「旧模板漂移 / 新模板匹配」。"""

    def __init__(self, *, drift_template_ids, ready_template_ids, published=None):
        self.drift_template_ids = set(drift_template_ids)
        self.ready_template_ids = set(ready_template_ids)
        self.published = published
        self.calls = []

    async def find_best_template(self, **_kwargs):
        return self.published

    async def detect_header_changes(self, template_id, current_columns, account=None):
        self.calls.append(template_id)
        if template_id in self.drift_template_ids:
            return {
                "is_exact_match": False,
                "is_semantic_match": False,
                "detected": True,
                "added_fields": ["商品卡 GMV"],
                "removed_fields": [],
                "blocking_changes": ["商品卡 GMV"],
                "non_blocking_changes": [],
                "match_rate": 96.6,
            }
        if template_id in self.ready_template_ids:
            return {
                "is_exact_match": True,
                "is_semantic_match": True,
                "detected": False,
                "added_fields": [],
                "removed_fields": [],
                "blocking_changes": [],
                "non_blocking_changes": [],
                "match_rate": 100.0,
            }
        raise AssertionError(f"未预期的模板: {template_id}")


class _StubResolver:
    async def resolve(self, **_kwargs):
        return {}


class _StubDb:
    def __init__(self, templates):
        self.templates = templates

    async def get(self, _model, pk):
        return self.templates.get(int(pk))


def _catalog_file(contract):
    return SimpleNamespace(
        id=3019,
        platform_code="tiktok",
        data_domain="analytics",
        granularity="monthly",
        sub_domain=None,
        account=None,
        file_metadata={"template_contract": contract} if contract else {},
    )


def _service(templates, *, drift_template_ids, ready_template_ids, published=None):
    db = _StubDb(templates)
    service = DataSyncTemplateStatusService(db)
    service.template_matcher = _StubMatcher(
        drift_template_ids=drift_template_ids,
        ready_template_ids=ready_template_ids,
        published=published,
    )
    service.template_resolver = _StubResolver()
    return service


def _contract(template, *, captured_at=T0):
    contract = build_template_contract(template)
    contract["captured_at"] = captured_at.isoformat()
    return contract


async def _evaluate(
    service,
    *,
    contract_template,
    published_template,
    current_columns,
    baseline_kind=TEMPLATE_BASELINE_CONTRACT,
    captured_at=T0,
):
    contract = _contract(contract_template, captured_at=captured_at)
    catalog_file = _catalog_file(contract)
    return await service.evaluate_catalog_file(
        catalog_file,
        template=contract_template,
        current_columns=current_columns,
        sample_rows=[],
        header_row=8,
        baseline_template_override=contract_template,
        baseline_kind_override=baseline_kind,
        published_template=published_template,
    )


# ── 不变量 1: 事后追平 => 放行 + 晋升信号 ────────────────────────────


@pytest.mark.asyncio
async def test_promotion_releases_file_when_published_template_explains_it():
    """旧契约解释不了、新模板能解释, 且新模板是**事后**发布的 => 放行。"""
    contract_template = _template(368, 6)
    published_template = _template(372, 8, created_at=T0 + timedelta(hours=1))
    service = _service(
        {368: contract_template, 372: published_template},
        drift_template_ids={368},
        ready_template_ids={372},
    )

    status = await _evaluate(
        service,
        contract_template=contract_template,
        published_template=published_template,
        current_columns=["日期", "GMV", "商品卡 GMV"],
    )

    assert status["template_status"] == "ready"
    assert status["should_auto_sync"] is True
    # 生效模板必须换成新版本, 否则后续入库仍会按旧模板解析(丢掉新增字段)
    assert status["template_id"] == 372
    assert status["template_version"] == 8
    promotion = status["contract_promotion"]
    assert promotion["from_template_id"] == 368
    assert promotion["to_template_id"] == 372
    assert promotion["to_template_version"] == 8


# ── 不变量 2: 当前模板也解释不了 => 绝不误放行 ──────────────────────


@pytest.mark.asyncio
async def test_promotion_not_applied_when_published_template_also_drifts():
    """源文件结构真变了(新旧模板都漂移) => 保持「待更新」。"""
    contract_template = _template(368, 6)
    published_template = _template(372, 8, created_at=T0 + timedelta(hours=1))
    service = _service(
        {368: contract_template, 372: published_template},
        drift_template_ids={368, 372},
        ready_template_ids=set(),
    )

    status = await _evaluate(
        service,
        contract_template=contract_template,
        published_template=published_template,
        current_columns=["日期", "GMV", "商品卡 GMV"],
    )

    assert status["template_status"] == "update_required"
    assert status["should_auto_sync"] is False
    assert "contract_promotion" not in status


# ── 不变量 3: 模板早于契约 => 不算追平, D7 原语义不变 ───────────────


@pytest.mark.asyncio
async def test_promotion_not_applied_when_published_template_predates_contract():
    """当前已发布模板**早于**契约采集时刻 => 它就是登记时那一版 => 仍阻断。

    这是 D7「模板升级不自动让历史文件改用新版」的边界:
    我们自己升级模板时碰巧能解释这个文件, 不等于用户为这个文件追平了模板。
    """
    contract_template = _template(368, 6, created_at=T0 - timedelta(days=1))
    published_template = _template(372, 8, created_at=T0 - timedelta(hours=1))
    service = _service(
        {368: contract_template, 372: published_template},
        drift_template_ids={368},
        ready_template_ids={372},
    )

    status = await _evaluate(
        service,
        contract_template=contract_template,
        published_template=published_template,
        current_columns=["日期", "GMV", "商品卡 GMV"],
    )

    assert status["template_status"] == "update_required"
    assert status["should_auto_sync"] is False
    assert "contract_promotion" not in status


# ── 不变量 4: 契约本来就匹配 => 不走回退 ────────────────────────────


@pytest.mark.asyncio
async def test_promotion_skipped_when_contract_baseline_matches():
    """契约精确匹配时不许回退 —— 模板升级不得让历史文件误报漂移。"""
    contract_template = _template(368, 6)
    published_template = _template(372, 8, created_at=T0 + timedelta(hours=1))
    service = _service(
        {368: contract_template, 372: published_template},
        drift_template_ids=set(),
        ready_template_ids={368, 372},
    )

    status = await _evaluate(
        service,
        contract_template=contract_template,
        published_template=published_template,
        current_columns=["日期", "GMV"],
    )

    assert status["template_status"] == "ready"
    assert "contract_promotion" not in status
    # 基准仍然是契约模板
    assert status["baseline_template_id"] == 368


# ── 不变量 5: 非契约基准不走回退 ────────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_skipped_for_non_contract_baseline():
    """接管基准不走晋升 —— 接管有自己的落库路径(契约回填)。"""
    contract_template = _template(368, 6)
    published_template = _template(372, 8, created_at=T0 + timedelta(hours=1))
    service = _service(
        {368: contract_template, 372: published_template},
        drift_template_ids=set(),
        ready_template_ids={368, 372},
    )

    status = await _evaluate(
        service,
        contract_template=contract_template,
        published_template=published_template,
        current_columns=["日期"],
        baseline_kind=TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    )

    assert status["template_status"] == "ready"
    assert "contract_promotion" not in status
    assert status["template_baseline"] == TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT


# ── 契约写库 ─────────────────────────────────────────────────────────


def test_promote_template_contract_rewrites_contract_to_new_template():
    """晋升后契约指向新模板, 且留痕来源。"""
    catalog_file = SimpleNamespace(file_metadata={})
    template = _template(372, 8, columns=["日期", "GMV", "商品卡 GMV"])

    contract = promote_template_contract(catalog_file, template)

    assert contract is not None
    assert contract["template_id"] == 372
    assert contract["template_version"] == 8
    assert contract["source"] == CONTRACT_SOURCE_PROMOTION
    assert contract["column_count"] == 3

    stored = read_template_contract(catalog_file)
    assert stored["template_id"] == 372


def test_promote_template_contract_without_template_is_noop():
    """模板为空时不写任何东西。"""
    catalog_file = SimpleNamespace(file_metadata={})
    assert promote_template_contract(catalog_file, None) is None
    assert read_template_contract(catalog_file) is None


def test_build_template_contract_keeps_source_and_columns_hash():
    """晋升写出的契约必须能被 ``is_contract_baseline_valid`` 认可。"""
    from backend.services.template_contract_service import is_contract_baseline_valid

    template = _template(372, 8, columns=["日期", "GMV", "商品卡 GMV"])
    contract = build_template_contract(template, source=CONTRACT_SOURCE_PROMOTION)

    assert is_contract_baseline_valid(contract, template) is True


def test_parse_contract_captured_at_handles_missing_and_iso():
    """拿不到采集时刻时必须返回 None(调用方据此保守阻断)。"""
    from backend.services.template_contract_service import parse_contract_captured_at

    assert parse_contract_captured_at(None) is None
    assert parse_contract_captured_at({}) is None
    assert parse_contract_captured_at({"captured_at": "not-a-date"}) is None

    parsed = parse_contract_captured_at({"captured_at": T0.isoformat()})
    assert parsed is not None
    assert parsed == T0


# ── 重检落库: 恢复时必须把新契约写回去 ───────────────────────────────


@pytest.mark.asyncio
async def test_build_promoted_contract_returns_contract_from_signal():
    """重检路径: 有晋升信号 -> 算出新契约(不含旧契约)。"""
    from backend.tasks.scheduled_tasks import _build_promoted_contract

    template = _template(372, 8, columns=["日期", "GMV", "商品卡 GMV"])

    class _LocalDb:
        async def get(self, _model, _pk):
            return template

    contract = await _build_promoted_contract(
        _LocalDb(),
        {
            "contract_promotion": {
                "from_template_id": 368,
                "from_template_version": 6,
                "to_template_id": 372,
                "to_template_version": 8,
            }
        },
    )

    assert contract is not None
    assert contract["template_id"] == 372
    assert contract["source"] == CONTRACT_SOURCE_PROMOTION


@pytest.mark.asyncio
async def test_build_promoted_contract_without_signal_is_none():
    """没有晋升信号 -> 不产出契约(普通放行不该改契约)。"""
    from backend.tasks.scheduled_tasks import _build_promoted_contract

    class _LocalDb:
        async def get(self, _model, _pk):
            raise AssertionError("没有晋升信号时不该去取模板")

    assert await _build_promoted_contract(_LocalDb(), {"should_auto_sync": True}) is None


# ── 表头读取缓存 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_header_read_is_cached_by_file_mtime(monkeypatch, tmp_path):
    """同一文件重复读表头只解析一次 —— 治理看板要读 27 个组合的样本表头。"""
    from backend.services import spreadsheet_header_reader as shr

    target = tmp_path / "sample.xlsx"
    target.write_bytes(b"x")

    calls = []

    class _FakeColumns(list):
        def tolist(self):
            return list(self)

    class _FakeFrame:
        columns = _FakeColumns(["日期", "GMV"])

    def _fake_read_excel(_path, header=None, nrows=None):
        calls.append((header, nrows))
        return _FakeFrame()

    monkeypatch.setattr(shr, "_header_cache", {})
    monkeypatch.setattr(
        "backend.services.excel_parser.ExcelParser.detect_file_format",
        lambda _p: "xlsx",
    )
    monkeypatch.setattr(
        "backend.services.excel_parser.ExcelParser.read_excel",
        staticmethod(_fake_read_excel),
    )

    reader = shr.get_spreadsheet_header_reader(log_prefix="Test", use_cpu_executor=False)

    first = await reader.read_columns(str(target), header_row=0, nrows=5)
    second = await reader.read_columns(str(target), header_row=0, nrows=5)

    assert first.ok and second.ok
    assert list(second.columns) == ["日期", "GMV"]
    assert len(calls) == 1, "第二次读应该命中缓存, 不该再解析一次"
