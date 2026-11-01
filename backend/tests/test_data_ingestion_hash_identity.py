from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "backend" / "services" / "data_ingestion_service.py"


def test_hash_scope_contains_stable_identity_keys():
    """data_hash 作用域必须包含稳定身份编号。

    注：``shop_id`` 键**保留**（它的取值现在是稳定 id 优先），因为当
    ``shop_account_id`` 未知时仍需要靠它区分店铺；直接删掉会造成同平台多店撞 hash。
    """
    text = TARGET.read_text(encoding="utf-8")
    hash_scope = text.split("hash_scope_values = {", 1)[1].split("}", 1)[0]
    assert "shop_account_id" in hash_scope, "hash 作用域缺少 shop_account_id"
    assert "platform_shop_id" in hash_scope, "hash 作用域缺少 platform_shop_id"


def test_ingestion_uses_resolve_file_identity():
    """文件级身份必须走 resolve_file_identity（Task 9 抽出的纯函数）。"""
    text = TARGET.read_text(encoding="utf-8")
    assert "resolve_file_identity" in text, "入库没有使用 resolve_file_identity"
    assert (
        "file_shop_id = resolve_file_identity(file_record)" in text
    ), "入库的文件级身份没有走 resolve_file_identity"


def test_hash_scope_keeps_shop_id_key():
    """``shop_id`` 键必须保留。

    当 ``shop_account_id`` / ``platform_shop_id`` 都拿不到时，
    仍需要靠 ``shop_id`` 区分同平台的多个店铺；直接删掉会造成同平台多店撞 hash。
    """
    text = TARGET.read_text(encoding="utf-8")
    hash_scope = text.split("hash_scope_values = {", 1)[1].split("}", 1)[0]
    assert '"shop_id"' in hash_scope, "hash 作用域不应删掉 shop_id 键"


def _scope_for(shop_account_id: str, *, raw_shop_id: str = "xihong") -> dict:
    """按入库链路的口径拼出 hash 作用域（``shop_id`` 取稳定身份编号）。"""
    from backend.services.data_ingestion_service import resolve_file_identity

    class _Record:
        platform_shop_id = None

        def __init__(self) -> None:
            self.shop_account_id = shop_account_id
            self.shop_id = raw_shop_id

    record = _Record()
    return {
        "platform_code": "tiktok",
        "shop_account_id": shop_account_id,
        "platform_shop_id": None,
        "shop_id": resolve_file_identity(record),
        "data_domain": "orders",
        "granularity": "monthly",
        "sub_domain": None,
    }


def test_hash_scope_survives_shop_rename():
    """改名后重新采集，去重作用域必须不变 —— 否则同一份数据会重复入库。

    这正是 Task 10 的核心口径：作用域里的店铺身份取**稳定身份编号**
    （shop_account_id），而不是会随改名变化的 shop_id。
    """
    from backend.services.deduplication_service import DeduplicationService

    before = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_sg_daone_mall_local", raw_shop_id="xihong")
    )
    after = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_sg_daone_mall_local", raw_shop_id="xihong_改名后")
    )

    assert before == after, "改名后去重作用域变了，同一份数据会重复入库"
    assert before["scope:shop_account_id"] == "tiktok_sg_daone_mall_local"


def test_hash_scope_separates_shops_of_same_platform():
    """同平台两个不同店铺账号，去重作用域必须不同 —— 不能撞 hash。"""
    from backend.services.deduplication_service import DeduplicationService

    left = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_sg_daone_mall_local")
    )
    right = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_my_tm_local")
    )

    assert left != right, "同平台不同店铺撞了去重作用域"
    assert left["scope:shop_account_id"] == "tiktok_sg_daone_mall_local"
    assert right["scope:shop_account_id"] == "tiktok_my_tm_local"


def test_hash_scope_uses_stable_identity_key_not_shop_id():
    """有稳定身份时，作用域里**不允许**再出现 shop_id 键。

    ``shop_id`` 随改名变化，它一旦留在作用域里，改名就会让同一份数据算出
    不同的 hash（重复入账）。稳定身份在场时，shop_id 不参与去重。
    """
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_sg_daone_mall_local", raw_shop_id="DAONE Mall")
    )

    assert "scope:shop_account_id" in scope
    assert "scope:shop_id" not in scope


def test_hash_scope_falls_back_to_platform_shop_id():
    """没有 shop_account_id 时用平台店铺ID（也是稳定身份）。"""
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": None,
            "platform_shop_id": "1407964586",
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )

    assert scope["scope:platform_shop_id"] == "1407964586"
    assert "scope:shop_id" not in scope


def test_hash_scope_falls_back_to_shop_id_when_no_stable_identity():
    """两个稳定身份都没有时，shop_id 是唯一的兜底（否则同平台多店会撞 hash）。"""
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": None,
            "platform_shop_id": None,
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )

    assert scope["scope:shop_id"] == "1407964586"
    assert "scope:shop_account_id" not in scope


def test_hash_scope_keeps_dimension_keys():
    """维度键必须保留（平台/数据域/粒度/子域）。"""
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        _scope_for("tiktok_sg_daone_mall_local")
    )

    assert scope["scope:platform_code"] == "tiktok"
    assert scope["scope:data_domain"] == "orders"
    assert scope["scope:granularity"] == "monthly"
    assert "scope:sub_domain" not in scope


def test_hash_scope_identity_is_single_key():
    """作用域里的身份键只能有一个。

    ``shop_account_id`` 与 ``platform_shop_id`` 在同一个店铺上一一对应，
    同时放进作用域不会增加区分度，却会让"后补一个字段"变成一次口径变更
    （回填 platform_shop_id 会让已算好的 hash 全部作废）。
    """
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": "shopee_sg_zewei_toys_local",
            "platform_shop_id": "1407964586",
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )

    identity_keys = [
        key
        for key in scope
        if key in ("scope:shop_account_id", "scope:platform_shop_id", "scope:shop_id")
    ]
    assert identity_keys == ["scope:shop_account_id"]


def test_hash_scope_ignores_blank_identity_values():
    """空串身份不能占住优先级（live 上 catalog_files 里空串和 NULL 都有）。"""
    from backend.services.deduplication_service import DeduplicationService

    scope = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": "   ",
            "platform_shop_id": "1407964586",
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )

    assert scope["scope:platform_shop_id"] == "1407964586"
    assert "scope:shop_account_id" not in scope


def test_hash_scope_is_stable_when_platform_shop_id_arrives_later():
    """后补 platform_shop_id 不得改变已确定的口径（幂等）。"""
    from backend.services.deduplication_service import DeduplicationService

    before = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": "shopee_sg_zewei_toys_local",
            "platform_shop_id": None,
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )
    after = DeduplicationService._build_scope_hash_data(
        {
            "platform_code": "shopee",
            "shop_account_id": "shopee_sg_zewei_toys_local",
            "platform_shop_id": "1407964586",
            "shop_id": "1407964586",
            "data_domain": "orders",
            "granularity": "monthly",
            "sub_domain": None,
        }
    )

    assert before == after, "后补 platform_shop_id 让口径变了（会造成重复入库）"
