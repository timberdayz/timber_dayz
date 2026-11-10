from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    create_engine,
    insert,
    inspect as sa_inspect,
    select,
    text,
    update,
)

from backend.services.cloud_b_class_mirror_manager import build_canonical_columns
from backend.services.cloud_b_class_sync_utils import (
    quote_ident,
    validate_b_class_table_name,
)
from backend.services.cloud_sync_identity_guard_service import (
    DUAL_BASELINE_CONSISTENT,
    DUAL_BASELINE_MISMATCH,
    DUAL_BASELINE_NOT_APPLIED,
    DUAL_BASELINE_UNAVAILABLE,
    LOAD_STATUS_DISABLED,
    collect_registry_mismatch_events,
)
from backend.services.shop_identity_conflict_ledger_service import (
    REASON_LOCAL_REGISTRY_AMBIGUOUS,
    REASON_LOCAL_TOKEN_MISMATCH,
    ConflictRowRecord,
    build_row_locator,
    conflict_record_from_mismatch_event,
    extract_business_date,
    notify_new_conflict_rows,
    pick_identity_value,
)
from backend.services.data_pipeline.refresh_queue_service import (
    RefreshQueueService,
    resolve_refresh_lane,
)
from backend.services.shop_identity_reconciliation_service import (
    row_identity_accounts,
    row_identity_tokens,
)
from modules.core.db import CloudSyncReceiveLog, RefreshQueueTask
from modules.core.logger import get_logger


logger = get_logger(__name__)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sync_batch_status(conflict_rows: int, degraded_rows: int) -> str:
    """同步状态: 有行**没落库**(真矛盾 / 被双基准降级)⇒ ``partial_success``。

    ⚠️ 降级行同样没写进云端 ⇒ 状态不能记 ``completed``(否则账本虚报)。
    """
    return "partial_success" if (conflict_rows or degraded_rows) else "completed"


def _sync_identity_error_code(conflict_rows: int, degraded_rows: int) -> str | None:
    """身份相关的错误码(矛盾优先于降级)。"""
    if conflict_rows:
        return "identity_conflict_rows_present"
    if degraded_rows:
        return "identity_registry_mismatch_rows_present"
    return None


#: 行内「店铺身份」候选键(优先级从高到低)。
#:
#: ⚠️ 事实表的 **列** ``shop_id`` **不在这里** —— 它是「采集层写进来的原始标识」,
#: 不是身份列(shopee 上是平台编号 / tiktok 上是导出店名 / miaoshou 采集链上是
#: 采集方代号 ``xihong``),拿它当身份列判会误杀正常数据。
#: 仓库对该列的成文定性见 ``sql/semantic/orders_atomic.sql`` 与
#: ``sql/semantic/inventory_snapshot.sql`` 的注释。
#:
#: ⚠️ 行内身份的**解析实现**住在身份真相点
#: ``shop_identity_reconciliation_service``(SSOT)——
#: 同步侧拦截与云端巡检共用同一份, 这里不再另写一份。


@dataclass(frozen=True)
class IdentitySplitResult:
    """行内身份判定的**三分**结果(SSOT: 同步侧唯一的身份裁决出口)。

    三类行
    ------
    * ``consistent`` —— **会落云端**的行。既包含"唯一归属到主数据账号"的自洽行,
      也包含"行内无身份线索"或"归属不到任何账号"的行。
    * ``unresolved`` —— ``consistent`` 的**子集**: 行内带了身份线索, 但在主数据里
      **归属不到任何账号**(停用店 / 历史数据缺戳 / 别名未覆盖)。
      这些行**照常落库**(不能当成坏数据丢掉), 但会被计数并告警。
    * ``conflicting`` —— **真矛盾**: 行内的多个身份键指向了**不同的**主数据账号。
      这些行**不写云端**(宁可少同步一行, 也不要在云端造出"内容与身份不符"的混合行)。

    为什么要分成三类
    ----------------
    2026-11-07 的事故把「无法归属」和「自相矛盾」混为一谈:
    前者(其实是**好数据**)被当成后者**静默丢弃** 3,714 行, 账本却记 "completed"。
    拆开之后, 账本能分别记「落库行数 / 未归属行数 / 被拒行数」,
    作业状态也能只在**真丢数据**时才是 ``partial_success``。
    """

    #: 会落云端的行(unresolved 是它的子集)
    consistent: list[dict[str, Any]] = field(default_factory=list)
    #: 真矛盾、不写云端的行
    conflicting: list[dict[str, Any]] = field(default_factory=list)
    #: 落库但归属不到主数据账号的行(consistent 的子集)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    #: ``consistent`` 各行在**入参列表**中的下标(供检查点定位最后一行落库数据)
    written_indexes: tuple[int, ...] = ()
    #: 被「**双基准不一致**」降级的行(可观测事件负载, 不含行体)
    #:
    #: 这些行**不写云端** —— 写上去云端会用**云端**的登记去解释, 可能指向别的店
    #: ⇒ 归属塌陷。它们被记成可观测事件(见
    #: :mod:`backend.services.cloud_sync_identity_guard_service`)。
    degraded: list[dict[str, Any]] = field(default_factory=list)
    #: 被降级行在**入参列表**中的下标
    degraded_indexes: tuple[int, ...] = ()
    #: 双基准状态: ``not_applied`` / ``consistent`` / ``mismatch`` / ``unavailable``
    dual_baseline_status: str = DUAL_BASELINE_NOT_APPLIED
    #: **矛盾行台账**的行级负载(批次 4.3)。
    #:
    #: 每条对应一个「被跳过 / 被降级」的行, 带原因码与定位信息(不含行体)。
    #: ⇒ 记进 ``ops.shop_identity_conflict_rows``(**只记不阻塞**)。
    #: ⚠️ 这些行**不写云端**, 但**不改变**检查点推进算法
    #: (推进到最后一个落库行 —— 不改成「停在第一个矛盾行」, 那会永久卡死)。
    conflict_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def written_rows(self) -> int:
        """真正写进云端的行数。"""
        return len(self.consistent)

    @property
    def conflict_rows(self) -> int:
        """因身份矛盾被拒、**没有**写进云端的行数。"""
        return len(self.conflicting)

    @property
    def unresolved_rows(self) -> int:
        """落库但归属不到主数据账号的行数。"""
        return len(self.unresolved)

    @property
    def degraded_rows(self) -> int:
        """因「本地/云端登记信息不一致」被降级、**没有**写进云端的行数。"""
        return len(self.degraded)

    @property
    def last_written_index(self) -> int:
        """最后一行落库数据在入参列表中的下标; 一行都没落库时为 ``-1``。

        ⚠️ 检查点**只能**推进到这个位置 —— 推进到 ``rows[-1]`` 就等于
        把"被拒的行"也一并跳过, 那正是 2026-11-07 丢数的机制。
        """
        return self.written_indexes[-1] if self.written_indexes else -1


def split_rows_by_identity_consistency(
    rows: list[dict[str, Any]],
    identity_index: Any = None,
) -> IdentitySplitResult:
    """把待同步的行按「行内身份」分成三类(自洽 / 未归属 / 真矛盾)。

    为什么需要这一步
    ----------------
    同步的 upsert 冲突键是 ``(platform_code, shop_id, data_domain, granularity,
    data_hash)``, 而 ``data_hash`` **不含 raw_data** ⇒ 两行只要核心业务字段相同,
    就会撞到同一个冲突键上。

    于是: 本地第一行(行内身份=A) 写进去之后, 第二行(行内身份=**B**) 会命中冲突键,
    ``DO UPDATE`` 把 raw_data 改成 B 的 ⇒ 云端留下一行「内容与身份不符」的
    **混合行**。这正是同步侧的**放大器**。

    判据:行内身份**能否唯一归属到一个主数据账号**
    -------------------------------------------
    取行内 ``raw_data`` 的身份键(平台编号 / 账号 ID / 中文店铺列 / ``store_name``),
    逐个到**主数据账号索引**反查, 汇总它们指向的账号集合:

    * 恰好 **1 个账号** ⇒ **自洽**, 落库;
    * **0 个账号** ⇒ **未归属**(停用店 / 历史数据缺戳 / 别名未覆盖)⇒ **照常落库**,
      但计入「未归属」计数并告警 —— 这不是「矛盾」, 不该当成坏数据丢弃;
    * **>1 个账号** ⇒ **真矛盾**(行内两个身份键指向不同的店)⇒ **不写云端**。

    宁可少同步一行, 也不要把混合行搬进云端 ——
    云端那一份是看板与对比分析的数据源, 污染它比缺它更难发现。

    ⚠️ **为什么不再拿事实表的 ``shop_id`` 列来比**
    ------------------------------------------
    2026-11-07 上线的旧判据是「列 ``shop_id`` vs ``raw_data['shop_id']``」。
    但那一列**不是身份列** —— 它装的是采集层写进来的原始标识:
    shopee 上是平台店铺编号、tiktok 上是导出店名、miaoshou 采集链上是
    采集方代号 ``xihong``。拿它当身份列, 等于拿「平台编号」去比「账号 ID」,
    **同源的两层也永远不相等**。

    实测(本地 dev 库 65,197 行):旧判据误杀 **3,781 行正常数据**,
    且这些行在语义层能正常归属到唯一店铺 —— 数据本来是好的, 是在同步侧被扔掉的。

    ⚠️ **为什么不能只靠字符串比较行内的两个键**
    ------------------------------------------
    账号 ID(``shopee_my_xhkj1_local``)与平台编号(``1540271739``)是**不同形态**,
    归一化后也互不包含 ⇒ 纯字符串比较会把「同一个店」判成矛盾
    (实测误判 15,884 行 products 数据)。**必须查主数据**才能判定归属。

    ``identity_index`` 为 None(拿不到主数据)时, 退化为「只比同形态的键」,
    宁可少拦也不误杀 —— 拦错会静默丢数, 不拦最多留下待人工处理的一批。
    降级模式下没有「归属」概念, 因此不产生 ``unresolved`` 计数。

    返回:
        :class:`IdentitySplitResult`
    """
    consistent: list[dict[str, Any]] = []
    conflicting: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    written_indexes: list[int] = []
    conflict_events: list[dict[str, Any]] = []

    for index, row in enumerate(rows or []):
        tokens = row_identity_tokens(row)

        mismatch = ""
        is_unresolved = False
        reason_code = ""
        resolved_accounts: list[str] = []

        if identity_index is not None:
            accounts = row_identity_accounts(
                row, identity_index, _text(row.get("platform_code"))
            )
            if len(accounts) > 1:
                reason_code = REASON_LOCAL_REGISTRY_AMBIGUOUS
                resolved_accounts = sorted(accounts)
                mismatch = "row identity resolves to %d accounts: %s" % (
                    len(accounts),
                    sorted(accounts),
                )
            elif not accounts and tokens:
                # 行内带了身份线索, 但主数据里认不到 ⇒ 未归属(不是矛盾)
                is_unresolved = True
        else:
            # 无主数据时的降级判据: 只在**同形态**的键之间比较。
            # (编号 vs 账号 ID 属不同形态, 不可直接比 —— 见上文说明)
            platform_shop_id = tokens.get("platform_shop_id")
            raw_shop_id = tokens.get("shop_id")

            numeric_ids = {
                value
                for value in (platform_shop_id, raw_shop_id)
                if value and value.isdigit()
            }
            if len(numeric_ids) > 1:
                reason_code = REASON_LOCAL_TOKEN_MISMATCH
                mismatch = (
                    "raw_data.platform_shop_id=%s disagrees with raw_data.shop_id=%s"
                    % (
                        platform_shop_id,
                        raw_shop_id,
                    )
                )

            store_label = tokens.get("store_label")
            if not mismatch and store_label and platform_shop_id:
                if (
                    store_label != platform_shop_id
                    and store_label not in platform_shop_id
                    and platform_shop_id not in store_label
                ):
                    reason_code = REASON_LOCAL_TOKEN_MISMATCH
                    mismatch = (
                        "raw_data.store_label=%s disagrees with "
                        "raw_data.platform_shop_id=%s" % (store_label, platform_shop_id)
                    )

        if mismatch:
            conflicting.append(row)
            conflict_events.append(
                _build_conflict_event(
                    row,
                    index=index,
                    reason_code=reason_code,
                    identity_tokens=tokens,
                    resolved_accounts=resolved_accounts,
                )
            )
        else:
            consistent.append(row)
            written_indexes.append(index)
            if is_unresolved:
                unresolved.append(row)

    return IdentitySplitResult(
        consistent=consistent,
        conflicting=conflicting,
        unresolved=unresolved,
        written_indexes=tuple(written_indexes),
        conflict_events=conflict_events,
    )


def _build_conflict_event(
    row: dict[str, Any],
    *,
    index: int,
    reason_code: str,
    identity_tokens: dict[str, str],
    resolved_accounts: list[str],
) -> dict[str, Any]:
    """构造一条**矛盾行台账**负载(批次 4.3)。

    只放**定位**信息(表 / 日期 / 行内那列的值 / 认出的账号 / 原因码),
    **不放行体** —— 行体可能很大, 而且台账会被运维看到。
    """
    business_date = extract_business_date(row)
    source_row_id = row.get("id")
    data_hash = str(row.get("data_hash") or "")
    return {
        "reason_code": reason_code,
        "row_locator": build_row_locator(
            source_row_id=source_row_id,
            data_hash=data_hash,
        ),
        "source_row_id": "" if source_row_id is None else str(source_row_id),
        "platform_code": _text(row.get("platform_code")),
        "business_date": business_date,
        "identity_value": pick_identity_value(identity_tokens),
        "identity_tokens": dict(identity_tokens),
        "resolved_account_id": (
            resolved_accounts[0] if len(resolved_accounts) == 1 else ""
        ),
        "resolved_accounts": list(resolved_accounts),
        "cloud_accounts": [],
        "row_index": index,
    }


def split_rows_by_dual_baseline(
    rows: list[dict[str, Any]],
    identity_index: Any = None,
    cloud_registry: Any = None,
) -> IdentitySplitResult:
    """在本地单基准判定之上, **再与云端登记信息比一次**(批次 3.7)。

    为什么需要这一步
    ----------------
    本地单基准只看**本地**那份登记信息(``core.shop_accounts`` /
    ``core.shop_account_aliases``)。但**云端也有一份登记信息** ——
    两边不同步时(采集机本地台账与云端台账不一致), 本地判「自洽」的行推到云端后,
    云端会用**云端**的登记去解释它 ⇒ 可能指向别的店 ⇒ **归属塌陷**(语义层落
    ``unknown``)。

    ⇒ 所以推送前比一次: 两边解释不一致 ⇒ 该行**降级为可观测事件**,
    **不再当自洽行直接放行**(不写云端), 但**不阻塞同步**。

    「两边不一致」的判定口径
    ----------------------
    设 ``L`` = 本地解析出的账号集合, ``C`` = 云端解析出的账号集合
    (两边用**同一份**解析实现 ``row_identity_accounts``, 口径不会分叉):

    * ``len(L) == 1`` 且 ``C == L`` ⇒ **一致** ⇒ 行为与改造前**完全相同**;
    * ``C`` 为空 ⇒ 本地认出的账号, 云端**认不出** ⇒ **不一致**;
    * ``C`` 与 ``L`` 不同 ⇒ 云端把它**指向另一个账号** ⇒ **不一致**;
    * ``len(C) > 1`` ⇒ 云端自己都认不唯一 ⇒ **不一致**。

    ⚠️ **未归属行不做跨端比较** —— 本地没唯一认出来时没有可比对的基准,
    行为保持不变(照常落库 + 计数 + 告警)。

    云端不可达 ⇒ 优雅降级
    ---------------------
    ``cloud_registry`` 为 None / 不可用 ⇒ **退回本地单基准判定**
    (行为与改造前一致), 并由调用方记一条「双基准不可用」事件。
    **绝不能因为云端连不上就把同步搞挂。**

    Args:
        rows: 待同步的行。
        identity_index: 本地主数据反查索引(None ⇒ 本地降级判据)。
        cloud_registry: :class:`backend.services.cloud_sync_identity_guard_service.
            CloudIdentityRegistry`; None / 不可用 ⇒ 不做跨端比较。
    """
    base = split_rows_by_identity_consistency(rows, identity_index)

    registry = cloud_registry
    if registry is not None and getattr(registry, "status", "") == (
        LOAD_STATUS_DISABLED
    ):
        # 守卫被人工关掉 ⇒ 行为与本批次上线前**完全一致**。
        return IdentitySplitResult(
            consistent=base.consistent,
            conflicting=base.conflicting,
            unresolved=base.unresolved,
            written_indexes=base.written_indexes,
            dual_baseline_status=DUAL_BASELINE_NOT_APPLIED,
            conflict_events=list(base.conflict_events),
        )
    if (
        identity_index is None
        or registry is None
        or not getattr(registry, "available", False)
    ):
        # 双基准不可用(本地台账拿不到 / 云端台账拿不到)⇒ 退回本地单基准
        # (行为与改造前一致)。
        return IdentitySplitResult(
            consistent=base.consistent,
            conflicting=base.conflicting,
            unresolved=base.unresolved,
            written_indexes=base.written_indexes,
            dual_baseline_status=DUAL_BASELINE_UNAVAILABLE,
            conflict_events=list(base.conflict_events),
        )

    cloud_index = registry.index
    events = collect_registry_mismatch_events(
        rows,
        consistent_indexes=base.written_indexes,
        local_index=identity_index,
        cloud_index=cloud_index,
    )
    if not events:
        # 两边一致 ⇒ 行为与改造前**完全相同**。
        return IdentitySplitResult(
            consistent=base.consistent,
            conflicting=base.conflicting,
            unresolved=base.unresolved,
            written_indexes=base.written_indexes,
            dual_baseline_status=DUAL_BASELINE_CONSISTENT,
            conflict_events=list(base.conflict_events),
        )

    degraded_indexes = {event.row_index for event in events}
    kept_rows: list[dict[str, Any]] = []
    kept_indexes: list[int] = []
    for row, index in zip(base.consistent, base.written_indexes):
        if index in degraded_indexes:
            continue
        kept_rows.append(row)
        kept_indexes.append(index)

    # ⚠️ ``unresolved`` **不用**摘: 降级只发生在「本地唯一认出」的行上,
    # 而 ``unresolved`` 是「本地认不出」的行 —— 两者互斥。
    #
    # ⚠️ **检查点推进算法不变** —— 降级行同样不参与 ``written_indexes``,
    # 检查点照样推进到「最后一个落库行」。**绝不**改成「停在第一个矛盾行」
    # (那会让 ``fact_shopee_products_daily`` 永久卡死 —— 历史不修 ⇒
    # 那些行的归属永远不会被修)。
    degraded_payloads = [event.to_payload() for event in events]
    conflict_events = list(base.conflict_events)
    for payload in degraded_payloads:
        record = conflict_record_from_mismatch_event(payload)
        conflict_events.append(
            {
                "reason_code": record.reason_code,
                "row_locator": record.row_locator,
                "source_row_id": record.source_row_id,
                "platform_code": record.platform_code,
                "business_date": record.business_date,
                "identity_value": record.identity_value,
                "identity_tokens": record.identity_tokens,
                "resolved_account_id": record.resolved_account_id,
                "resolved_accounts": record.resolved_accounts,
                "cloud_accounts": record.cloud_accounts,
            }
        )
    return IdentitySplitResult(
        consistent=kept_rows,
        conflicting=base.conflicting,
        unresolved=base.unresolved,
        written_indexes=tuple(kept_indexes),
        degraded=degraded_payloads,
        degraded_indexes=tuple(sorted(degraded_indexes)),
        dual_baseline_status=DUAL_BASELINE_MISMATCH,
        conflict_events=conflict_events,
    )


def build_sync_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Build canonical sync payload from one local B-class row."""
    payload = {column: row.get(column) for column in build_canonical_columns()}
    if payload.get("data_domain") != "services" and payload.get("shop_id") is None:
        payload["shop_id"] = ""
    raw_data = payload.get("raw_data")
    if isinstance(raw_data, dict):
        raw_payload = dict(raw_data)
    else:
        raw_payload = {}
        if raw_data not in (None, ""):
            raw_payload["_cloud_sync_original_raw_data"] = raw_data
    if row.get("file_id") is not None:
        raw_payload["_cloud_sync_source_file_id"] = row.get("file_id")
    if raw_payload:
        payload["raw_data"] = raw_payload
    # Cloud-side raw facts do not own the local file/template dimension rows.
    payload["file_id"] = None
    payload["template_id"] = None
    return payload


class SQLAlchemyBClassSourceReader:
    """Read canonical rows from local B-class tables."""

    def __init__(self, engine):
        self.engine = engine

    def _build_select_sql(
        self,
        table_name: str,
        where_sql: str,
        available_columns: set[str] | None = None,
    ) -> str:
        validate_b_class_table_name(table_name)
        select_columns = []
        for column in build_canonical_columns():
            if available_columns is None or column in available_columns:
                select_columns.append(column)
            else:
                select_columns.append(f"NULL AS {column}")
        where_clause = f"WHERE {where_sql}" if where_sql else ""
        return (
            f'SELECT id, {", ".join(select_columns)} '
            f"FROM b_class.{quote_ident(table_name)} "
            f"{where_clause} "
            "ORDER BY ingest_timestamp ASC, id ASC "
            "LIMIT :batch_size"
        )

    def __call__(self, table_name: str, checkpoint, batch_size: int = 1000):
        where_sql, params = CloudBClassSyncService._build_checkpoint_where_clause(
            checkpoint
        )
        inspector = sa_inspect(self.engine)
        available_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema="b_class")
        }
        sql = self._build_select_sql(
            table_name, where_sql, available_columns=available_columns
        )
        bind_params = dict(params)
        bind_params["batch_size"] = batch_size
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), bind_params)
            return [dict(row) for row in result.mappings().all()]


class SQLAlchemyCloudWriter:
    """Write canonical rows to cloud mirror tables via PostgreSQL upsert."""

    TARGET_SCHEMA = "b_class"

    def __init__(
        self,
        engine,
        dry_run: bool = False,
        identity_index: Any = None,
        cloud_registry: Any = None,
        guard_event_recorder: Any = None,
        conflict_ledger_recorder: Any = None,
    ):
        self.engine = engine
        self.dry_run = dry_run
        #: 主数据账号索引 —— 供身份自洽判定使用(见
        #: :func:`split_rows_by_identity_consistency`)。None ⇒ 降级判据。
        self.identity_index = identity_index
        #: **云端**登记信息快照(批次 3.7 双基准守卫)。None / 不可用 ⇒
        #: 退回本地单基准判定(行为与改造前一致)。
        self.cloud_registry = cloud_registry
        #: 双基准守卫的可观测事件台账(None ⇒ 不记事件)。
        self.guard_event_recorder = guard_event_recorder
        #: **矛盾行台账**(批次 4.3, ``ops.shop_identity_conflict_rows``)。
        #: None ⇒ 不记台账。
        self.conflict_ledger_recorder = conflict_ledger_recorder
        #: 「双基准不可用」事件**每轮只记一次**(避免每批次刷一条)。
        self._guard_unavailable_reported = False

    def _record_conflict_ledger(
        self,
        split: IdentitySplitResult,
        *,
        table_name: str,
        data_domain: str,
    ) -> dict[str, Any]:
        """把被跳过 / 被降级的行记进**矛盾行台账**(批次 4.3)。

        ⚠️ **只记不阻塞** —— 台账写失败(表不存在 / 连不上 / 约束冲突)只记 warning,
        **同步照跑, 写入结果不变**。
        ⚠️ 台账写入走**独立**的事务 ⇒ **不参与**同步的写入事务。

        Returns:
            摘要字典(``new_rows`` / ``seen_rows`` / ``status`` …);
            没有配台账时返回 ``{"status": "not_configured", ...}``。
        """
        recorder = self.conflict_ledger_recorder
        if recorder is None:
            return {
                "status": "not_configured",
                "new_rows": 0,
                "seen_rows": 0,
                "total_rows": 0,
            }
        if not split.conflict_events:
            return {
                "status": "skipped",
                "reason": "no_conflict_rows",
                "new_rows": 0,
                "seen_rows": 0,
                "total_rows": 0,
            }
        try:
            summary = recorder.record_conflicts(
                source_table_name=table_name,
                data_domain=data_domain,
                records=split.conflict_events,
            )
        except Exception as exc:  # noqa: BLE001 - 台账写失败绝不阻塞同步
            logger.warning(
                "[CloudSync] [%s] 矛盾行台账写入失败(不影响同步): %s", table_name, exc
            )
            return {"status": "failed", "error": str(exc), "new_rows": 0}
        if not isinstance(summary, dict):
            return {"status": "skipped", "new_rows": 0}
        summary.setdefault("source_table_name", table_name)
        summary.setdefault("data_domain", data_domain)
        summary["reason_codes"] = sorted(
            {
                str(event.get("reason_code") or "")
                for event in split.conflict_events
                if event.get("reason_code")
            }
        )
        return summary

    def _report_guard_events(
        self,
        split: IdentitySplitResult,
        *,
        table_name: str,
        data_domain: str,
        ledger_summary: dict[str, Any] | None = None,
    ) -> None:
        """把双基准守卫的可观测事件记进台账。

        ⚠️ **记事件失败绝不阻塞同步** ⇒ 这里兜住所有异常。

        ⚠️ **批次 4.3: 事件不再重复写**
        --------------------------------
        批次 3.7 留下的已知问题: 整批被降级时检查点停在当前水位 ⇒ 下一轮会读到
        同一批 ⇒ **同样的事件被重复记一条**。

        ⇒ 现在「双基准不一致」事件**只在本批出现了台账里没有的新行时才记**
        (``ledger_summary['new_rows'] > 0``)。去重口径与矛盾行台账**完全同一套**
        (同一「源表 + 业务日期 + 行内定位 + 原因码」)⇒ **不写第二套**。

        ⚠️ 台账**没配**或**写失败**时 ⇒ 事件照记(宁可多记一条, 也不丢可观测性)。
        """
        recorder = self.guard_event_recorder
        if recorder is None:
            return
        try:
            if split.degraded_rows:
                # ⚠️ **只有台账「成功写入」且「本批没有新行」时**才跳过事件。
                # 台账没配 / 写失败 ⇒ 事件照记(宁可多记一条, 也不丢可观测性)。
                already_seen = (
                    isinstance(ledger_summary, dict)
                    and ledger_summary.get("status") == "recorded"
                    and int(ledger_summary.get("new_rows") or 0) <= 0
                )
                if already_seen:
                    logger.info(
                        "[CloudSyncGuard] [%s] %d 行本地/云端登记信息不一致, "
                        "台账里已全部见过 ⇒ 不重复记事件",
                        table_name,
                        split.degraded_rows,
                    )
                    return
                recorder.record_mismatch(
                    source_table_name=table_name,
                    data_domain=data_domain,
                    events=split.degraded,
                    registry=self.cloud_registry,
                )
                logger.error(
                    "[CloudSyncGuard] [%s] %d 行本地/云端登记信息不一致, "
                    "已降级为可观测事件(不写云端)",
                    table_name,
                    split.degraded_rows,
                )
                return
            if (
                split.dual_baseline_status == DUAL_BASELINE_UNAVAILABLE
                and not self._guard_unavailable_reported
            ):
                # 「双基准不可用」每轮只记一次(否则每批次刷一条)。
                self._guard_unavailable_reported = True
                reason = str(getattr(self.cloud_registry, "reason", "") or "")
                if self.identity_index is None:
                    reason = (
                        "%s;local_registry_unavailable" % reason
                        if reason
                        else "local_registry_unavailable"
                    )
                recorder.record_unavailable(
                    source_table_name=table_name,
                    reason=reason,
                    registry=self.cloud_registry,
                )
                logger.warning(
                    "[CloudSyncGuard] [%s] 双基准不可用(%s), 已退回本地单基准判定",
                    table_name,
                    reason,
                )
        except Exception as exc:  # noqa: BLE001 - 记事件绝不阻塞同步
            logger.warning("[CloudSyncGuard] 可观测事件记录失败(不影响同步): %s", exc)

    @staticmethod
    def _build_upsert_sql(table_name: str, data_domain: str) -> str:
        columns = build_canonical_columns()
        column_list = ", ".join(columns)
        bind_list = ", ".join(f":{column}" for column in columns)
        # [*] shop_id 与 raw_data **绑定**: 两者要么一起更新, 要么都不更新。
        #
        # 为什么不把 shop_id 留在「不更新」那一组: 冲突键里就带着 shop_id
        # (services 域除外), 留着不更新就会产生「列是 A、内容是 B」的混合行 ——
        # 而 raw_data 恰恰是**要被更新**的那个, 两者一拆开就必然不同源。
        # 把它放进更新组, 就等于宣告「这一行的身份与内容同进同退」。
        update_fields = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column
            not in {
                "platform_code",
                "data_domain",
                "granularity",
                "sub_domain",
                "data_hash",
            }
        )
        if data_domain == "services":
            conflict_clause = "(data_domain, sub_domain, granularity, data_hash)"
        else:
            conflict_clause = (
                "(platform_code, shop_id, data_domain, granularity, data_hash)"
            )
        return (
            f'INSERT INTO {SQLAlchemyCloudWriter.TARGET_SCHEMA}."{table_name}" ({column_list}) '
            f"VALUES ({bind_list}) "
            f"ON CONFLICT {conflict_clause} DO UPDATE SET {update_fields}"
        )

    def __call__(self, table_name: str, rows: list[dict[str, Any]], data_domain: str):
        if self.dry_run:
            return {
                "success": True,
                "written_rows": len(rows),
                "dry_run": True,
                "last_written_index": len(rows) - 1,
            }

        split = split_rows_by_dual_baseline(
            rows,
            self.identity_index,
            self.cloud_registry,
        )
        ledger_summary = self._record_conflict_ledger(
            split,
            table_name=table_name,
            data_domain=data_domain,
        )
        self._report_guard_events(
            split,
            table_name=table_name,
            data_domain=data_domain,
            ledger_summary=ledger_summary,
        )
        if split.conflict_rows:
            logger.error(
                "[CloudSync] [%s] %d 行行内身份自相矛盾, 已跳过不写云端",
                table_name,
                split.conflict_rows,
            )

        sql = self._build_upsert_sql(table_name, data_domain)
        prepared_rows = self._prepare_rows_for_insert(split.consistent)
        with self.engine.begin() as conn:
            if prepared_rows:
                conn.execute(text(sql), prepared_rows)
        return {
            "success": True,
            "written_rows": split.written_rows,
            "identity_conflict_rows": split.conflict_rows,
            "identity_unresolved_rows": split.unresolved_rows,
            "identity_registry_mismatch_rows": split.degraded_rows,
            "dual_baseline_status": split.dual_baseline_status,
            "last_written_index": split.last_written_index,
            "conflict_ledger": ledger_summary,
        }

    def write_rows_with_receive_log(
        self,
        *,
        table_name: str,
        rows: list[dict[str, Any]],
        data_domain: str,
        receive_log_recorder: "CloudSyncReceiveLogRecorder",
        receive_log_context: dict[str, Any],
    ) -> dict[str, Any]:
        if self.dry_run:
            return {
                "success": True,
                "written_rows": len(rows),
                "dry_run": True,
                "last_written_index": len(rows) - 1,
            }

        split = split_rows_by_dual_baseline(
            rows,
            self.identity_index,
            self.cloud_registry,
        )
        ledger_summary = self._record_conflict_ledger(
            split,
            table_name=table_name,
            data_domain=data_domain,
        )
        self._report_guard_events(
            split,
            table_name=table_name,
            data_domain=data_domain,
            ledger_summary=ledger_summary,
        )
        if split.conflict_rows:
            logger.error(
                "[CloudSync] [%s] %d 行行内身份自相矛盾, 已跳过不写云端",
                table_name,
                split.conflict_rows,
            )
        if split.unresolved_rows:
            logger.warning(
                "[CloudSync] [%s] %d 行行内身份归属不到主数据账号, 已照常落库并计数",
                table_name,
                split.unresolved_rows,
            )

        sql = self._build_upsert_sql(table_name, data_domain)
        prepared_rows = self._prepare_rows_for_insert(split.consistent)
        # ⚠️ 账本必须记**真正落库**的行数, 不是"送进来"的行数 ——
        # 2026-11-07 事故里账本记 72 行 / 实际落库 0 行, 就是记了送进去的行数。
        receive_context = dict(receive_log_context)
        receive_context["written_rows"] = split.written_rows
        receive_context["identity_conflict_rows"] = split.conflict_rows
        receive_context["identity_unresolved_rows"] = split.unresolved_rows
        # ⚠️ 被降级(不写云端)的行也算「没落库」⇒ 状态不能记 completed,
        # 否则账本又会虚报(2026-11-07 的形态)。
        receive_context["status"] = (
            "partial_success"
            if (split.conflict_rows or split.degraded_rows)
            else "completed"
        )
        with self.engine.begin() as conn:
            if prepared_rows:
                conn.execute(text(sql), prepared_rows)
            receive_result = receive_log_recorder.record_success_on_connection(
                conn,
                **receive_context,
            )
        return {
            "success": True,
            "written_rows": split.written_rows,
            "identity_conflict_rows": split.conflict_rows,
            "identity_unresolved_rows": split.unresolved_rows,
            "identity_registry_mismatch_rows": split.degraded_rows,
            "dual_baseline_status": split.dual_baseline_status,
            "last_written_index": split.last_written_index,
            "receive_log": receive_result,
            "receive_id": receive_result.get("receive_id"),
            "conflict_ledger": ledger_summary,
        }

    @staticmethod
    def _prepare_rows_for_insert(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            if isinstance(record.get("raw_data"), dict):
                record["raw_data"] = json.dumps(record["raw_data"], ensure_ascii=False)
            if isinstance(record.get("header_columns"), list):
                record["header_columns"] = json.dumps(
                    record["header_columns"], ensure_ascii=False
                )
            prepared_rows.append(record)
        return prepared_rows


class CloudSyncReceiveLogRecorder:
    """Append cloud-side receive ledger rows after successful mirror writes."""

    def __init__(self, engine, source_environment: str | None = None):
        self.engine = engine
        self.source_environment = source_environment

    @staticmethod
    def _coerce_business_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @classmethod
    def _business_date_range(
        cls, rows: list[dict[str, Any]]
    ) -> tuple[date | None, date | None]:
        dates: list[date] = []
        for row in rows:
            for key in (
                "business_date",
                "period_end_date",
                "analytics_date",
                "order_date",
                "stat_date",
                "date",
            ):
                parsed = cls._coerce_business_date(row.get(key))
                if parsed is not None:
                    dates.append(parsed)
                    break
        if not dates:
            return None, None
        return min(dates), max(dates)

    @staticmethod
    def _first_non_empty(rows: list[dict[str, Any]], key: str) -> Any | None:
        for row in rows:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    def record_success(
        self,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
        identity_conflict_rows: int = 0,
        identity_unresolved_rows: int = 0,
        status: str = "completed",
    ) -> dict[str, Any]:
        payload = self._build_success_payload(
            source_table_name=source_table_name,
            receive_id=receive_id,
            source_file_id=source_file_id,
            platform_code=platform_code,
            data_domain=data_domain,
            granularity=granularity,
            checkpoint_scope=checkpoint_scope,
            source_latest_ingest_timestamp=source_latest_ingest_timestamp,
            written_rows=written_rows,
            rows=rows,
            identity_conflict_rows=identity_conflict_rows,
            identity_unresolved_rows=identity_unresolved_rows,
            status=status,
        )
        with self.engine.begin() as conn:
            conn.execute(insert(CloudSyncReceiveLog.__table__).values(**payload))
        return {
            "status": payload["status"],
            "receive_id": payload["receive_id"],
            "written_rows": written_rows,
            "identity_conflict_rows": identity_conflict_rows,
            "identity_unresolved_rows": identity_unresolved_rows,
        }

    def record_success_on_connection(
        self,
        conn,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
        identity_conflict_rows: int = 0,
        identity_unresolved_rows: int = 0,
        status: str = "completed",
    ) -> dict[str, Any]:
        payload = self._build_success_payload(
            source_table_name=source_table_name,
            receive_id=receive_id,
            source_file_id=source_file_id,
            platform_code=platform_code,
            data_domain=data_domain,
            granularity=granularity,
            checkpoint_scope=checkpoint_scope,
            source_latest_ingest_timestamp=source_latest_ingest_timestamp,
            written_rows=written_rows,
            rows=rows,
            identity_conflict_rows=identity_conflict_rows,
            identity_unresolved_rows=identity_unresolved_rows,
            status=status,
        )
        conn.execute(insert(CloudSyncReceiveLog.__table__).values(**payload))
        return {
            "status": payload["status"],
            "receive_id": payload["receive_id"],
            "written_rows": written_rows,
            "identity_conflict_rows": identity_conflict_rows,
            "identity_unresolved_rows": identity_unresolved_rows,
        }

    def _build_success_payload(
        self,
        *,
        source_table_name: str,
        receive_id: str | None = None,
        source_file_id: int | None = None,
        platform_code: str | None = None,
        data_domain: str | None = None,
        granularity: str | None = None,
        checkpoint_scope: str = "b_class",
        source_latest_ingest_timestamp: Any | None = None,
        written_rows: int = 0,
        rows: list[dict[str, Any]] | None = None,
        identity_conflict_rows: int = 0,
        identity_unresolved_rows: int = 0,
        status: str = "completed",
    ) -> dict[str, Any]:
        rows = list(rows or [])
        business_date_min, business_date_max = self._business_date_range(rows)
        receive_id = receive_id or f"receive-{uuid.uuid4().hex}"
        return {
            "receive_id": receive_id,
            "source_environment": self.source_environment,
            "checkpoint_scope": checkpoint_scope,
            "source_table_name": source_table_name,
            "source_file_id": (
                source_file_id
                if source_file_id is not None
                else self._first_non_empty(rows, "file_id")
            ),
            "platform_code": platform_code
            or self._first_non_empty(rows, "platform_code"),
            "data_domain": data_domain or self._first_non_empty(rows, "data_domain"),
            "granularity": granularity or self._first_non_empty(rows, "granularity"),
            "business_date_min": business_date_min,
            "business_date_max": business_date_max,
            "source_latest_ingest_timestamp": source_latest_ingest_timestamp,
            # ⚠️ ``written_rows`` = **真正写进云端**的行数。
            # 2026-11-07 事故里这里记的是"送进去"的行数, 于是账本写 72 行、
            # 实际落库 0 行, 看上去一切正常。绝不能再回退成"送进去的行数"。
            "written_rows": written_rows,
            "identity_conflict_rows": identity_conflict_rows,
            "identity_unresolved_rows": identity_unresolved_rows,
            "status": status,
        }


class CloudRefreshQueueEnqueuer:
    """Write post-sync refresh intents into the target database refresh queue."""

    PIPELINE_NAME = "data_ingested_refresh"
    TRIGGER_TYPE = "cloud_sync"

    def __init__(self, engine):
        self.engine = engine

    def enqueue_after_sync(
        self,
        *,
        source_table_name: str,
        data_domain: str,
        written_rows: int,
        checkpoint_scope: str,
        source_latest_ingest_timestamp: Any | None = None,
    ) -> dict[str, Any]:
        from backend.services.event_listeners import (
            determine_pipeline_targets_for_data_ingested,
        )
        from backend.utils.events import DataIngestedEvent

        event = DataIngestedEvent(
            file_id=None,
            platform_code=None,
            data_domain=data_domain,
            sub_domain=None,
            granularity=None,
            source_table_name=source_table_name,
            row_count=written_rows,
        )
        targets = determine_pipeline_targets_for_data_ingested(event)
        if not targets:
            return {"status": "not_required", "targets": []}

        context = {
            "source_table_name": source_table_name,
            "data_domain": data_domain,
            "written_rows": written_rows,
            "checkpoint_scope": checkpoint_scope,
            "trigger_source": self.TRIGGER_TYPE,
            "related_table_names": [source_table_name],
        }
        if source_latest_ingest_timestamp is not None:
            context["source_latest_ingest_timestamp"] = str(
                source_latest_ingest_timestamp
            )
        dedupe_key = RefreshQueueService.build_dedupe_key(self.PIPELINE_NAME, targets)
        table = RefreshQueueTask.__table__
        # 业务域分道（2026-11-11）：这条路径**直接写表**入队（不走服务层），
        # 所以域必须在这里算出来写进去 ——
        # 漏了的话，所有云同步任务都会落进 default 共享道（= 串行），
        # 而云同步恰恰是生产上失败最多的一条触发路径（262 次 / 30% 失败）。
        lane = resolve_refresh_lane(context)

        with self.engine.begin() as conn:
            existing = (
                conn.execute(
                    select(table.c.id, table.c.job_id, table.c.context_json)
                    .where(
                        table.c.dedupe_key == dedupe_key, table.c.status == "pending"
                    )
                    .order_by(table.c.id.asc())
                    .limit(1)
                )
                .mappings()
                .first()
            )

            if existing is not None:
                merged_context = RefreshQueueService._merge_context(
                    dict(existing.get("context_json") or {}),
                    context,
                )
                conn.execute(
                    update(table)
                    .where(table.c.id == existing["id"])
                    .values(context_json=merged_context, domain=lane)
                )
                return {
                    "status": "queued",
                    "job_id": existing["job_id"],
                    "targets": sorted(set(targets)),
                    "coalesced": True,
                }

            job_id = f"refresh-{uuid.uuid4().hex}"
            conn.execute(
                insert(table).values(
                    job_id=job_id,
                    trigger_type=self.TRIGGER_TYPE,
                    pipeline_name=self.PIPELINE_NAME,
                    dedupe_key=dedupe_key,
                    targets_json=sorted(
                        str(target).strip() for target in targets if str(target).strip()
                    ),
                    context_json=context,
                    status="pending",
                    attempt_count=0,
                    domain=lane,
                )
            )
            return {
                "status": "queued",
                "job_id": job_id,
                "targets": sorted(set(targets)),
                "coalesced": False,
            }


class CloudBClassSyncService:
    """Checkpointed local-to-cloud B-class sync orchestration."""

    def __init__(
        self,
        checkpoint_service,
        mirror_manager,
        source_batch_reader,
        remote_writer,
        table_inspector=None,
        run_recorder=None,
        sync_table_handler=None,
        local_engine=None,
        cloud_engine=None,
        owns_engines: bool = False,
        checkpoint_scope: str = "b_class",
        projection_enqueuer=None,
        receive_log_recorder=None,
    ) -> None:
        self.checkpoint_service = checkpoint_service
        self.mirror_manager = mirror_manager
        self.source_batch_reader = source_batch_reader
        self.remote_writer = remote_writer
        self.table_inspector = table_inspector
        self.run_recorder = run_recorder
        self.sync_table_handler = sync_table_handler
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.owns_engines = owns_engines
        self.checkpoint_scope = checkpoint_scope
        self.projection_enqueuer = projection_enqueuer
        self.receive_log_recorder = receive_log_recorder
        if self.projection_enqueuer is None and cloud_engine is not None:
            self.projection_enqueuer = CloudRefreshQueueEnqueuer(cloud_engine)
        if self.receive_log_recorder is None and cloud_engine is not None:
            self.receive_log_recorder = CloudSyncReceiveLogRecorder(cloud_engine)

    @staticmethod
    def _should_advance_checkpoint(
        write_succeeded: bool, dry_run: bool = False
    ) -> bool:
        return bool(write_succeeded) and not dry_run

    @staticmethod
    def _filter_b_class_tables(table_names: Iterable[str]) -> list[str]:
        filtered: list[str] = []
        for table_name in table_names:
            if "." in table_name:
                continue
            if table_name.startswith("fact_test_"):
                continue
            if table_name.startswith("fact_"):
                filtered.append(table_name)
        return filtered

    @staticmethod
    def _build_checkpoint_where_clause(checkpoint) -> tuple[str, dict[str, Any]]:
        if not checkpoint or not checkpoint.last_ingest_timestamp:
            return "", {}

        where_sql = (
            "(ingest_timestamp > :last_ingest_timestamp "
            "OR (ingest_timestamp = :last_ingest_timestamp AND id > :last_source_id))"
        )
        return where_sql, {
            "last_ingest_timestamp": checkpoint.last_ingest_timestamp,
            "last_source_id": checkpoint.last_source_id or 0,
        }

    @staticmethod
    def _infer_data_domain(table_name: str) -> str:
        validate_b_class_table_name(table_name)
        parts = table_name.split("_")
        if len(parts) < 4 or parts[0] != "fact":
            raise ValueError(f"Unsupported B-class table name: {table_name}")
        return parts[2]

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def _maybe_notify_conflict_ledger(
        self,
        write_result: Any,
        *,
        table_name: str,
    ) -> None:
        """矛盾行台账新增了行 ⇒ 走**通知出口**(批次 4.3, 默认关)。

        ⚠️ 通知**绝不**影响同步成败 —— 任何异常都吞掉。
        ⚠️ 开关是环境变量 :envvar:`SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`,
        **默认关** ⇒ 上线后行为与本批次之前完全一致。
        """
        if not isinstance(write_result, dict):
            return
        summary = write_result.get("conflict_ledger")
        if not isinstance(summary, dict):
            return
        if int(summary.get("new_rows") or 0) <= 0:
            return
        try:
            await notify_new_conflict_rows(summary)
        except Exception as exc:  # noqa: BLE001 —— 通知失败不能拖垮同步
            logger.warning(
                "[CloudSync] [%s] 矛盾行通知失败(不影响同步): %s", table_name, exc
            )

    async def sync_all_tables(self, batch_size: int = 1000) -> dict[str, Any]:
        if self.table_inspector is None:
            return {
                "status": "completed",
                "total_tables": 0,
                "succeeded_tables": 0,
                "failed_tables": 0,
                "results": [],
            }

        inspected = await self._maybe_await(self.table_inspector())
        tables = self._filter_b_class_tables(inspected)
        run_id = None
        if self.run_recorder is not None:
            run_id = self.run_recorder.create_run(total_tables=len(tables))

        results = []
        succeeded = 0
        partial = 0
        failed = 0
        for table_name in tables:
            if self.sync_table_handler is not None:
                result = await self._maybe_await(
                    self.sync_table_handler(table_name, batch_size=batch_size)
                )
            else:
                result = await self.sync_table(table_name, batch_size=batch_size)
            results.append(result)
            table_status = result.get("status")
            if table_status == "completed":
                succeeded += 1
            elif table_status == "partial_success":
                # 部分成功(有行因身份矛盾没落库)—— 不是失败, 但也不是全好
                partial += 1
            else:
                failed += 1

        summary = {
            "status": (
                "completed" if (failed == 0 and partial == 0) else "partial_success"
            ),
            "total_tables": len(tables),
            "succeeded_tables": succeeded,
            "partial_tables": partial,
            "failed_tables": failed,
            "results": results,
        }
        if run_id is not None:
            self.run_recorder.finish_run(
                run_id=run_id,
                status=summary["status"],
                succeeded_tables=succeeded,
                failed_tables=failed + partial,
                error_summary=(
                    None
                    if failed == 0 and partial == 0
                    else f"{failed} tables failed, {partial} tables partially succeeded"
                ),
            )
            summary["run_id"] = run_id
        return summary

    def list_b_class_tables(self) -> list[str]:
        if self.table_inspector is None:
            return []
        inspected = self.table_inspector()
        if inspect.isawaitable(inspected):
            raise RuntimeError(
                "Async table inspector is not supported in synchronous list_b_class_tables"
            )
        return self._filter_b_class_tables(inspected)

    async def sync_table(
        self, table_name: str, batch_size: int = 1000
    ) -> dict[str, Any]:
        try:
            validate_b_class_table_name(table_name)
            checkpoint = self.checkpoint_service.create_or_get_checkpoint(
                table_name,
                table_schema=self.checkpoint_scope,
            )
            data_domain = self._infer_data_domain(table_name)
            self.mirror_manager.ensure_cloud_mirror_table(table_name, data_domain)
            total_written_rows = 0
            total_conflict_rows = 0
            total_unresolved_rows = 0
            total_degraded_rows = 0
            dry_run_seen = False
            latest_ingest_timestamp = None

            def _projection_result() -> dict[str, Any]:
                if total_written_rows <= 0 or dry_run_seen:
                    return {"projection_status": "not_required"}
                if self.projection_enqueuer is None:
                    return {"projection_status": "not_required"}
                try:
                    enqueue_result = self.projection_enqueuer.enqueue_after_sync(
                        source_table_name=table_name,
                        data_domain=data_domain,
                        written_rows=total_written_rows,
                        checkpoint_scope=self.checkpoint_scope,
                        source_latest_ingest_timestamp=latest_ingest_timestamp,
                    )
                except Exception as exc:  # noqa: BLE001
                    return {
                        "projection_status": "failed",
                        "projection_error": str(exc),
                        "error_code": "projection_runtime_failure",
                    }

                status = enqueue_result.get("status", "not_required")
                payload = {
                    "projection_status": status,
                    "refresh_queue_job_id": enqueue_result.get("job_id"),
                    "refresh_targets": enqueue_result.get("targets", []),
                }
                if status == "not_required":
                    payload["projection_status"] = "not_required"
                return payload

            while True:
                rows = await self._maybe_await(
                    self.source_batch_reader(
                        table_name=table_name,
                        checkpoint=checkpoint,
                        batch_size=batch_size,
                    )
                )
                rows = list(rows)
                payload_rows = [build_sync_payload(row) for row in rows]

                if not rows:
                    return {
                        "status": _sync_batch_status(
                            total_conflict_rows, total_degraded_rows
                        ),
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "identity_conflict_rows": total_conflict_rows,
                        "identity_unresolved_rows": total_unresolved_rows,
                        "identity_registry_mismatch_rows": total_degraded_rows,
                        "error_code": _sync_identity_error_code(
                            total_conflict_rows, total_degraded_rows
                        ),
                        **_projection_result(),
                    }

                receive_id = f"receive-{uuid.uuid4().hex}"
                source_file_id = CloudSyncReceiveLogRecorder._first_non_empty(
                    rows, "file_id"
                )
                for payload_row in payload_rows:
                    raw_payload = payload_row.get("raw_data")
                    if not isinstance(raw_payload, dict):
                        raw_payload = {}
                    raw_payload["_cloud_sync_receive_id"] = receive_id
                    if source_file_id is not None:
                        raw_payload.setdefault(
                            "_cloud_sync_source_file_id", source_file_id
                        )
                    payload_row["raw_data"] = raw_payload

                receive_log_context = {
                    "source_table_name": table_name,
                    "receive_id": receive_id,
                    "source_file_id": source_file_id,
                    "data_domain": data_domain,
                    "granularity": (
                        (payload_rows[0] or {}).get("granularity")
                        if payload_rows
                        else None
                    ),
                    "platform_code": (
                        (payload_rows[0] or {}).get("platform_code")
                        if payload_rows
                        else None
                    ),
                    "checkpoint_scope": self.checkpoint_scope,
                    "source_latest_ingest_timestamp": (
                        rows[-1].get("ingest_timestamp") if rows else None
                    ),
                    "written_rows": len(rows),
                    "rows": rows,
                }
                if self.receive_log_recorder is not None and hasattr(
                    self.remote_writer, "write_rows_with_receive_log"
                ):
                    write_result = await self._maybe_await(
                        self.remote_writer.write_rows_with_receive_log(
                            table_name=table_name,
                            rows=payload_rows,
                            data_domain=data_domain,
                            receive_log_recorder=self.receive_log_recorder,
                            receive_log_context=receive_log_context,
                        )
                    )
                else:
                    write_result = await self._maybe_await(
                        self.remote_writer(
                            table_name=table_name,
                            rows=payload_rows,
                            data_domain=data_domain,
                        )
                    )

                # ⚠️ 通知在**写入之后**发 —— 通知失败绝不影响同步成败,
                # 且**默认关**(环境变量开关)。
                await self._maybe_notify_conflict_ledger(
                    write_result, table_name=table_name
                )

                write_succeeded = bool(write_result.get("success"))
                if not write_succeeded:
                    return {
                        "status": "failed",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "identity_conflict_rows": total_conflict_rows,
                        "identity_unresolved_rows": total_unresolved_rows,
                        "identity_registry_mismatch_rows": total_degraded_rows,
                        "error": write_result.get("error")
                        or write_result.get("detail")
                        or "sync_failed",
                        "error_code": write_result.get("error_code") or "sync_failed",
                    }

                batch_written_rows = int(write_result.get("written_rows", len(rows)))
                batch_conflict_rows = int(write_result.get("identity_conflict_rows", 0))
                batch_unresolved_rows = int(
                    write_result.get("identity_unresolved_rows", 0)
                )
                batch_degraded_rows = int(
                    write_result.get("identity_registry_mismatch_rows", 0)
                )
                total_written_rows += batch_written_rows
                total_conflict_rows += batch_conflict_rows
                total_unresolved_rows += batch_unresolved_rows
                total_degraded_rows += batch_degraded_rows

                if (
                    self.receive_log_recorder is not None
                    and not bool(write_result.get("dry_run"))
                    and not write_result.get("receive_log")
                ):
                    # 账本必须记**真正落库**的行数, 不能记"送进去"的行数。
                    fallback_context = dict(receive_log_context)
                    fallback_context["written_rows"] = batch_written_rows
                    fallback_context["identity_conflict_rows"] = batch_conflict_rows
                    fallback_context["identity_unresolved_rows"] = batch_unresolved_rows
                    fallback_context["status"] = _sync_batch_status(
                        batch_conflict_rows, batch_degraded_rows
                    )
                    await self._maybe_await(
                        self.receive_log_recorder.record_success(**fallback_context)
                    )
                dry_run_seen = dry_run_seen or bool(write_result.get("dry_run"))

                if not self._should_advance_checkpoint(
                    write_succeeded, dry_run=bool(write_result.get("dry_run"))
                ):
                    # dry_run: 不推进检查点, 本表到此结束
                    return {
                        "status": "completed",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "identity_conflict_rows": total_conflict_rows,
                        "identity_unresolved_rows": total_unresolved_rows,
                        **_projection_result(),
                    }

                # ⚠️ 检查点**只能**推进到最后一行**真正落库**的数据。
                # 推进到 ``rows[-1]`` 等于把"被判矛盾、根本没写进去"的行
                # 一并跳过 —— 那正是 2026-11-07 丢数的机制。
                last_written_index = write_result.get("last_written_index")
                if last_written_index is None:
                    # 兼容不认识新契约的自定义 writer: 保守假定本批全部落库
                    last_written_index = len(rows) - 1
                last_written_index = int(last_written_index)

                if last_written_index < 0:
                    # 本批**一行都没落库**(全部被判矛盾 / 全部被双基准降级)
                    # ⇒ 检查点不能推进, 停在当前水位并明确报告 ——
                    # 绝不能"跳过"这些行。
                    logger.error(
                        "[CloudSync] [%s] 本批 %d 行行内身份自相矛盾 / %d 行被双基准降级, "
                        "无一行落库; 检查点停在当前水位, 需人工确认归属后再同步",
                        table_name,
                        batch_conflict_rows,
                        batch_degraded_rows,
                    )
                    return {
                        "status": "partial_success",
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "identity_conflict_rows": total_conflict_rows,
                        "identity_unresolved_rows": total_unresolved_rows,
                        "identity_registry_mismatch_rows": total_degraded_rows,
                        "error": (
                            "%d 行行内身份自相矛盾 / %d 行被双基准降级, 本批无一落库; "
                            "检查点已停在当前水位, 需人工确认这些行的店铺归属"
                            % (batch_conflict_rows, batch_degraded_rows)
                        ),
                        "error_code": _sync_identity_error_code(
                            batch_conflict_rows, batch_degraded_rows
                        ),
                        **_projection_result(),
                    }

                last_row = rows[last_written_index]
                latest_ingest_timestamp = last_row["ingest_timestamp"]
                self.checkpoint_service.advance_checkpoint(
                    table_name=table_name,
                    ingest_timestamp=last_row["ingest_timestamp"],
                    source_id=last_row["id"],
                    status=_sync_batch_status(batch_conflict_rows, batch_degraded_rows),
                    table_schema=self.checkpoint_scope,
                )

                if len(rows) < batch_size:
                    return {
                        "status": _sync_batch_status(
                            total_conflict_rows, total_degraded_rows
                        ),
                        "table_name": table_name,
                        "written_rows": total_written_rows,
                        "identity_conflict_rows": total_conflict_rows,
                        "identity_unresolved_rows": total_unresolved_rows,
                        "identity_registry_mismatch_rows": total_degraded_rows,
                        "error_code": _sync_identity_error_code(
                            total_conflict_rows, total_degraded_rows
                        ),
                        **_projection_result(),
                    }
        except Exception as exc:
            self.checkpoint_service.mark_failure(
                table_name,
                str(exc),
                table_schema=self.checkpoint_scope,
            )
            return {
                "status": "failed",
                "table_name": table_name,
                "error": str(exc),
            }

    def close(self) -> None:
        db = getattr(self.checkpoint_service, "db", None)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if self.owns_engines:
            if self.local_engine is not None:
                try:
                    self.local_engine.dispose()
                except Exception:
                    pass
            if (
                self.cloud_engine is not None
                and self.cloud_engine is not self.local_engine
            ):
                try:
                    self.cloud_engine.dispose()
                except Exception:
                    pass
