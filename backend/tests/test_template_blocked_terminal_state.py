"""「没有可用模板」必须落终态 —— 防止无限重试闭环复发。

背景
----
「无模板」是**确定性结论**: 重试不会让模板凭空出现。

旧实现里, ``sync_single_file`` 遇到「无模板」只写了 ``auto_ingest`` 元数据,
**没有改 ``catalog_files.status``** —— 文件因此一直停在 ``processing``(进行中):

    兜底任务(每分钟)捞 pending -> 置 processing
      -> 同步任务跑 -> 无模板 -> skipped, 但 status 仍是 processing
      -> 看门狗看到 processing 超时 -> 判「任务卡死」-> 回退 pending
      -> 回到第一步 => 无限重试闭环

实测代价: 8 个文件 2 天内产生 72 次完全无效的同步任务, 占全库
single_file 任务总量的 39%, 而且用户看到的报错是「任务超时」—— 真实原因
根本不是超时。

本文件锁死三条不变量:
1. 无模板 -> catalog status 必须是终态(不是 processing)
2. 源文件也不在 -> 落 ``source_missing``(而不是误报「无模板」)
3. 兜底任务不再把「确定无模板」的文件塞回队列
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.services.cloud_sync_auto_recovery_service import (
    CloudSyncAutoRecoveryService,
)
from backend.services.data_sync_file_state_service import (
    apply_template_blocked_state,
    resolve_template_blocked_catalog_status,
)
from backend.services.data_sync_service import DataSyncService


# ── 纯函数: 终态归属 ────────────────────────────────────────────────


def test_template_blocked_catalog_status_depends_on_source_existence():
    """源文件还在 -> 等人工建模板; 源文件也没了 -> 等人工补文件。"""
    assert (
        resolve_template_blocked_catalog_status(source_exists=True)
        == "template_update_required"
    )
    assert resolve_template_blocked_catalog_status(source_exists=False) == "source_missing"


def test_apply_template_blocked_state_writes_status_reason_and_releases_claim():
    file_record = SimpleNamespace(
        status="processing",
        error_message=None,
        file_metadata={"auto_ingest": {"current_task_id": "single_file_1_abc"}},
    )

    landed = apply_template_blocked_state(
        file_record,
        target_status="template_update_required",
        reason="无模板(platform=miaoshou, domain=purchase), 需人工创建模板",
        status_info={"template_status": "missing", "governance_status": "missing_family"},
    )

    assert landed == "template_update_required"
    assert file_record.status == "template_update_required"
    assert "无模板" in file_record.error_message
    auto_meta = file_record.file_metadata["auto_ingest"]
    assert auto_meta["current_task_id"] is None
    assert auto_meta["last_template_status"] == "missing"
    assert auto_meta["last_governance_status"] == "missing_family"


# ── sync_single_file: 无模板落终态 ──────────────────────────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, file_record):
        self.file_record = file_record
        self.commit_calls = 0

    async def execute(self, _query):
        return _FakeResult(self.file_record)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        return None


class _NoTemplateResolverStub:
    async def resolve(self, **_kwargs):
        return None


class _NoTemplateMatcherStub:
    async def find_best_template(self, **_kwargs):
        return None


async def _no_contract_template(_catalog_file):
    return None


def _make_file_record(file_path, *, status="processing"):
    """模拟「兜底任务已认领」的真实状态。

    认领后 ``status=processing`` 且 ``auto_ingest.current_task_id`` 就是本次
    同步任务的 task_id —— sync_single_file 认得出来才会继续往下走,
    否则会被并发保护当成「别人正在跑」提前跳过。
    """
    return SimpleNamespace(
        id=2760,
        file_path=str(file_path),
        file_name="miaoshou_purchase_daily_20260914_134832.xlsx",
        status=status,
        error_message=None,
        file_metadata={"auto_ingest": {"current_task_id": "single_file_2760_test"}},
        data_domain="purchase",
        platform_code="miaoshou",
        source_platform="miaoshou",
        shop_id="xihong",
        granularity="daily",
        sub_domain=None,
        last_processed_at=None,
    )


@pytest.mark.asyncio
async def test_no_template_lands_terminal_state_instead_of_staying_processing(
    monkeypatch, tmp_path
):
    """无模板且源文件在 -> 落 template_update_required, 绝不能停在 processing。"""
    file_path = tmp_path / "miaoshou_purchase_daily.xlsx"
    file_path.write_bytes(b"x")
    file_record = _make_file_record(file_path)
    service = DataSyncService(_FakeDb(file_record))

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(file_path))
    monkeypatch.setattr(service, "template_resolver", _NoTemplateResolverStub())
    monkeypatch.setattr(service, "template_matcher", _NoTemplateMatcherStub())
    monkeypatch.setattr(service, "_resolve_contract_template", _no_contract_template)

    result = await service.sync_single_file(
        file_id=2760,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2760_test",
        use_template_header_row=True,
    )

    assert result["success"] is False
    assert result["error_code"] == "NO_TEMPLATE"
    # [*] 关键不变量: 不能停在 processing
    assert file_record.status == "template_update_required"
    assert file_record.status != "processing"
    # 错误信息要说清真实原因, 而不是「任务超时」
    assert "无模板" in file_record.error_message
    assert "超时" not in file_record.error_message
    assert "需人工创建模板" in file_record.error_message


@pytest.mark.asyncio
async def test_no_template_with_missing_source_file_lands_source_missing(
    monkeypatch, tmp_path
):
    """源文件已经不在磁盘上 -> 落 source_missing(不是误报「无模板」)。"""
    missing_path = tmp_path / "not_there.xlsx"
    file_record = _make_file_record(missing_path)
    service = DataSyncService(_FakeDb(file_record))

    monkeypatch.setattr(service, "_safe_resolve_path", lambda _path: str(missing_path))
    monkeypatch.setattr(service, "template_resolver", _NoTemplateResolverStub())
    monkeypatch.setattr(service, "template_matcher", _NoTemplateMatcherStub())
    monkeypatch.setattr(service, "_resolve_contract_template", _no_contract_template)

    await service.sync_single_file(
        file_id=2760,
        only_with_template=True,
        allow_quarantine=True,
        task_id="single_file_2760_test",
        use_template_header_row=True,
    )

    assert file_record.status == "source_missing"
    assert file_record.status != "processing"


# ── 兜底任务: 确定无模板的文件不再入队 ──────────────────────────────


class _FakeCatalogFile:
    def __init__(self, *, file_id, status="pending", platform_code=None, data_domain=None):
        self.id = file_id
        self.status = status
        self.first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        self.file_metadata = {}
        self.error_message = None
        self.file_path = "data/raw/2026/miaoshou_purchase_daily.xlsx"
        self.platform_code = platform_code
        self.data_domain = data_domain
        self.granularity = "daily"
        self.sub_domain = None


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values

    def scalar(self):
        return self._values


class _CountAwareSession:
    """按语句类型返回不同结果: count 查询 -> 计数, 其余 -> 文件列表。"""

    def __init__(self, files, *, family_count=0):
        self.files = files
        self.family_count = family_count
        self.committed = False

    @staticmethod
    def _is_count_query(stmt) -> bool:
        try:
            descriptions = stmt.column_descriptions
        except Exception:  # noqa: BLE001
            descriptions = []
        return any(
            str(item.get("name") or "").lower() == "count" for item in descriptions
        )

    def execute(self, stmt):
        if self._is_count_query(stmt):
            return _FakeScalarResult(self.family_count)
        return _FakeScalarResult(self.files)

    def commit(self):
        self.committed = True

    def rollback(self):
        return None


def test_auto_recovery_does_not_enqueue_file_whose_domain_has_no_template_family(
    monkeypatch,
):
    """同平台同数据域下没有任何模板族 -> 确定无模板 -> 不入队, 直接落终态。"""
    orphan = _FakeCatalogFile(
        file_id=2760, platform_code="miaoshou", data_domain="purchase"
    )
    session = _CountAwareSession([orphan], family_count=0)
    enqueued = []

    def fake_apply_async(*, kwargs, queue=None):
        enqueued.append(kwargs)
        raise AssertionError("确定无模板的文件不应入队")

    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        fake_apply_async,
    )
    monkeypatch.setattr(
        CloudSyncAutoRecoveryService, "_source_file_exists", lambda self, _f: True
    )

    service = CloudSyncAutoRecoveryService(session)
    result = service.enqueue_overdue_pending_catalog_files(limit=10, overdue_minutes=10)

    assert enqueued == []
    assert result["enqueued"] == 0
    assert result["blocked"] == 1
    assert result["blocked_file_ids"] == [2760]
    assert orphan.status == "template_update_required"
    assert orphan.status != "processing"
    assert session.committed is True


def test_auto_recovery_still_enqueues_when_domain_has_template_family(monkeypatch):
    """同域还有模板族 -> 保守放行(可能被同域其它粒度变体接管), 不误伤。"""
    candidate = _FakeCatalogFile(
        file_id=2761, platform_code="tiktok", data_domain="products"
    )
    session = _CountAwareSession([candidate], family_count=3)
    enqueued = []

    class _FakeTaskHandle:
        id = "celery-2761"

    def fake_apply_async(*, kwargs, queue=None):
        enqueued.append(kwargs)
        return _FakeTaskHandle()

    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        fake_apply_async,
    )

    service = CloudSyncAutoRecoveryService(session)
    result = service.enqueue_overdue_pending_catalog_files(limit=10, overdue_minutes=10)

    assert result["enqueued"] == 1
    assert result["blocked"] == 0
    assert result["file_ids"] == [2761]
    assert enqueued[0]["file_id"] == 2761
    assert enqueued[0]["task_id"].startswith("single_file_2761_")
