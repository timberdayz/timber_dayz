from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from modules.core.db import CatalogFile
from modules.core.file_naming import StandardFileName
from modules.services.metadata_manager import MetadataManager

REPO_ROOT = Path(__file__).resolve().parents[2]


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_resolve_file_identity_prefers_shop_account_id():
    """文件级身份必须优先用 shop_account_id（永不变化；店铺账号层 20/20 覆盖）。"""
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = "tiktok_sg_daone_mall_local"
        platform_shop_id = "123456"
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "tiktok_sg_daone_mall_local"


def test_resolve_file_identity_falls_back_to_platform_shop_id():
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = None
        platform_shop_id = "123456"
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "123456"


def test_resolve_file_identity_falls_back_to_raw_shop_id():
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = None
        platform_shop_id = None
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "xihong"


def test_resolve_file_identity_skips_blank_shop_account_id():
    """空串必须当"没有值"处理，不能占住最高优先级。

    live 上 ``public.catalog_files.shop_account_id`` 既有 NULL 也有空串
    （计划 Task 9 Step 5 的覆盖率口径正是 ``is not null and <> ''``），
    空串若被当成有效身份，会让同一店铺的不同文件算出不同 hash。
    """
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = "   "
        platform_shop_id = "123456"
        shop_id = "xihong"

    assert resolve_file_identity(_Record()) == "123456"


def test_resolve_file_identity_returns_none_when_nothing_available():
    """三者都拿不到时返回 "none"（与既有 ``file_record.shop_id or "none"`` 语义一致）。"""
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        shop_account_id = None
        platform_shop_id = None
        shop_id = None

    assert resolve_file_identity(_Record()) == "none"


# ---------------------------------------------------------------------------
# 身份反查（纯函数，无数据库）
# ---------------------------------------------------------------------------

ACCOUNTS = [
    {
        "id": 1,
        "shop_account_id": "shopee_sg_zewei_toys_local",
        "platform": "shopee",
        "main_account_id": "chenewei666:main",
        "store_name": "zewei_toys.sg",
        "platform_shop_id": "1407964586",
        "shop_region": "SG",
    },
    {
        "id": 2,
        "shop_account_id": "shopee_sg_zhengfu_local",
        "platform": "shopee",
        "main_account_id": "chenewei666:main",
        "store_name": "zhengfu.sg",
        "platform_shop_id": None,
        "shop_region": "SG",
    },
    {
        "id": 3,
        "shop_account_id": "tiktok_sg_daone_mall_local",
        "platform": "tiktok",
        "main_account_id": "tiktok_main",
        "store_name": "DAONE Mall",
        "platform_shop_id": None,
        "shop_region": "SG",
    },
    {
        "id": 4,
        "shop_account_id": "miaoshou_real_001",
        "platform": "miaoshou",
        "main_account_id": "miaoshou_real_001",
        "store_name": "xihong",
        "platform_shop_id": None,
        "shop_region": "",
    },
]

ALIASES = [
    {
        "shop_account_pk": 1,
        "platform": "shopee",
        "alias_normalized": "3c店",
        "is_active": True,
    },
    {
        "shop_account_pk": 3,
        "platform": "tiktok",
        "alias_normalized": "新加坡1店",
        "is_active": True,
    },
    {
        "shop_account_pk": 3,
        "platform": "tiktok",
        "alias_normalized": "已废弃店",
        "is_active": False,
    },
]


def test_match_shop_account_prefers_platform_shop_id_over_store_name():
    """平台店铺ID 是最稳的匹配键：命中它就不再看店铺名称。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="shopee",
        platform_shop_id="1407964586",
        store_name="zhengfu.sg",
    )

    assert matched is not None
    assert matched["shop_account_id"] == "shopee_sg_zewei_toys_local"
    assert matched["match_method"] == "platform_shop_id"


def test_match_shop_account_matches_store_name_in_same_platform():
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="tiktok",
        store_name="DAONE Mall",
    )

    assert matched is not None
    assert matched["shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert matched["match_method"] == "store_name"


def test_match_shop_account_matches_active_alias():
    """别名表命中也要能用（老文件里的标签是 'TK新加坡1店' 这类）。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="tiktok",
        shop_id="新加坡1店",
    )

    assert matched is not None
    assert matched["shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert matched["match_method"] == "alias"


def test_match_shop_account_ignores_inactive_alias():
    """停用别名不能命中（否则会把文件挂到已废弃的绑定上）。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="tiktok",
        shop_id="已废弃店",
    )

    assert matched is None


def test_match_shop_account_returns_none_when_store_name_is_ambiguous():
    """同平台同名店铺 -> 多候选 -> 保持 NULL（不猜）。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    accounts = ACCOUNTS + [
        {
            "id": 5,
            "shop_account_id": "shopee_sg_zhengfu_local_2",
            "platform": "shopee",
            "main_account_id": "chenewei666:main",
            "store_name": "zhengfu.sg",
            "platform_shop_id": None,
            "shop_region": "SG",
        }
    ]

    matched = match_shop_account_by_identity(
        accounts,
        ALIASES,
        platform_code="shopee",
        store_name="zhengfu.sg",
    )

    assert matched is None


def test_match_shop_account_returns_none_when_platform_shop_id_is_ambiguous():
    from modules.services.catalog_scanner import match_shop_account_by_identity

    accounts = ACCOUNTS + [
        {
            "id": 6,
            "shop_account_id": "shopee_sg_zewei_toys_local_dup",
            "platform": "shopee",
            "main_account_id": "chenewei666:main",
            "store_name": "other.sg",
            "platform_shop_id": "1407964586",
            "shop_region": "SG",
        }
    ]

    matched = match_shop_account_by_identity(
        accounts,
        ALIASES,
        platform_code="shopee",
        platform_shop_id="1407964586",
    )

    assert matched is None


def test_match_shop_account_uses_collection_source_platform():
    """业务平台与采集来源平台不一致时（miaoshou 代采）也要能反查到账号。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="shopee",
        source_platform="miaoshou",
        shop_id="xihong",
    )

    assert matched is not None
    assert matched["shop_account_id"] == "miaoshou_real_001"


def test_match_shop_account_returns_none_without_any_match():
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="tiktok",
        shop_id="不存在的店铺",
    )

    assert matched is None


def test_match_shop_account_ignores_none_sentinel_shop_id():
    """目录里的 'none' 是哨兵值，不能拿去反查。"""
    from modules.services.catalog_scanner import match_shop_account_by_identity

    matched = match_shop_account_by_identity(
        ACCOUNTS,
        ALIASES,
        platform_code="tiktok",
        shop_id="none",
    )

    assert matched is None


# ---------------------------------------------------------------------------
# 写入侧：采集登记路径必须写 shop_account_id
# ---------------------------------------------------------------------------


def _no_op_table_manager(monkeypatch):
    import backend.services.platform_table_manager as platform_table_manager_module

    monkeypatch.setattr(
        platform_table_manager_module,
        "get_platform_table_manager",
        lambda _session: type(
            "_NoopTableManager",
            (),
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_tiktok_orders_monthly")},
        )(),
    )


def _register_single_file(tmp_path, monkeypatch, *, resolved_identity):
    from modules.services import catalog_scanner as catalog_scanner_module
    from modules.services.catalog_scanner import register_single_file

    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    CatalogFile.__table__.create(engine)
    monkeypatch.setattr(catalog_scanner_module, "_get_engine", lambda: engine)
    _no_op_table_manager(monkeypatch)

    calls = []

    def _fake_resolve(session, **kwargs):
        calls.append(kwargs)
        return resolved_identity

    monkeypatch.setattr(
        catalog_scanner_module, "resolve_shop_account_by_identity", _fake_resolve
    )

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / StandardFileName.generate(
        source_platform="tiktok",
        data_domain="orders",
        granularity="monthly",
        timestamp="20260618_120000",
        ext="xlsx",
    )
    file_path.write_text("demo", encoding="utf-8")

    # 采集上下文里**没有** shop_account_id（老文件/老采集器）
    MetadataManager.create_meta_file(
        file_path,
        business_metadata={
            "source_platform": "tiktok",
            "data_domain": "orders",
            "granularity": "monthly",
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "shop_id": "DAONE Mall",
        },
        collection_info={
            "method": "python_component",
            "collection_platform": "tiktok",
            "account": "TK新加坡1店",
            "shop_id": "DAONE Mall",
            "original_path": r"temp\downloads\task-1\tiktok\acc\shop\orders\monthly\orders.xlsx",
            "collected_at": datetime.now().isoformat(),
        },
    )

    file_id = register_single_file(str(file_path))

    with Session(engine) as session:
        record = session.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one()

    return record, calls


def test_register_single_file_writes_resolved_shop_account_id(tmp_path, monkeypatch):
    """反查唯一命中时，catalog_files 必须写上 shop_account_id。"""
    record, calls = _register_single_file(
        tmp_path,
        monkeypatch,
        resolved_identity={
            "shop_account_id": "tiktok_sg_daone_mall_local",
            "main_account_id": "tiktok_main",
            "store_name": "DAONE Mall",
            "platform_shop_id": None,
            "shop_region": "SG",
            "match_method": "store_name",
        },
    )

    assert record.shop_account_id == "tiktok_sg_daone_mall_local"
    assert record.store_name == "DAONE Mall"
    assert calls, "写入前必须尝试反查店铺账号"


def test_register_single_file_keeps_shop_account_id_null_when_unresolved(tmp_path, monkeypatch):
    """反查不到（或多命中）时保持 NULL —— 不猜。"""
    record, _calls = _register_single_file(
        tmp_path, monkeypatch, resolved_identity=None
    )

    assert record.shop_account_id is None


def test_register_single_file_keeps_known_shop_account_id_from_collection_context(
    tmp_path, monkeypatch
):
    """采集上下文已经带了 shop_account_id 时，主路径优先，不再反查。"""
    from modules.services import catalog_scanner as catalog_scanner_module
    from modules.services.catalog_scanner import register_single_file

    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    CatalogFile.__table__.create(engine)
    monkeypatch.setattr(catalog_scanner_module, "_get_engine", lambda: engine)
    _no_op_table_manager(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise AssertionError("采集上下文已知身份时不应再反查")

    monkeypatch.setattr(
        catalog_scanner_module, "resolve_shop_account_by_identity", _boom
    )

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / StandardFileName.generate(
        source_platform="tiktok",
        data_domain="orders",
        granularity="monthly",
        timestamp="20260618_130000",
        ext="xlsx",
    )
    file_path.write_text("demo", encoding="utf-8")

    MetadataManager.create_meta_file(
        file_path,
        business_metadata={
            "source_platform": "tiktok",
            "data_domain": "orders",
            "granularity": "monthly",
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "shop_account_id": "tiktok_sg_daone_mall_local",
            "store_name": "DAONE Mall",
            "shop_id": "DAONE Mall",
        },
        collection_info={
            "method": "python_component",
            "collection_platform": "tiktok",
            "account": "TK新加坡1店",
            "shop_account_id": "tiktok_sg_daone_mall_local",
            "store_name": "DAONE Mall",
            "shop_id": "DAONE Mall",
            "original_path": r"temp\downloads\task-1\tiktok\acc\shop\orders\monthly\orders.xlsx",
            "collected_at": datetime.now().isoformat(),
        },
    )

    file_id = register_single_file(str(file_path))

    with Session(engine) as session:
        record = session.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one()

    assert record.shop_account_id == "tiktok_sg_daone_mall_local"


def test_file_registration_service_writes_shop_identity(tmp_path, monkeypatch):
    """上传登记路径也必须写店铺账号身份（原来这三个字段完全不写）。"""
    import backend.services.file_registration_service as registration_module
    from backend.services.file_registration_service import FileRegistrationService

    class _FakeCatalogFile:
        file_hash = None

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.added = []
            self.commits = 0

        def query(self, _model):
            return _FakeQuery()

        def add(self, obj):
            self.added.append(obj)

        def flush(self):
            return None

        def commit(self):
            self.commits += 1

        def rollback(self):
            return None

    monkeypatch.setattr(registration_module, "CatalogFile", _FakeCatalogFile)
    monkeypatch.setattr(
        registration_module.FileRegistrationService,
        "_resolve_identity",
        lambda self, **kwargs: {
            "shop_account_id": "shopee_sg_zewei_toys_local",
            "store_name": "zewei_toys.sg",
            "platform_shop_id": "1407964586",
        },
    )

    source = tmp_path / "shopee_orders_daily.xlsx"
    source.write_text("demo", encoding="utf-8")

    session = _FakeSession()
    service = FileRegistrationService(session, data_dir=str(tmp_path / "data"))
    catalog_file = service.register_file(
        source_path=str(source),
        task_id=None,
        platform="shopee",
        data_domain="orders",
        account="chenewei666_main",
        date_from="2026-06-01",
        shop_id="1407964586",
    )

    assert catalog_file.shop_account_id == "shopee_sg_zewei_toys_local"
    assert catalog_file.store_name == "zewei_toys.sg"
    assert catalog_file.platform_shop_id == "1407964586"
    assert session.added == [catalog_file]


# ---------------------------------------------------------------------------
# 回填脚本（纯计划函数）
# ---------------------------------------------------------------------------


def _catalog_row(**overrides):
    row = {
        "id": 1,
        "platform_code": "shopee",
        "source_platform": "shopee",
        "shop_id": "1407964586",
        "store_name": "zewei_toys.sg",
        "platform_shop_id": None,
        "shop_account_id": None,
        "main_account_id": None,
        "status": "ingested",
        "meta_file_path": None,
        "file_metadata": None,
    }
    row.update(overrides)
    return row


def test_backfill_plan_fills_unique_match():
    """唯一命中 -> 回填。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    plan = build_backfill_plan([_catalog_row()], ACCOUNTS, ALIASES)

    assert len(plan.updates) == 1
    update = plan.updates[0]
    assert update.shop_account_id == "shopee_sg_zewei_toys_local"
    assert update.match_method == "platform_shop_id"
    assert plan.filled_after == 1


def test_backfill_plan_lists_ambiguous_rows_as_pending():
    """多命中 -> 保持 NULL 并进入待处理清单（含命中数）。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    accounts = ACCOUNTS + [
        {
            "id": 7,
            "shop_account_id": "shopee_sg_zewei_toys_local_dup",
            "platform": "shopee",
            "main_account_id": "chenewei666:main",
            "store_name": "other.sg",
            "platform_shop_id": "1407964586",
            "shop_region": "SG",
        }
    ]

    plan = build_backfill_plan([_catalog_row()], accounts, ALIASES)

    assert plan.updates == []
    assert len(plan.pending) == 1
    pending = plan.pending[0]
    assert pending.reason == "ambiguous"
    assert pending.candidate_count == 2
    assert pending.file_count == 1
    assert pending.platform_code == "shopee"


def test_backfill_plan_is_idempotent_for_already_filled_rows():
    """已经填好的行不再产生更新（重复执行结果一致）。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    row = _catalog_row(shop_account_id="shopee_sg_zewei_toys_local")

    plan = build_backfill_plan([row], ACCOUNTS, ALIASES)

    assert plan.updates == []
    assert plan.already_filled == 1
    assert plan.filled_after == 1


def test_backfill_plan_flags_ingested_files_for_rebuild():
    """已入库且身份口径会变的文件必须进"需重建清单"（否则会重复入账）。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    plan = build_backfill_plan([_catalog_row()], ACCOUNTS, ALIASES)

    assert plan.updates[0].scope_changed is True
    assert plan.rebuild_file_ids == [1]


def test_backfill_plan_does_not_flag_pending_files_for_rebuild():
    """待处理（保持 NULL）的文件口径不变 -> 不需要重建。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    row = _catalog_row(platform_code="tiktok", source_platform="tiktok",
                       shop_id="不存在的店铺", store_name=None)

    plan = build_backfill_plan([row], ACCOUNTS, ALIASES)

    assert plan.updates == []
    assert plan.rebuild_file_ids == []
    assert plan.pending[0].reason == "not_found"


def test_backfill_plan_uses_meta_json_identity_as_primary_path(tmp_path):
    """.meta.json 里已经带了 shop_account_id 时直接用（采集上下文 = 主路径）。"""
    from backend.services.catalog_files_identity_backfill import build_backfill_plan

    meta_path = tmp_path / "demo.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "collection_info": {
                    "shop_account_id": "tiktok_sg_daone_mall_local",
                    "store_name": "DAONE Mall",
                    "shop_id": "DAONE Mall",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    row = _catalog_row(
        id=99,
        platform_code="tiktok",
        source_platform="tiktok",
        shop_id="DAONE Mall",
        store_name=None,
        meta_file_path=str(meta_path),
    )

    plan = build_backfill_plan([row], ACCOUNTS, ALIASES)

    assert len(plan.updates) == 1
    assert plan.updates[0].shop_account_id == "tiktok_sg_daone_mall_local"
    assert plan.updates[0].match_method == "meta_json"


def test_backfill_script_defaults_to_dry_run():
    """默认只读：不带 --apply 时不得写库。"""
    from backend.services import catalog_files_identity_backfill as backfill_module

    parser = backfill_module.build_parser()
    args = parser.parse_args([])

    assert args.apply is False
    assert args.dry_run is False

    apply_mode = bool(args.apply) and not args.dry_run
    assert apply_mode is False
