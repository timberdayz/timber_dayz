from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


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
