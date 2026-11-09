"""全新环境的引导清单（bootstrap manifest）—— 「空库从零建库」的唯一真相点。

问题
----
``current_schema_20261116_add_tiktok_export_store_name_aliases`` 是**数据修复型**迁移：
它给 6 个**已存在的** TikTok 店铺账号补「导出店名」别名，动手前做 fail-closed 前置检查
（账号存在 / 区域相符 / 已启用 / 是经营店 / 别名键没被别人认领）。

全新空库上 ``core.shop_accounts`` 里根本没有这些账号 ⇒ 前置检查必然失败
⇒ 整条链在 20261116 中止 ⇒ **任何「从零建库」的路径都跑不通**。

实测影响到的真实调用方（不止门禁）：

* ``scripts/rebuild_local_current_schema.py`` —— drop 库 → create 空库 → 跑迁移
  ⇒ 它没有任何种子步骤 ⇒ 卡在 20261116；
* ``docker-compose.prod.yml`` / ``docker-compose.dev.yml`` 的 ``migrate`` 服务
  —— 直接跑 ``scripts/run_current_schema_migrations.py`` ⇒ 同样卡在 20261116；
* ``docker/scripts/backend-entrypoint.sh`` —— 启动时跑同一个 runner。

为什么是「两段式引导」，而不是改迁移
------------------------------------
* 已应用过的迁移文件**不可改**（``20260914_warehouse_platform_profit.py:3``：
  "Previous migration files remain immutable"）；
* 在 20261116 之前插入一个新修订也不行 —— 链是**严格线性**的，插一个修订就必须改
  20261116 的 ``down_revision``，那同样是改已应用文件；
* 让迁移在空库上 no-op 更不可接受 —— 那会把「全新环境缺 TikTok 导出别名」这个
  **真实部署缺陷**悄悄掩掉。

⇒ 唯一不动迁移的做法是**两段式**：

1. 先把链跑到 **20261116 的前一个节点** ``current_schema_20261115_add_sku_platform_pricing``
   （此时 ``core.main_accounts`` / ``core.shop_accounts`` 已由更早的迁移建好）；
2. 注入引导账号（主账号 + 6 个 TikTok 出口账号）；
3. 再把链跑到 head。

本模块是这套流程的**唯一实现**，两种 profile 共用：

* ``gate`` profile —— 占位值，仅供「临时库迁移门禁」使用
  （``scripts/validate_migrations_fresh_db.py``）；
* ``operator`` profile —— 真实环境由运维提供真实值（主账号凭据、6 个店的显示名）。

清单本身与迁移里的常量**逐字对应**，由 ``backend/tests/test_bootstrap_seed_manifest.py``
守护（漂移即红），避免「两边各改一份、报错还定位不到」的老问题。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from sqlalchemy import create_engine, text


#: 20261116 的**前一个**节点 —— 第一段迁移停在这里。
#:
#: 它同时是 20261116 的 ``down_revision``，由守护测试校验（防止迁移被改挂）。
PRECHECK_TARGET_REVISION = "current_schema_20261115_add_sku_platform_pricing"

#: 需要引导账号的那一步迁移。
BOOTSTRAP_REVISION = "current_schema_20261116_add_tiktok_export_store_name_aliases"

#: 门禁 profile 的主账号 id（占位，不与任何真实环境冲突）。
GATE_MAIN_ACCOUNT_ID = "migration_gate_main"

#: 引导账号所属平台。
BOOTSTRAP_PLATFORM = "tiktok"

#: 引导账号必须是经营店 —— 20261116 的前置检查会核对这一项。
BOOTSTRAP_BUSINESS_ROLE = "operating_store"


@dataclass(frozen=True)
class BootstrapShopAccount:
    """一个必须在新环境里存在的店铺账号。"""

    shop_account_id: str
    shop_region: str
    alias_value: str
    alias_normalized: str
    platform: str = BOOTSTRAP_PLATFORM
    business_role: str = BOOTSTRAP_BUSINESS_ROLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shop_account_id": self.shop_account_id,
            "shop_region": self.shop_region,
            "alias_value": self.alias_value,
            "alias_normalized": self.alias_normalized,
            "platform": self.platform,
            "business_role": self.business_role,
        }


#: 6 个 TikTok 出口账号 —— 与 20261116 的 ``_TIKTOK_EXPORT_ALIASES`` **逐字一致**。
#:
#: ⚠ 这份清单必须与迁移里的常量保持一致；改动其中一边都要同步另一边。
#: 守护测试 ``backend/tests/test_bootstrap_seed_manifest.py`` 断言两边相等，
#: 所以不会再出现「只能靠人肉同步、报错还定位不到」的情况。
BOOTSTRAP_TIKTOK_ACCOUNTS: Tuple[BootstrapShopAccount, ...] = (
    BootstrapShopAccount("tiktok_sg_daone_mall_local", "SG", "DAONE Mall", "daonemall"),
    BootstrapShopAccount("tiktok_my_dawie_mall_local", "MY", "DAWIE Mall", "dawiemall"),
    BootstrapShopAccount(
        "tiktok_ph_explorers_mall_local", "PH", "Explorers Mall", "explorersmall"
    ),
    BootstrapShopAccount(
        "tiktok_my_flora_mall_local",
        "MY",
        "Malaysia(Flora Mall)",
        "malaysiafloramall",
    ),
    BootstrapShopAccount(
        "tiktok_ph_daju_mall_local",
        "PH",
        "Philippines(DAJU Mall)",
        "philippinesdajumall",
    ),
    BootstrapShopAccount(
        "tiktok_sg_hx_home_local", "SG", "Singapore(HX Home)", "singaporehxhome"
    ),
)

#: 运维提供的主账号字段（真实环境）。
REQUIRED_MAIN_ACCOUNT_FIELDS: Tuple[str, ...] = (
    "platform",
    "main_account_id",
    "username",
    "password_encrypted",
    "main_account_name",
)

#: 运维提供的店铺账号字段（真实环境）。
REQUIRED_SHOP_ACCOUNT_FIELDS: Tuple[str, ...] = ("shop_account_id", "store_name")


class BootstrapManifestError(ValueError):
    """引导清单不合法 —— 必须在动库之前就说清楚缺什么。"""


def bootstrap_account_ids() -> Tuple[str, ...]:
    """需要在新环境里存在的店铺账号 id（有序）。"""
    return tuple(item.shop_account_id for item in BOOTSTRAP_TIKTOK_ACCOUNTS)


def required_manifest_template() -> Dict[str, Any]:
    """给运维的清单模板（真实环境用）。

    字段固定部分（``shop_region`` / ``business_role`` / ``enabled``）由本模块提供，
    运维只需要补真实凭据与显示名。
    """
    return {
        "main_account": {
            "platform": BOOTSTRAP_PLATFORM,
            "main_account_id": "<真实主账号 ID>",
            "username": "<登录名>",
            "password_encrypted": "<加密后的口令>",
            "main_account_name": "<主账号显示名>",
        },
        "shop_accounts": [
            {
                "shop_account_id": item.shop_account_id,
                "shop_region": item.shop_region,
                "store_name": "<该店的显示名>",
            }
            for item in BOOTSTRAP_TIKTOK_ACCOUNTS
        ],
    }


def load_operator_manifest(path: str | Path) -> Dict[str, Any]:
    """读取运维提供的清单文件（JSON）。"""
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise BootstrapManifestError(
            "引导清单文件不存在: {path}".format(path=manifest_path)
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BootstrapManifestError(
            "引导清单文件无法解析: {path} ({exc})".format(path=manifest_path, exc=exc)
        ) from exc
    if not isinstance(payload, dict):
        raise BootstrapManifestError("引导清单根节点必须是 JSON 对象")
    return payload


def build_operator_rows(
    manifest: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """把运维清单校验后转成「主账号行 + 店铺账号行」。

    校验失败**不写库**，直接抛 :class:`BootstrapManifestError` 并列出全部问题。
    """
    problems: List[str] = []

    main_block = manifest.get("main_account")
    if not isinstance(main_block, dict):
        raise BootstrapManifestError("引导清单缺少 main_account 对象")
    main_row: Dict[str, Any] = {}
    for field in REQUIRED_MAIN_ACCOUNT_FIELDS:
        value = main_block.get(field)
        if value is None or not str(value).strip():
            problems.append("main_account 缺少字段: {field}".format(field=field))
        else:
            main_row[field] = value
    if main_row.get("platform") and str(main_row["platform"]) != BOOTSTRAP_PLATFORM:
        problems.append(
            "main_account.platform 必须是 {want}，实际 {got}".format(
                want=BOOTSTRAP_PLATFORM, got=main_row["platform"]
            )
        )

    shop_blocks = manifest.get("shop_accounts")
    if not isinstance(shop_blocks, list):
        raise BootstrapManifestError("引导清单缺少 shop_accounts 数组")

    provided: Dict[str, Dict[str, Any]] = {}
    for index, block in enumerate(shop_blocks):
        if not isinstance(block, dict):
            problems.append("shop_accounts[{index}] 必须是对象".format(index=index))
            continue
        shop_account_id = str(block.get("shop_account_id") or "").strip()
        if not shop_account_id:
            problems.append(
                "shop_accounts[{index}] 缺少 shop_account_id".format(index=index)
            )
            continue
        if shop_account_id in provided:
            problems.append(
                "shop_accounts 里 shop_account_id 重复: {sid}".format(
                    sid=shop_account_id
                )
            )
            continue
        provided[shop_account_id] = block

    known_ids = set(bootstrap_account_ids())
    for unknown_id in sorted(set(provided) - known_ids):
        problems.append(
            "shop_accounts 里出现未知账号 {sid}（清单只认 {ids}）".format(
                sid=unknown_id, ids=", ".join(sorted(known_ids))
            )
        )

    shop_rows: List[Dict[str, Any]] = []
    for account in BOOTSTRAP_TIKTOK_ACCOUNTS:
        block = provided.get(account.shop_account_id)
        if block is None:
            problems.append(
                "缺少账号 {sid}（区域 {region}）".format(
                    sid=account.shop_account_id, region=account.shop_region
                )
            )
            continue
        store_name = str(block.get("store_name") or "").strip()
        if not store_name:
            problems.append(
                "账号 {sid} 缺少 store_name".format(sid=account.shop_account_id)
            )
            continue
        declared_region = block.get("shop_region")
        if (
            declared_region is not None
            and str(declared_region).strip() != account.shop_region
        ):
            problems.append(
                "账号 {sid} 区域不符: 期望 {want}，实际 {got}".format(
                    sid=account.shop_account_id,
                    want=account.shop_region,
                    got=declared_region,
                )
            )
            continue
        shop_rows.append(
            {
                "platform": account.platform,
                "shop_account_id": account.shop_account_id,
                "main_account_id": main_row.get("main_account_id"),
                "store_name": store_name,
                "shop_region": account.shop_region,
                "enabled": True,
                "business_role": account.business_role,
            }
        )

    if problems:
        raise BootstrapManifestError("引导清单未通过校验：" + "；".join(problems))
    return main_row, shop_rows


def build_gate_rows() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """门禁 profile —— 占位值（**仅供临时库门禁使用**）。

    真实环境**不允许**用这套占位值：它没有真实凭据、显示名也是占位。
    """
    main_row: Dict[str, Any] = {
        "platform": BOOTSTRAP_PLATFORM,
        "main_account_id": GATE_MAIN_ACCOUNT_ID,
        "username": GATE_MAIN_ACCOUNT_ID,
        # 门禁库里没有真实口令；只要求 NOT NULL。
        "password_encrypted": "<migration-gate-placeholder>",
        "main_account_name": "迁移门禁种子主账号",
        "enabled": True,
    }
    shop_rows: List[Dict[str, Any]] = []
    for account in BOOTSTRAP_TIKTOK_ACCOUNTS:
        shop_rows.append(
            {
                "platform": account.platform,
                "shop_account_id": account.shop_account_id,
                "main_account_id": GATE_MAIN_ACCOUNT_ID,
                "store_name": "迁移门禁种子店 {sid}".format(
                    sid=account.shop_account_id
                ),
                "shop_region": account.shop_region,
                "enabled": True,
                # business_role 默认就是 operating_store，但显式写出来 ——
                # 20261116 的前置检查会核对这一项。
                "business_role": account.business_role,
            }
        )
    return main_row, shop_rows


def apply_bootstrap_accounts(
    database_url: str,
    main_row: Dict[str, Any],
    shop_rows: Sequence[Dict[str, Any]],
) -> int:
    """写入引导账号，返回新增行数。幂等（已存在的行会被跳过）。"""
    engine = create_engine(database_url)
    inserted = 0
    try:
        with engine.begin() as connection:
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

            for shop_row in shop_rows:
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


def verify_bootstrap_accounts(database_url: str) -> List[str]:
    """返回「缺失或属性不符」的账号 id 描述（空列表 = 全部就位）。"""
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                SELECT shop_account_id, shop_region, enabled, business_role
                FROM core.shop_accounts
                WHERE platform = :platform
                  AND shop_account_id = ANY(CAST(:ids AS text[]))
                """
                ),
                {
                    "platform": BOOTSTRAP_PLATFORM,
                    "ids": list(bootstrap_account_ids()),
                },
            ).all()
    finally:
        engine.dispose()

    found = {str(row[0]): row for row in rows}
    problems: List[str] = []
    for account in BOOTSTRAP_TIKTOK_ACCOUNTS:
        row = found.get(account.shop_account_id)
        if row is None:
            problems.append("账号不存在: {sid}".format(sid=account.shop_account_id))
            continue
        if str(row[1] or "").strip() != account.shop_region:
            problems.append(
                "区域不符: {sid} 期望 {want}，实际 {got}".format(
                    sid=account.shop_account_id,
                    want=account.shop_region,
                    got=row[1] or "(空)",
                )
            )
        if not row[2]:
            problems.append("账号已停用: {sid}".format(sid=account.shop_account_id))
        if str(row[3] or "") != account.business_role:
            problems.append(
                "不是经营店: {sid}(business_role={role})".format(
                    sid=account.shop_account_id, role=row[3]
                )
            )
    return problems


def fresh_environment_bootstrap_message() -> str:
    """空库时的**可执行**指引（迁移 runner 直接抛这句话）。"""
    account_lines = "\n".join(
        "  - {sid}（区域 {region}，别名 {alias}）".format(
            sid=item.shop_account_id,
            region=item.shop_region,
            alias=item.alias_value,
        )
        for item in BOOTSTRAP_TIKTOK_ACCOUNTS
    )
    return (
        "当前数据库是全新空库，current-schema 迁移链无法直接跑完：\n"
        "迁移 {rev} 需要 {n} 个已存在的 TikTok 出口账号（fail-closed 前置检查），\n"
        "空库上这些账号不存在 ⇒ 链会在该步中止。\n"
        "\n"
        "必须走两段式引导（不要改迁移文件，已应用迁移不可变）：\n"
        "  1) 先升级到 {pre}\n"
        "  2) 注入引导账号（主账号 + 6 个店铺账号）\n"
        "  3) 再升级到 head\n"
        "\n"
        "现成入口：\n"
        "  python scripts/bootstrap_fresh_environment.py --manifest <你的引导清单.json>\n"
        "  （清单模板：python scripts/bootstrap_fresh_environment.py --print-template）\n"
        "\n"
        "需要的账号：\n{accounts}\n"
        "\n"
        "临时库门禁用占位值即可：python scripts/validate_migrations_fresh_db.py".format(
            rev=BOOTSTRAP_REVISION,
            n=len(BOOTSTRAP_TIKTOK_ACCOUNTS),
            pre=PRECHECK_TARGET_REVISION,
            accounts=account_lines,
        )
    )


def iter_account_payloads() -> Iterable[Dict[str, Any]]:
    """清单的可序列化形式（供校验、文档与测试使用）。"""
    for account in BOOTSTRAP_TIKTOK_ACCOUNTS:
        yield account.to_dict()
