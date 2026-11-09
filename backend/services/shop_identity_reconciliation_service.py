"""入库前的「行内身份收敛」—— 让一条事实行**只带一套身份**。

背景
----
一条事实行身上原本会带**多套**身份表示:

===========================  ==========================================
位置                          来源
===========================  ==========================================
``b_class`` 的 ``shop_id`` 列  文件级登记(``catalog_files.shop_id``)
``raw_data['shop_id']``       行内自带, 没有才用文件级
``raw_data['shop_account_id']`` 文件级登记 / 行内自带
``raw_data['store_name']``     文件级登记 / 行内自带
``raw_data['platform_shop_id']``文件级登记 / 行内自带
===========================  ==========================================

语义层把其中几路当成**独立候选**去计数(``count(DISTINCT c.resolved_shop_id)``),
所以只要它们**互相矛盾** ⇒ 候选数 2 ⇒ 整行落 ``unknown``。

2026-11 的实测: Shopee 有 **1,946 行**的「行内编号」与「行内标签」互相矛盾
(采集侧算错编号 ⇒ 标签被换到别的店上), 造成 8,409 UV 从看板消失。

为什么「编号优先」
----------------
这一行到底属于哪个店, 有两组硬证据:

* **UV 量级**(决定性)::

      标签店 shopee_sg_xhkj11_local   正常行 UV avg 314.7   错配行 UV avg 786.9
      编号店 shopee_ph_xhkj11_local   正常行 UV avg 896.4

      标签店 shopee_ph_xh_home_local  正常行 UV avg 362.6   错配行 UV avg 147.4
      编号店 shopee_my_xhkj1_local    正常行 UV avg 141.2

  错配行的 UV 吻合**编号所属**的店, 不吻合**标签所属**的店 ⇒ **数据是编号那个店的**,
  标签被贴错了。

* **语义层候选池的既有优先级**: ``shop_identity_resolution_candidates`` 早在
  2026-11-06 就把 ``shop_account_id`` 提到 priority 1, 理由写得很清楚 ——
  「``platform_shop_id`` 会被采集器污染」。本次事故正是这条警告的兑现。

⇒ 结论: **平台店铺编号是权威的**, 标签(店名/账号 ID)可能整组贴错。
本模块与历史订正迁移(``20261117_remediate_shopee_row_identity_conflicts``)
**同构** —— 都以「行内编号反查到的账号」为归属。

三条硬规则
----------
1. **唯一命中才归属** —— 某个信号反查出**多个**账号时, 该信号**不可用**(跳过),
   换下一个信号; 所有信号都无法唯一命中 ⇒ **不收敛**, 保持原样。
   语义层照旧落 ``unknown`` + 看板按 ``platform_shop_id_conflict`` 告警。
   **绝不静默挑一个。**
2. **收敛值一律取主数据登记值** —— 不从行内观测值推导, 不猜。
3. **只改身份键** —— 业务字段(访客数 / GMV / 日期 …)一个字都不动。

⚠️ 与 ``data_hash`` 的关系
--------------------------
``data_hash`` 的作用域只取**一个**身份键(``shop_account_id`` > ``platform_shop_id``
> ``shop_id``), 且全部取**文件级**的值 ⇒ 收敛**不改变** ``data_hash`` ⇒
重新采集同一份文件时 upsert 冲突键一致 ⇒ 覆盖同一行, **不会重复入库**。

⚠️ 为什么 ``shop_id`` 在没有平台编号时**不**被改写
--------------------------------------------------
TikTok 的主数据没有 ``platform_shop_id``(TikTok 侧只有别名表是锚点),
若把它的 ``shop_id`` 改写成账号 ID, 则**文件级 upsert 冲突键**
(``platform_code, shop_id, data_domain, granularity, data_hash``)会变 ⇒
将来重采同一份文件会**插入重复行**而不是覆盖。

⇒ 所以: **有平台编号才改 ``shop_id``**; 没有则保留原值, 只补 ``shop_account_id``
与 ``store_name``(让行内自带权威锚点), 冲突键因此不变。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from backend.utils.text_normalization import normalize_alias_key
from modules.core.fact_identity_columns import COLLECTION_SOURCE_IDS
from modules.core.validators import normalize_enum_value


#: 收敛开关(可用环境变量关掉, 便于线上快速止血)。
#:
#: 默认**开**。关掉后行为与收敛前完全一致(只是多跑一次诊断)。
RECONCILIATION_ENABLED = os.getenv(
    "SHOP_IDENTITY_RECONCILIATION_ENABLED", "1"
).strip().lower() not in ("0", "false", "off", "no")

#: 信号优先级 —— **平台店铺编号最权威**。
#:
#: 顺序即「同一串值同时命中多个信号时先听谁的」:
#:
#: 1. ``platform_shop_id`` —— 主数据登记的平台编号
#: 2. ``shop_id``           —— 行内那列(Shopee 是编号 / TikTok 是导出店名)
#: 3. ``shop_account_id``   —— 账号 ID
#: 4. ``store_name``        —— 店名
#:
#: ``store_name`` 命中不到主数据店名时会自动退回别名索引(见 :meth:`IdentityIndex.lookup`),
#: 所以 TikTok 的导出店名(``DAONE Mall`` 之类)也能认到账号。
SIGNAL_PRIORITY = (
    "platform_shop_id",
    "shop_id",
    "shop_account_id",
    "store_name",
)

#: ``raw_data`` 里承载「店铺标签」的键 —— 语义层的 ``store_label_raw`` 会读到它们。
_STORE_NAME_KEYS = ("店铺", "店铺名", "店铺名称", "store_name", "store_label_raw")

#: ``raw_data`` 里承载「平台店铺编号」的键 —— 语义层的 ``source_platform_shop_id`` 会读到它们。
_PLATFORM_SHOP_ID_KEYS = ("platform_shop_id", "平台店铺ID", "店铺ID")

#: ``raw_data`` 里承载「账号 ID」的键 —— 语义层的 ``source_shop_account_id`` 会读到它们。
_SHOP_ACCOUNT_ID_KEYS = (
    "shop_account_id",
    "account_id",
    "店铺账号ID",
    "账号ID",
    "account",
)

#: 行内 ``shop_id`` 键(语义层的 ``source_shop_id`` 会读到它)。
_SHOP_ID_KEYS = ("shop_id",)

#: 行内「店铺身份」候选键 —— **行内自带**的那几路身份表示。
#:
#: ⚠️ 事实表的 **列** ``shop_id`` **不在这里** —— 它是采集层写进来的原始标识
#: (shopee 上是平台编号 / tiktok 上是导出店名 / miaoshou 采集链上是采集方代号
#: ``xihong``), **不是身份列**。权威定性见
#: ``modules/core/fact_identity_columns.py``。
#:
#: 这里取的是 ``raw_data`` **内部**的键 —— 与事实表那一列是两回事。
_ROW_IDENTITY_KEYS = ("platform_shop_id", "shop_account_id", "shop_id")

#: 「采集方标识」—— 是**数据来源**, 不是店铺身份。
#:
#: ⚠️ 必须排除: ``xihong`` / ``miaoshou_real_001`` 出现在行内 ``shop_id`` 时
#: 表示「这批数据来自哪个采集器」, 拿它当店铺身份比对会得出错误结论。
#:
#: SSOT: ``modules/core/fact_identity_columns.py``

#: 收敛结果的三种状态
STATUS_CONVERGED = "converged"
STATUS_CONFLICT = "conflict"
STATUS_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class MasterIdentity:
    """``core.shop_accounts`` 里的一条账号登记。"""

    shop_account_id: str
    platform: str
    platform_shop_id: str
    store_name: str
    shop_region: str
    enabled: bool
    business_role: str
    #: ``core.shop_accounts.id``(整数主键) —— 别名表的 FK 指向它,
    #: 与 ``shop_account_id``(字符串账号编码)**不是同一个东西**。
    pk: str = ""

    @property
    def is_operating_store(self) -> bool:
        """是否是在营经营店。

        ⚠️ ``business_role`` 必须已经过 :func:`modules.core.validators.normalize_enum_value`
        解包 —— 见 :func:`_as_identity`。直接拿 SAEnum 成员做等值比较会**恒为 False**
        且**完全静默**, 曾导致本模块的反查索引恒为空、收敛 100% 失效。
        """
        return self.enabled and self.business_role == "operating_store"


@dataclass(frozen=True)
class ReconciliationResult:
    """一行(或一个文件)的收敛结果。"""

    status: str
    identity: MasterIdentity | None = None
    conflict_signals: tuple[str, ...] = ()
    matched_signals: tuple[str, ...] = ()
    ambiguous_signals: tuple[str, ...] = ()

    @property
    def converged(self) -> bool:
        return self.status == STATUS_CONVERGED and self.identity is not None


@dataclass(frozen=True)
class IdentityIndex:
    """按平台建好的反查索引。

    每个键都指向**账号列表**(而不是单个账号)—— 因为同一串值可能挂在两个账号上
    (跨区域同名 / 别名撞车), 那时就是**歧义**, 不能挑一个。
    """

    by_shop_account_id: Mapping[str, tuple[MasterIdentity, ...]]
    by_platform_shop_id: Mapping[str, tuple[MasterIdentity, ...]]
    by_store_name: Mapping[str, tuple[MasterIdentity, ...]]
    by_alias_normalized: Mapping[str, tuple[MasterIdentity, ...]]

    def lookup(
        self,
        signal: str,
        value: str,
        platform_code: str | None = None,
    ) -> tuple[MasterIdentity, ...]:
        """按信号类型反查账号列表(**按平台过滤**)。

        一个信号可能落在**两种**语义上:
        ``shop_id`` 对 Shopee 是「平台店铺编号」, 对 TikTok 是「店名」⇒
        编号索引查不到就退回别名索引(反之亦然)。

        ⚠️ **平台过滤是必须的**, 不是可选的优化
        --------------------------------------
        别名表里同一个店名可能同时挂在**不同平台**的账号上
        (实测: 中文名「菲律宾1店」既指向 ``shopee_ph_xhkj11_local``
        也指向 ``tiktok_ph_explorers_mall_local``)。
        不按平台过滤 ⇒ 同一行会解析出**两个**账号 ⇒ 被误判成「身份矛盾」⇒
        正常数据被丢弃。

        语义层候选池(``sql/semantic/shop_identity_resolution_candidates.sql``)
        是靠 SQL 里的 ``platform_code`` 过滤实现的; 本方法是它的等价物,
        **必须**显式传 ``platform_code`` 才能得到同样的结果。
        """
        text = str(value or "").strip()
        if not text:
            return ()
        if signal == "shop_account_id":
            hits = self.by_shop_account_id.get(text.lower(), ())
        elif signal in ("platform_shop_id", "shop_id"):
            hits = self.by_platform_shop_id.get(text.lower(), ())
            if not hits:
                hits = self.by_alias_normalized.get(normalize_alias_key(text), ())
        elif signal == "store_name":
            hits = self.by_store_name.get(text.lower(), ())
            if not hits:
                hits = self.by_alias_normalized.get(normalize_alias_key(text), ())
        else:
            return ()

        if not platform_code:
            return hits
        platform = _platform_key(platform_code)
        filtered = tuple(
            identity for identity in hits if identity.platform == platform
        )
        return filtered or hits


def _identity_text(value: Any) -> str:
    return str(value or "").strip()


def _get(row: Any, key: str) -> Any:
    """同时支持 ``dict`` 与 ORM 对象。"""
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _platform_key(value: Any) -> str:
    return _identity_text(value).lower()


# ---------------------------------------------------------------------------
# 行内身份解析(SSOT: 同步侧拦截与云端巡检共用同一份实现)
# ---------------------------------------------------------------------------


def normalize_identity_token(value: Any) -> str:
    """归一化一个行内身份值, 供「同层互证」比较。

    去掉平台前缀(``Shopee`` / ``TK`` / ``TikTok Shop`` / ``Miaoshou`` …)与
    分隔符(空格/下划线/括号/斜杠/连字符), 让 ``Shopee3C店`` 与 ``3c店``
    归一到同一个 token —— 与语义层 ``shop_identity_resolution_candidates.sql``
    的归一化口径保持一致。
    """
    text = _identity_text(value).lower()
    if not text:
        return ""
    text = re.sub(
        r"^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*",
        "",
        text,
    )
    text = re.sub(r"[\s_()/\-]+", "", text)
    return text


def row_identity_tokens(row: Mapping[str, Any]) -> dict[str, str]:
    """取出行内身份键的归一化 token 集合(同层, 不含事实表的列)。

    只读 ``raw_data`` **内部**的键 —— 事实表那一列 ``shop_id`` 不是身份列,
    拿它判身份会把正常数据全误杀(实测 3,781 行)。
    """
    raw_data = _get(row, "raw_data")
    raw = raw_data if isinstance(raw_data, dict) else {}

    tokens: dict[str, str] = {}
    for key in _ROW_IDENTITY_KEYS:
        value = _identity_text(raw.get(key))
        if not value or value.lower() in COLLECTION_SOURCE_IDS:
            continue
        tokens[key] = normalize_identity_token(value)

    for key in _STORE_NAME_KEYS:
        value = _identity_text(raw.get(key))
        if not value or value.lower() in COLLECTION_SOURCE_IDS:
            continue
        tokens.setdefault("store_label", normalize_identity_token(value))

    return {k: v for k, v in tokens.items() if v}


def row_identity_accounts(
    row: Mapping[str, Any],
    identity_index: IdentityIndex,
    platform_code: str = "",
) -> set[str]:
    """用主数据反查出行内身份键能归属到的**账号集合**。

    ``identity_index`` 为 :class:`IdentityIndex`。

    ⚠️ 归一化口径: 账号 ID 与平台编号是**不同形态**(``shopee_sg_xxx_local`` vs
    ``1407964586``), 归一化后并不能互相匹配 ⇒ **必须查主数据**, 不能靠字符串比较。
    中文店名需用 ``normalize_alias_key`` 归一(与语义层候选池同口径)。

    ⚠️ **必须按平台过滤**: 同一个中文店名可能同时挂在不同平台的账号上
    (实测「菲律宾1店」既指向 shopee 也指向 tiktok 的账号)。
    不按平台过滤 ⇒ 同一行解析出两个账号 ⇒ 正常数据被误判成矛盾丢弃。

    采集方标识(``xihong`` / ``miaoshou_real_001``)已在取 token 时排除 ——
    它们表示「数据来自哪个采集器」, 不是店铺身份。
    """
    if identity_index is None:
        return set()

    raw_data = _get(row, "raw_data")
    raw = raw_data if isinstance(raw_data, dict) else {}

    accounts: set[str] = set()

    def _collect(signal: str, value: str) -> None:
        if not value:
            return
        for identity in identity_index.lookup(signal, value, platform_code):
            accounts.add(identity.shop_account_id)

    # 强身份键
    for key in ("platform_shop_id", "shop_account_id", "shop_id"):
        value = _identity_text(raw.get(key))
        if not value or value.lower() in COLLECTION_SOURCE_IDS:
            continue
        signal = (
            "shop_account_id"
            if key == "shop_account_id"
            else ("platform_shop_id" if key == "platform_shop_id" else "shop_id")
        )
        _collect(signal, value)

    # 店铺标签(中文列 / store_name)
    for key in _STORE_NAME_KEYS:
        value = _identity_text(raw.get(key))
        if not value or value.lower() in COLLECTION_SOURCE_IDS:
            continue
        _collect("store_name", value)
        _collect("store_name", normalize_alias_key(value))

    return accounts


def _as_identity(row: Any) -> MasterIdentity:
    return MasterIdentity(
        shop_account_id=_identity_text(_get(row, "shop_account_id")),
        platform=_platform_key(_get(row, "platform")),
        platform_shop_id=_identity_text(_get(row, "platform_shop_id")),
        store_name=_identity_text(_get(row, "store_name")),
        shop_region=_identity_text(_get(row, "shop_region")),
        enabled=bool(_get(row, "enabled")),
        business_role=normalize_enum_value(_get(row, "business_role")),
        pk=_identity_text(_get(row, "id")),
    )


def _push(
    index: dict[str, list[MasterIdentity]], key: str, value: MasterIdentity
) -> None:
    bucket = index.setdefault(key, [])
    if value not in bucket:
        bucket.append(value)


def build_identity_index(
    accounts: Iterable[Mapping[str, Any]],
    aliases: Iterable[Mapping[str, Any]] = (),
) -> IdentityIndex:
    """用「账号 + 别名」建反查索引。

    只收**在营经营店**(``enabled IS TRUE`` 且 ``business_role='operating_store'``)——
    与语义层候选池的口径一致(停用店的编号本来就不该命中任何行)。

    Args:
        accounts: ``core.shop_accounts`` 的行(``dict`` 或 ORM 对象都行)。
        aliases: ``core.shop_account_aliases`` 的行(只取 active)。
    """
    identities: list[MasterIdentity] = []
    for row in accounts:
        identity = _as_identity(row)
        if not identity.shop_account_id or not identity.platform:
            continue
        if not identity.is_operating_store:
            continue
        identities.append(identity)

    by_account: dict[str, list[MasterIdentity]] = {}
    by_psid: dict[str, list[MasterIdentity]] = {}
    by_store: dict[str, list[MasterIdentity]] = {}
    for identity in identities:
        _push(by_account, identity.shop_account_id.lower(), identity)
        if identity.platform_shop_id:
            _push(by_psid, identity.platform_shop_id.lower(), identity)
        if identity.store_name:
            _push(by_store, identity.store_name.lower(), identity)

    by_alias: dict[str, list[MasterIdentity]] = {}
    # ⚠️ 别名表的 FK 指向 ``core.shop_accounts.id``(整数主键),
    #    **不是** ``shop_account_id``(字符串账号编码)—— 两种写法都得认。
    owner_by_pk: dict[str, MasterIdentity] = {}
    owner_by_code: dict[str, MasterIdentity] = {}
    for identity in identities:
        if identity.pk:
            owner_by_pk[identity.pk] = identity
        owner_by_code[identity.shop_account_id] = identity
    for alias in aliases:
        if not bool(_get(alias, "is_active")):
            continue
        # 语义层用的是 ``LOWER(TRIM(saa.alias_normalized))`` ⇒ 以库里的归一化值为准,
        # 只有它为空时才回退到现算(两边规则本应一致)。
        alias_key = _identity_text(_get(alias, "alias_normalized")).lower()
        if not alias_key:
            alias_key = normalize_alias_key(_identity_text(_get(alias, "alias_value")))
        if not alias_key:
            continue
        alias_ref = _identity_text(_get(alias, "shop_account_id"))
        owner = owner_by_pk.get(alias_ref) or owner_by_code.get(alias_ref)
        if owner is None:
            continue
        _push(by_alias, alias_key.lower(), owner)

    return IdentityIndex(
        by_shop_account_id={k: tuple(v) for k, v in by_account.items()},
        by_platform_shop_id={k: tuple(v) for k, v in by_psid.items()},
        by_store_name={k: tuple(v) for k, v in by_store.items()},
        by_alias_normalized={k: tuple(v) for k, v in by_alias.items()},
    )


async def load_identity_index(db) -> IdentityIndex:
    """从库里取「账号 + 别名」建索引。

    ⚠️ 主数据规模很小(实测 52 个账号 / 20 条 active 别名)⇒ **一次性全量拉取**,
    不做逐行查库(避免 N+1)。

    调用方负责兜住异常 —— 索引取不到就**跳过收敛**(不改数据), 不让入库失败。
    """
    from sqlalchemy import select

    from modules.core.db import ShopAccount, ShopAccountAlias

    account_rows = (
        (
            await db.execute(
                select(ShopAccount).where(
                    ShopAccount.enabled.is_(True),
                    ShopAccount.business_role == "operating_store",
                )
            )
        )
        .scalars()
        .all()
    )
    alias_rows = (
        (
            await db.execute(
                select(ShopAccountAlias).where(ShopAccountAlias.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    return build_identity_index(account_rows, alias_rows)


def reconcile_identity(
    index: IdentityIndex,
    *,
    platform_code: str,
    signals: Mapping[str, str],
) -> ReconciliationResult:
    """把一组身份信号解析成「唯一归属账号」。

    按 :data:`SIGNAL_PRIORITY` 的顺序逐个信号反查:

    * 命中**唯一**账号 ⇒ 该账号即归属(第一个命中的说了算);
    * 命中**多个**账号 ⇒ 该信号**歧义** ⇒ 不可用, 换下一个信号;
    * 一个都没命中 ⇒ 跳过。

    归属确定后, 其余信号若指向**别的**账号 ⇒ 记为冲突信号(仍然收敛 ——
    编号权威), 由看板的 ``platform_shop_id_conflict`` 告警暴露。

    Args:
        index: :func:`build_identity_index` 的产物。
        platform_code: 平台码(``shopee`` / ``tiktok`` …)。
        signals: ``{"shop_account_id": ..., "platform_shop_id": ..., "shop_id": ...,
            "store_name": ...}`` —— 空值会被忽略。

    Returns:
        :class:`ReconciliationResult`:
        * ``converged`` —— 某个信号唯一命中了一个账号;
        * ``conflict`` —— 没有信号能唯一命中, 但存在**歧义**信号(多账号认领);
        * ``unresolved`` —— 一个都没命中(保持原样)。
    """
    platform = _platform_key(platform_code)
    primary: MasterIdentity | None = None
    matched: list[str] = []
    conflicts: list[str] = []
    ambiguous: list[str] = []

    for signal in SIGNAL_PRIORITY:
        value = _identity_text(signals.get(signal))
        if not value:
            continue
        candidates = [
            identity
            for identity in index.lookup(signal, value)
            if not platform or identity.platform == platform
        ]
        if not candidates:
            continue
        if len(candidates) > 1:
            # 同一串值被多个账号认领 ⇒ 该信号不可用(绝不挑一个)
            ambiguous.append(signal)
            continue
        identity = candidates[0]
        if primary is None:
            primary = identity
            matched.append(signal)
            continue
        if identity.shop_account_id != primary.shop_account_id:
            # 低优先级信号指向别的账号 ⇒ 记冲突, 但**不推翻**编号权威
            conflicts.append(signal)
        else:
            matched.append(signal)

    if primary is not None:
        return ReconciliationResult(
            status=STATUS_CONVERGED,
            identity=primary,
            conflict_signals=tuple(sorted(set(conflicts))),
            matched_signals=tuple(matched),
            ambiguous_signals=tuple(sorted(set(ambiguous))),
        )
    if ambiguous:
        return ReconciliationResult(
            status=STATUS_CONFLICT,
            identity=None,
            conflict_signals=tuple(sorted(set(ambiguous))),
            matched_signals=(),
            ambiguous_signals=tuple(sorted(set(ambiguous))),
        )
    return ReconciliationResult(
        status=STATUS_UNRESOLVED,
        identity=None,
        matched_signals=(),
    )


def converged_shop_id_value(identity: MasterIdentity, fallback: str = "") -> str:
    """收敛后该行/该文件的 ``shop_id`` 该取什么。

    * 有平台编号(Shopee)⇒ 用**主数据登记的编号**;
    * 没有平台编号(TikTok)⇒ **保留原值**。

    ⚠️ 保留原值不是偷懒 —— 是为了不动**文件级 upsert 冲突键**
    ``(platform_code, shop_id, data_domain, granularity, data_hash)``:
    改了它, 将来重采同一份文件会**插入重复行**而不是覆盖。
    """
    return identity.platform_shop_id or fallback


def apply_reconciliation(
    row: Mapping[str, Any],
    result: ReconciliationResult,
) -> dict[str, Any]:
    """把收敛结果写回一行(**只改身份键**)。

    非收敛时原样返回 —— 冲突/无法确定的行必须保留原貌, 让语义层照旧落
    ``unknown``, 再由看板的 ``platform_shop_id_conflict`` 告警暴露出来。
    """
    updated = dict(row)
    if not result.converged or result.identity is None:
        return updated
    identity = result.identity

    for key in _STORE_NAME_KEYS:
        if key in updated:
            updated[key] = identity.store_name
    for key in _PLATFORM_SHOP_ID_KEYS:
        if key in updated:
            if identity.platform_shop_id:
                updated[key] = identity.platform_shop_id
            else:
                updated.pop(key, None)
    for key in _SHOP_ACCOUNT_ID_KEYS:
        if key in updated:
            updated[key] = identity.shop_account_id

    # `shop_id`: 有平台编号才改(见 converged_shop_id_value 的说明)
    if identity.platform_shop_id:
        updated["shop_id"] = identity.platform_shop_id

    # 行内**必须**带上权威锚点 —— 即使原行没有这两个键
    updated["shop_account_id"] = identity.shop_account_id
    updated["store_name"] = identity.store_name
    # 平台编号也补上: 语义层的 source_platform_shop_id 会读它,
    # 补上之后行内四路候选全部指向同一个账号 ⇒ 候选数必然为 1。
    # (与历史订正迁移写回的 raw_data 形态完全一致 ⇒ 新旧行同构)
    if identity.platform_shop_id:
        updated["platform_shop_id"] = identity.platform_shop_id
    else:
        updated.pop("platform_shop_id", None)
    return updated


def collect_row_signals(row: Mapping[str, Any]) -> dict[str, str]:
    """从一行里抽出身份信号。

    ⚠️ ``shop_id`` 与 ``platform_shop_id`` 都按「平台店铺编号」反查 ——
    行内 ``shop_id`` 存的就是平台编号(妙手导出的那一列);
    TikTok 那边的 ``shop_id`` 存的是导出店名, 编号索引查不到时会自动
    退回别名索引(见 :meth:`IdentityIndex.lookup`)。
    """
    signals: dict[str, str] = {}
    for signal, keys in (
        ("platform_shop_id", _PLATFORM_SHOP_ID_KEYS),
        ("shop_id", _SHOP_ID_KEYS),
        ("shop_account_id", _SHOP_ACCOUNT_ID_KEYS),
        ("store_name", _STORE_NAME_KEYS),
    ):
        for key in keys:
            value = _identity_text(row.get(key))
            if value:
                signals[signal] = value
                break
    return signals
