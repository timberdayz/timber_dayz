"""内部标准名（internal_code）的建议值生成、冲突消歧与存量回填。

内部标准名是「给人看的唯一标识」，例如 ``FIORO_SG`` / ``FIORO_MY`` / ``FIORO_PH``。
它**不参与数据匹配**（匹配只走 平台 + 主账号 + 原始导出标签 + 区域），
见 ``docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md``。

三个名字的分工：

============  ==========================================  ====================
名字          含义                                        用途
============  ==========================================  ====================
store_name    平台侧真实店名（可重名、会变）                展示 + 改名联动的起点
internal_code 内部标准名（同平台内唯一、带地区标识）        人读标识，不参与匹配
别名表        原始导出标签（唯一匹配锚点）                  归属匹配的真正依据
============  ==========================================  ====================

回填入口（默认 dry-run，写库要显式加 ``--apply``）::

    python -m backend.services.shop_internal_code_service            # 只预览
    python -m backend.services.shop_internal_code_service --apply    # 真正写库
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.async_task_runner import run_async_task
from modules.core.db import ShopAccount
from modules.core.logger import get_logger


logger = get_logger(__name__)

# 已知的地区后缀（小写），从店铺名尾部剥离，避免重复拼接区域码
_KNOWN_REGION_SUFFIXES = (
    "my", "sg", "ph", "vn", "th", "tw", "id", "br", "mx", "cl", "co", "ar",
    "uk", "de", "fr", "it", "es", "jp", "kr", "us", "ca", "au",
)

_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")

#: 回填写入的 updated_by 标记
BACKFILL_UPDATED_BY = "system:backfill"


def suggest_internal_code(
    store_name: str,
    shop_region: Optional[str] = None,
    *,
    main_account_id: Optional[str] = None,
    taken: Optional[Iterable[str]] = None,
) -> str:
    """按 店铺名 + 区域 生成内部标准名建议值。

    规则：大写化(store_name 去掉已知地区后缀) -> 非字母数字转 ``_`` -> 去首尾 ``_``
    -> 拼 ``_`` + ``shop_region``；同平台同区域重名时追加主账号短标识。

    Args:
        store_name: 平台侧真实店名
        shop_region: 区域码，例如 ``MY``
        main_account_id: 主账号 ID，仅在冲突时用于追加短标识
        taken: 已占用的标准名集合，用于消歧

    Returns:
        建议的标准名，例如 ``FIORO_SG``。
    """
    base = str(store_name or "").strip()
    base = _strip_region_suffix(base)
    code = _NON_ALNUM_RE.sub("_", base.upper()).strip("_")
    if not code:
        code = "SHOP"

    region = str(shop_region or "").strip().upper()
    candidate = f"{code}_{region}" if region else code

    used = {str(item) for item in (taken or [])}
    if candidate not in used:
        return candidate

    # 同平台同区域多主账号冲突 -> 追加主账号短标识
    suffix = _main_account_short_id(main_account_id)
    if suffix:
        alternate = f"{candidate}_{suffix}"
        if alternate not in used:
            return alternate

    return candidate


def _strip_region_suffix(store_name: str) -> str:
    """剥离店铺名尾部已知的地区域名后缀，例如 ``xhkj1.my`` -> ``xhkj1``。"""
    text = store_name.strip()
    if "." not in text:
        return text
    head, _, tail = text.rpartition(".")
    if tail.lower() in _KNOWN_REGION_SUFFIXES and head:
        return head
    return text


def _main_account_short_id(main_account_id: Optional[str]) -> str:
    """主账号 ID -> 短标识，例如 ``Tiktok 1店`` -> ``T1``、``a@b.com`` -> ``AB``。"""
    text = str(main_account_id or "").strip()
    if not text:
        return ""
    if "@" in text:
        return "".join(ch for ch in text.split("@")[0].upper() if ch.isalnum())[:2] or "M1"
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"T{digits}"
    return "".join(ch for ch in text.upper() if ch.isalnum())[:2] or "M1"


def _platform_key(platform: Optional[str]) -> str:
    """平台归一化键 —— 同平台内唯一性按这个键判定。"""
    return str(platform or "").strip().lower()


def ensure_unique_internal_code(candidate: str, used: set[str]) -> str:
    """保证返回值不在 ``used`` 里。

    ``suggest_internal_code`` 只负责「建议」，当连主账号短标识都撞上时它会退回
    候选值本身 —— 那会违反库层的 ``uq_shop_accounts_platform_internal_code``。
    回填走的是「必须写进库」的路径，所以在这里补一个序号兜底。
    """
    if candidate not in used:
        return candidate
    index = 2
    while f"{candidate}_{index}" in used:
        index += 1
    return f"{candidate}_{index}"


async def load_taken_internal_codes(db: AsyncSession) -> dict[str, set[str]]:
    """读出每个平台已占用的内部标准名集合。

    唯一性判据是「同平台内唯一」（库层约束 ``uq_shop_accounts_platform_internal_code``）。
    """
    rows = (
        await db.execute(select(ShopAccount.platform, ShopAccount.internal_code))
    ).all()
    taken: dict[str, set[str]] = {}
    for platform, code in rows:
        normalized = str(code or "").strip()
        if not normalized:
            continue
        taken.setdefault(_platform_key(platform), set()).add(normalized)
    return taken


async def suggest_internal_code_for_account(
    db: AsyncSession,
    record: ShopAccount,
    *,
    taken_codes: Optional[dict[str, set[str]]] = None,
) -> str:
    """给一个店铺账号算内部标准名建议值（不落库）。

    Args:
        db: 异步会话
        record: 店铺账号
        taken_codes: 已占用标准名集合（按平台分组）。不传则现查一次。
    """
    if taken_codes is None:
        taken_codes = await load_taken_internal_codes(db)
    used = set(taken_codes.get(_platform_key(record.platform), set()))
    # 自己的旧值不算冲突
    own_code = str(record.internal_code or "").strip()
    if own_code:
        used.discard(own_code)
    return suggest_internal_code(
        record.store_name,
        record.shop_region,
        main_account_id=record.main_account_id,
        taken=used,
    )


async def backfill_internal_codes(
    db: AsyncSession,
    *,
    dry_run: bool = True,
    updated_by: str = BACKFILL_UPDATED_BY,
) -> dict[str, Any]:
    """回填存量店铺账号的内部标准名。

    规则：同平台内保证唯一；冲突时追加主账号短标识。
    已人工填写过 internal_code 的记录不动。

    Args:
        db: 异步会话
        dry_run: ``True``（默认）只算出结果不写库；``False`` 才真正落库
        updated_by: 写库时写入的 ``updated_by`` 标记

    Returns:
        统计信息 + 逐条的分配方案 ``assignments``。
    """
    records = (
        await db.execute(
            select(ShopAccount).order_by(
                ShopAccount.platform,
                ShopAccount.shop_region,
                ShopAccount.main_account_id,
                ShopAccount.shop_account_id,
            )
        )
    ).scalars().all()

    taken_by_platform: dict[str, set[str]] = {}
    for record in records:
        code = str(record.internal_code or "").strip()
        if not code:
            continue
        taken_by_platform.setdefault(_platform_key(record.platform), set()).add(code)

    assignments: list[dict[str, Any]] = []
    applied = 0
    for record in records:
        if str(record.internal_code or "").strip():
            continue
        used = taken_by_platform.setdefault(_platform_key(record.platform), set())
        candidate = suggest_internal_code(
            record.store_name,
            record.shop_region,
            main_account_id=record.main_account_id,
            taken=used,
        )
        internal_code = ensure_unique_internal_code(candidate, used)
        used.add(internal_code)
        assignments.append(
            {
                "platform": record.platform,
                "shop_account_id": record.shop_account_id,
                "main_account_id": record.main_account_id,
                "store_name": record.store_name,
                "shop_region": record.shop_region,
                "internal_code": internal_code,
            }
        )
        if not dry_run:
            record.internal_code = internal_code
            record.updated_by = updated_by
            record.updated_at = datetime.now(timezone.utc)
            applied += 1

    if not dry_run and applied:
        await db.commit()
        logger.info(
            "[ShopInternalCode] backfilled %s shop accounts (updated_by=%s)",
            applied,
            updated_by,
        )

    return {
        "dry_run": dry_run,
        "total": len(records),
        "already_filled": len(records) - len(assignments),
        "planned": len(assignments),
        "applied": applied,
        "assignments": assignments,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.services.shop_internal_code_service",
        description="回填 core.shop_accounts.internal_code（内部标准名），默认只预览",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（默认 dry-run，只打印方案）",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="覆盖数据库连接串（默认用项目配置里的 DATABASE_URL）",
    )
    return parser


async def _run_backfill(database_url: Optional[str], apply: bool) -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.models.database import get_async_database_url

    owned_engine = None
    if database_url:
        owned_engine = create_async_engine(
            get_async_database_url(database_url), pool_pre_ping=True
        )
        factory = async_sessionmaker(owned_engine, expire_on_commit=False)
    else:
        from backend.models.database import AsyncSessionLocal

        factory = AsyncSessionLocal

    try:
        async with factory() as session:
            return await backfill_internal_codes(session, dry_run=not apply)
    finally:
        if owned_engine is not None:
            await owned_engine.dispose()


def main() -> int:
    args = _build_arg_parser().parse_args()
    result = run_async_task(lambda: _run_backfill(args.database_url, args.apply))
    # stdout 只输出 JSON（机器可解析），提示信息走 stderr
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["dry_run"]:
        print(
            "[dry-run] 未写库。确认上面的分配方案后，加 --apply 再跑一次才会落库。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
