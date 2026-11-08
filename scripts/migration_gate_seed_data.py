"""迁移门禁的最小前置种子数据。

为什么需要它
------------
``current_migrations/versions/20261116_add_tiktok_export_store_name_aliases.py``
是一个**数据修复型迁移**: 它给 6 个已存在的 TikTok 店铺账号补「导出店名」别名,
并在动手前做 fail-closed 前置检查(账号存在 / 区域相符 / 已启用 / 是经营店 /
别名键没有被别人认领)。

在**全新空库**上, ``core.shop_accounts`` 里根本没有这些账号 ⇒ 前置检查必然失败
⇒ 整条迁移链在 20261116 中止 ⇒ ``scripts/validate_migrations_fresh_db.py``
这个「从零跑全量迁移」的门禁**永远跑不通**。

怎么修
------
两条路:

* (A) 改 20261116 的检查逻辑, 让它在空库上 no-op ——
  **不采用**: 已执行过的迁移不可改; 而且那样会让「全新部署的环境里 TikTok 导出
  别名不存在」这个**真实部署缺陷**被悄悄掩掉。
* (B) 让门禁脚本在跑迁移前注入**最小前置数据**, 使前置检查**有意义** ——
  **采用**。门禁脚本的职责本来就是「构造一个能跑通全量链的环境」,
  业务数据本就必须存在。

本模块只提供 (B) 需要的种子数据, 明确标注「仅供门禁使用」。

数据口径
--------
账号 id / 区域与 20261116 里硬编码的 ``_TIKTOK_EXPORT_ALIASES`` **逐字一致** ——
否则前置检查照样过不了。``store_name`` / ``main_account_id`` 是占位值,
因为前置检查不看这两项。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy import create_engine, text


#: 门禁种子用的主账号 id(占位, 不与任何真实环境冲突)。
GATE_MAIN_ACCOUNT_ID = "migration_gate_main"

#: 6 个 TikTok 导出别名账号 —— 与 20261116 的 ``_TIKTOK_EXPORT_ALIASES``
#: **逐字一致**(shop_account_id + 区域)。
#:
#: ⚠ 这份清单必须与迁移里的常量保持一致; 改动其中一边都要同步另一边,
#: 否则门禁会重新失败(而且失败信息是「账号不存在」, 不好定位)。
GATE_TIKTOK_ACCOUNTS: Tuple[Tuple[str, str], ...] = (
    ("tiktok_sg_daone_mall_local", "SG"),
    ("tiktok_my_dawie_mall_local", "MY"),
    ("tiktok_ph_explorers_mall_local", "PH"),
    ("tiktok_my_flora_mall_local", "MY"),
    ("tiktok_ph_daju_mall_local", "PH"),
    ("tiktok_sg_hx_home_local", "SG"),
)


def _main_account_row() -> Dict[str, Any]:
    return {
        "platform": "tiktok",
        "main_account_id": GATE_MAIN_ACCOUNT_ID,
        "username": GATE_MAIN_ACCOUNT_ID,
        # 门禁库里没有真实口令; 只要求 NOT NULL。
        "password_encrypted": "<migration-gate-placeholder>",
        "main_account_name": "迁移门禁种子主账号",
        "enabled": True,
    }


def _shop_account_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for shop_account_id, region in GATE_TIKTOK_ACCOUNTS:
        rows.append(
            {
                "platform": "tiktok",
                "shop_account_id": shop_account_id,
                "main_account_id": GATE_MAIN_ACCOUNT_ID,
                "store_name": "迁移门禁种子店 {sid}".format(sid=shop_account_id),
                "shop_region": region,
                "enabled": True,
                # business_role 默认就是 operating_store, 但显式写出来 ——
                # 20261116 的前置检查会核对这一项。
                "business_role": "operating_store",
            }
        )
    return rows


def seed_migration_gate_accounts(database_url: str) -> int:
    """注入门禁用的最小账号数据, 返回插入的行数(主账号 + 店铺账号)。

    幂等: 已存在的行会被跳过(``ON CONFLICT DO NOTHING``)。
    """
    engine = create_engine(database_url)
    inserted = 0
    try:
        with engine.begin() as connection:
            main_row = _main_account_row()
            result = connection.execute(
                text(
                    """
                INSERT INTO core.main_accounts (
                    platform,
                    main_account_id,
                    username,
                    password_encrypted,
                    main_account_name,
                    enabled
                )
                VALUES (
                    :platform,
                    :main_account_id,
                    :username,
                    :password_encrypted,
                    :main_account_name,
                    :enabled
                )
                ON CONFLICT DO NOTHING
                """
                ),
                main_row,
            )
            inserted += int(result.rowcount or 0)

            for shop_row in _shop_account_rows():
                result = connection.execute(
                    text(
                        """
                    INSERT INTO core.shop_accounts (
                        platform,
                        shop_account_id,
                        main_account_id,
                        store_name,
                        shop_region,
                        enabled,
                        business_role
                    )
                    VALUES (
                        :platform,
                        :shop_account_id,
                        :main_account_id,
                        :store_name,
                        :shop_region,
                        :enabled,
                        :business_role
                    )
                    ON CONFLICT DO NOTHING
                    """
                    ),
                    shop_row,
                )
                inserted += int(result.rowcount or 0)
    finally:
        engine.dispose()
    return inserted


def verify_seed_accounts(database_url: str) -> List[str]:
    """返回「缺失或属性不符」的账号 id 列表(空列表 = 全部就位)。"""
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                SELECT shop_account_id, shop_region, enabled, business_role
                FROM core.shop_accounts
                WHERE platform = 'tiktok'
                  AND shop_account_id = ANY(CAST(:ids AS text[]))
                """
                ),
                {"ids": [sid for sid, _ in GATE_TIKTOK_ACCOUNTS]},
            ).all()
    finally:
        engine.dispose()

    found = {str(row[0]): row for row in rows}
    problems: List[str] = []
    for shop_account_id, region in GATE_TIKTOK_ACCOUNTS:
        row = found.get(shop_account_id)
        if row is None:
            problems.append("账号不存在: {sid}".format(sid=shop_account_id))
            continue
        if str(row[1] or "").strip() != region:
            problems.append(
                "区域不符: {sid} 期望 {want}，实际 {got}".format(
                    sid=shop_account_id, want=region, got=row[1] or "(空)"
                )
            )
        if not row[2]:
            problems.append("账号已停用: {sid}".format(sid=shop_account_id))
        if str(row[3] or "") != "operating_store":
            problems.append(
                "不是经营店: {sid}(business_role={role})".format(
                    sid=shop_account_id, role=row[3]
                )
            )
    return problems


def gate_seed_account_ids() -> Iterable[str]:
    """门禁种子覆盖的账号 id(供测试断言用)。"""
    return (sid for sid, _ in GATE_TIKTOK_ACCOUNTS)
