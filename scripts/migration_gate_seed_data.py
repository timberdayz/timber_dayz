"""迁移门禁的最小前置种子数据 —— **共享引导清单的门禁 profile 适配层**。

⚠ 本模块**不再自己维护账号清单**
--------------------------------
账号清单的真源现在是 :mod:`scripts.bootstrap_seed_manifest`
（``BOOTSTRAP_TIKTOK_ACCOUNTS``），它同时服务三种调用方：

* 真实新环境 —— ``scripts/bootstrap_fresh_environment.py --manifest ...``
* 临时库门禁 —— 本模块（占位值 profile）
* 本地重建 —— ``scripts/rebuild_local_current_schema.py``（占位值 profile）

以前这里是一份**独立复制**的清单，与迁移里的常量靠人肉同步；
现在由 ``backend/tests/test_bootstrap_seed_manifest.py`` 断言三方逐字一致，
漂移会直接变红，而不是等到门禁报「账号不存在」。

为什么需要种子
--------------
``current_schema_20261116_add_tiktok_export_store_name_aliases`` 是**数据修复型迁移**:
它给 6 个已存在的 TikTok 店铺账号补「导出店名」别名, 并在动手前做 fail-closed
前置检查(账号存在 / 区域相符 / 已启用 / 是经营店 / 别名键没被别人认领)。

在**全新空库**上, ``core.shop_accounts`` 里根本没有这些账号 ⇒ 前置检查必然失败
⇒ 整条迁移链在 20261116 中止 ⇒ 「从零跑全量迁移」永远跑不通。

两条修法的取舍(与 ``scripts/bootstrap_seed_manifest.py`` 的说明一致):

* (A) 改 20261116 的检查逻辑, 让它在空库上 no-op ——
  **不采用**: 已执行过的迁移不可改; 而且那样会让「全新部署的环境里 TikTok 导出
  别名不存在」这个**真实部署缺陷**被悄悄掩掉。
* (B) 分两段迁移 + 注入**最小前置数据**, 使前置检查**有意义** ——
  **采用**。本模块提供 (B) 的门禁 profile, 真实环境用同一套流程但由运维提供真实值。

本模块只提供门禁 profile(占位值), 明确标注「仅供门禁使用」。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.bootstrap_seed_manifest import (  # noqa: E402
    BOOTSTRAP_TIKTOK_ACCOUNTS,
    GATE_MAIN_ACCOUNT_ID,
    apply_bootstrap_accounts,
    build_gate_rows,
    verify_bootstrap_accounts,
)


#: 6 个 TikTok 导出别名账号 —— 与 20261116 的 ``_TIKTOK_EXPORT_ALIASES``
#: **逐字一致**(shop_account_id + 区域)。
#:
#: ⚠ 数据来自共享清单 ``scripts/bootstrap_seed_manifest.py``，不在这里二次维护;
#: 一致性由 ``backend/tests/test_bootstrap_seed_manifest.py`` 守护。
GATE_TIKTOK_ACCOUNTS: Tuple[Tuple[str, str], ...] = tuple(
    (item.shop_account_id, item.shop_region) for item in BOOTSTRAP_TIKTOK_ACCOUNTS
)


def seed_migration_gate_accounts(database_url: str) -> int:
    """注入门禁用的最小账号数据, 返回插入的行数(主账号 + 店铺账号)。

    幂等: 已存在的行会被跳过(``ON CONFLICT DO NOTHING``)。
    """
    main_row, shop_rows = build_gate_rows()
    return apply_bootstrap_accounts(database_url, main_row, shop_rows)


def verify_seed_accounts(database_url: str) -> List[str]:
    """返回「缺失或属性不符」的账号 id 列表(空列表 = 全部就位)。"""
    return verify_bootstrap_accounts(database_url)


def gate_seed_account_ids() -> Iterable[str]:
    """门禁种子覆盖的账号 id(供测试断言用)。"""
    return (sid for sid, _ in GATE_TIKTOK_ACCOUNTS)
