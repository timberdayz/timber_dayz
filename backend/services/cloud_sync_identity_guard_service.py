"""同步侧「双基准守卫」—— 推送前把**本地登记信息**与**云端登记信息**比一次。

背景
----
同步侧推送前的身份判定(:func:`backend.services.cloud_b_class_sync_service.
split_rows_by_identity_consistency`)只看**本地**这一份登记信息
(``core.shop_accounts`` + ``core.shop_account_aliases``)。
它把行分成三类: 自洽 / 未归属 / 真矛盾(>1 个账号 ⇒ 不写云端)。

但**云端也有一份登记信息**。两边不同步时(采集机本地台账与云端台账不一致),
本地判「自洽」的行推到云端后, 云端会用**云端**的登记去解释它 ⇒ 可能指向别的店
⇒ 云端出现**归属塌陷**(语义层落 ``unknown``)。

⇒ 所以推送前要**再比一次**: 本地与云端对同一行的解释不一致 ⇒ 这一行
**不再当自洽行直接放行**, 而是降级成**可观测事件**(记下来 / 可查 / 可计数),
**不写云端**。

判定口径(为什么这么定)
----------------------
设 ``L`` = 本地台账把这一行解析出来的账号集合, ``C`` = 云端台账解析出来的账号集合。

* ``len(L) == 1`` 且 ``C == L`` ⇒ **两边一致** ⇒ 行为与改造前**完全相同**
  (自洽行照常放行);
* ``C`` 为空 ⇒ 本地认出的账号, 云端**认不出** ⇒ **不一致**;
* ``C`` 与 ``L`` 不同(且 ``len(C) == 1``) ⇒ 云端把它**指向另一个账号** ⇒ **不一致**;
* ``len(C) > 1`` ⇒ 云端自己都认不唯一 ⇒ **不一致**(推上去云端也是歧义)。

⚠️ **为什么用「两边各自的解析结果」比, 而不是逐字段比台账**
------------------------------------------------------------
台账比对(``platform_shop_id`` 逐条相等)只能发现「编号登记错了」,
发现不了「别名指错了」「本地停用店云端还在」这类差异。而本守卫要回答的是
**同一个问题**: *这一行推到云端后, 云端会把它算到谁头上?* ⇒ 直接问云端那一份
登记信息即可 —— 两边用**同一份解析实现**
(:func:`backend.services.shop_identity_reconciliation_service.row_identity_accounts`),
口径不会分叉。

⚠️ **口径方向: 与「账号章优先」一致**
------------------------------------
判定用的就是仓库唯一台账声明
(:mod:`modules.core.shop_identity_ssot`)派生出来的反查索引
(``shop_account_id`` > ``platform_shop_id`` > ``shop_id`` > ``store_name``),
与入库侧、语义层候选池**同源** ⇒ 守卫不会得出与语义层相反的结论。

云端不可达 ⇒ 优雅降级
---------------------
云端连不上(隧道没起 / 口令不对 / 云端还没建 ``core.shop_accounts``)时,
**退回本地单基准判定** —— 行为与改造前**一模一样**, 并记一条
「**双基准不可用**」的可观测事件。

⇒ **绝不能因为云端连不上就把同步搞挂。**

云端登记信息怎么读
----------------
* 连接串**只从环境变量读**(:envvar:`CLOUD_DATABASE_URL`); 源码里**没有任何
  连接串字面量**;
* 解析用 :func:`sqlalchemy.engine.make_url` —— 它会**自动解码百分号编码的口令**
  (``p%40ss`` → ``p@ss``)。**不要**用 ``urlparse`` 读口令: 它不解码,
  拿到的仍是编码串, 脱敏会漏;
* 连接**只读**、**短命**: 建引擎 → 查两张表 → ``finally`` 里 ``dispose()``;
* ⚠️ **不做主机名重写**: 采集机的云端同步 worker 跑在**宿主进程**
  (``scripts\\start_collection_formal.ps1``), 那里 ``127.0.0.1`` 就是宿主自己 ⇒
  重写成 ``host.docker.internal`` 反而连不上。现有同步链路
  (``backend/services/cloud_b_class_auto_sync_factory.py``)也是原样使用
  ``CLOUD_DATABASE_URL`` ⇒ 本模块与它保持一致。

⚠️ **别名表的 FK 是整数主键**
-----------------------------
``core.shop_account_aliases.shop_account_id`` 是 **integer FK →**
``core.shop_accounts.id``(不是字符串账号编码)。⇒ JOIN 必须写成
``ON a.shop_account_id = s.id``; 反查索引构建时也按**主键**认领别名。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from backend.services.shop_identity_conflict_ledger_service import (
    REASON_CLOUD_AMBIGUOUS as _REASON_CLOUD_AMBIGUOUS,
)
from backend.services.shop_identity_conflict_ledger_service import (
    REASON_CLOUD_DIFFERENT_ACCOUNT as _REASON_CLOUD_DIFFERENT_ACCOUNT,
)
from backend.services.shop_identity_conflict_ledger_service import (
    REASON_CLOUD_UNRESOLVED as _REASON_CLOUD_UNRESOLVED,
)
from backend.services.shop_identity_conflict_ledger_service import (
    extract_business_date,
)
from backend.services.shop_identity_reconciliation_service import (
    IdentityIndex,
    build_identity_index,
    row_identity_accounts,
    row_identity_tokens,
)
from modules.core.logger import get_logger


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 云端登记信息的**加载**状态。
LOAD_STATUS_LOADED = "loaded"
LOAD_STATUS_UNAVAILABLE = "unavailable"
#: 守卫被**人工关掉**(环境变量止血开关)。
LOAD_STATUS_DISABLED = "disabled"

#: 双基准守卫的**开关**(可用环境变量关掉, 便于线上快速止血)。
#:
#: 默认**开**。关掉后行为与本批次上线前**完全一致**(只是多跑一次诊断)。
#:
#: ⚠️ 为什么要留这个开关: 守卫会把「本地/云端台账不一致」的行**扣在本地**
#: (不写云端)。万一它在生产上误判, 需要一个**不用改代码、不用重新部署**的
#: 止血手段 —— 与入库侧收敛开关
#: (:data:`backend.services.shop_identity_reconciliation_service.
#: RECONCILIATION_ENABLED`)同一套做法。
GUARD_ENABLED_ENV = "SHOP_IDENTITY_DUAL_BASELINE_GUARD_ENABLED"

_DISABLED_VALUES = frozenset({"0", "false", "off", "no"})

#: 双基准判定的**结果**状态。
DUAL_BASELINE_NOT_APPLIED = "not_applied"
DUAL_BASELINE_CONSISTENT = "consistent"
DUAL_BASELINE_MISMATCH = "mismatch"
DUAL_BASELINE_UNAVAILABLE = "unavailable"

#: 降级原因码(机器可读, 便于按原因分组统计)。
#:
#: ⚠️ **唯一定义处在** ``shop_identity_conflict_ledger_service``
#: (批次 4.3 的矛盾行台账)—— 这里只做**转出**, 别再写第二份。
#: 之所以住在台账那边: 批次 4.3 要用**同一套**原因码给台账行分类,
#: 而台账的去重口径同时也是「事件不重复写」的修复口径 ⇒ 两边必须同源。
REASON_CLOUD_UNRESOLVED = _REASON_CLOUD_UNRESOLVED
REASON_CLOUD_AMBIGUOUS = _REASON_CLOUD_AMBIGUOUS
REASON_CLOUD_DIFFERENT_ACCOUNT = _REASON_CLOUD_DIFFERENT_ACCOUNT

#: 台账里最多保留多少条事件**样本**。
#:
#: ⚠️ **计数是全量的**(``degraded_rows``), 样本是**截断**的 ——
#: 一批 5,000 行全降级时不该把 5,000 条事件全塞进 ``ops.pipeline_run_log``。
MAX_EVENT_SAMPLES = 50

#: 可观测事件台账的 pipeline 名(计数时按它过滤)。
GUARD_PIPELINE_NAME = "cloud_sync_identity_guard"

#: 触发源(写进 ``ops.pipeline_run_log.trigger_source``)。
GUARD_TRIGGER_SOURCE = "cloud_sync"

_CLOUD_REGISTRY_SQL = """
SELECT s.id AS account_pk,
       s.shop_account_id AS shop_account_id,
       s.platform AS platform,
       s.platform_shop_id AS platform_shop_id,
       s.store_name AS store_name,
       s.shop_region AS shop_region,
       s.enabled AS enabled,
       s.business_role AS business_role,
       a.id AS alias_pk,
       a.shop_account_id AS alias_owner_pk,
       a.alias_value AS alias_value,
       a.alias_normalized AS alias_normalized,
       a.is_active AS is_active
FROM core.shop_accounts s
LEFT JOIN core.shop_account_aliases a ON a.shop_account_id = s.id
WHERE s.enabled IS TRUE
  AND s.business_role = 'operating_store'
"""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CloudIdentityRegistry:
    """云端登记信息的一次快照(只读)。"""

    #: ``loaded`` / ``unavailable`` / ``disabled``
    status: str = LOAD_STATUS_UNAVAILABLE
    #: 不可用原因(**脱敏**, 不含口令)
    reason: str = ""
    #: 脱敏后的云端目标(``驱动://主机:端口/库名``), 绝不含口令
    target: str = ""
    #: 反查索引(与本地那份同构)
    index: IdentityIndex | None = None
    #: 读到的账号数 / 别名数
    account_count: int = 0
    alias_count: int = 0

    @property
    def available(self) -> bool:
        """云端登记信息是否**成功读到**。"""
        return self.status == LOAD_STATUS_LOADED and self.index is not None

    def to_summary(self) -> dict[str, Any]:
        """给事件台账用的**脱敏**摘要。"""
        return {
            "status": self.status,
            "reason": self.reason,
            "target": self.target,
            "account_count": self.account_count,
            "alias_count": self.alias_count,
        }


@dataclass(frozen=True)
class RegistryMismatchEvent:
    """一行被「双基准不一致」降级时的**事件负载**。

    ⚠️ 这里**不放行体**(``raw_data`` 可能很大), 只放**定位它所需的最小信息**:
    行下标 + 源行主键 + 身份 token + 两边的账号集合。
    """

    #: 原因码(见 ``REASON_*``)
    reason: str
    #: 本地解析出的账号
    local_accounts: tuple[str, ...]
    #: 云端解析出的账号
    cloud_accounts: tuple[str, ...]
    #: 平台码
    platform_code: str
    #: 该行在**入参列表**中的下标
    row_index: int
    #: 行内身份 token(归一化后)
    identity_tokens: dict[str, str] = field(default_factory=dict)
    #: 源行主键(``b_class.fact_*.id``)
    source_row_id: Any = None
    #: 冲突键的一部分, 便于人工定位
    data_hash: str = ""
    #: 业务日期(便于人工定位)
    business_date: str = ""

    def to_payload(self) -> dict[str, Any]:
        """转成可 JSON 序列化的事件负载。"""
        return {
            "reason": self.reason,
            "local_accounts": list(self.local_accounts),
            "cloud_accounts": list(self.cloud_accounts),
            "platform_code": self.platform_code,
            "row_index": self.row_index,
            "identity_tokens": dict(self.identity_tokens),
            "source_row_id": self.source_row_id,
            "data_hash": self.data_hash,
            "business_date": self.business_date,
        }


# ---------------------------------------------------------------------------
# 连接串处理(脱敏)
# ---------------------------------------------------------------------------


def _masked_target(parsed: URL) -> str:
    """把连接串压成**脱敏**目标串(只留驱动/主机/端口/库名)。

    ⚠️ 绝不能带口令 —— 事件台账与日志都会被运维看到。
    """
    driver = parsed.drivername.split("+", 1)[0]
    return "%s://%s:%s/%s" % (
        driver,
        parsed.host or "",
        parsed.port or 5432,
        parsed.database or "",
    )


def _redact(text: str, raw_url: str) -> str:
    """把异常消息里可能出现的口令**抹掉**。

    ⚠️ 驱动异常常把整条 DSN 带进消息 ⇒ 直接写进日志/台账等于泄密。
    编码形式与解码形式都要抹(``p%40ss`` 与 ``p@ss``)。
    """
    secrets: set[str] = set()
    try:
        decoded = make_url(raw_url).password
        if decoded:
            secrets.add(decoded)
    except Exception:  # pragma: no cover - 畸形连接串
        pass
    # ⚠️ 口令里可能带**未编码的 ``@``**(形如 ``<scheme>://u:p@ss@host/db``) ⇒
    #    ``make_url`` 只取到第一个 ``@`` 之前的那一段 ⇒ 必须再按**最后一个**
    #    ``@`` 切一次 netloc, 把**完整**口令收进来。
    userinfo = raw_url.split("://", 1)[-1].rsplit("@", 1)[0]
    if ":" in userinfo:
        secrets.add(userinfo.split(":", 1)[1])
    # ⚠️ **长的先抹** —— 否则短口令会把长口令的前缀抹掉, 剩下尾巴露出来
    #    (``p@ss`` 被当成 ``p`` 抹掉 ⇒ 变成 ``***@ss``)。
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, "***")
    return text


# ---------------------------------------------------------------------------
# 读取云端登记信息
# ---------------------------------------------------------------------------


def _split_registry_rows(
    records: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把 JOIN 出来的扁平行拆成「账号行」与「别名行」。

    ⚠️ ``LEFT JOIN`` 会让**一个账号出现多次**(每个别名一行), 且没有别名的账号
    也会出现一次(别名列全 NULL) ⇒ 这里按账号主键去重。

    ⚠️ 别名行的 ``shop_account_id`` 必须是 **``core.shop_accounts.id``(整数主键)**,
    不是字符串账号编码 —— 反查索引构建时按主键认领别名。
    """
    accounts: dict[Any, dict[str, Any]] = {}
    aliases: list[dict[str, Any]] = []

    for record in records:
        account_pk = record.get("account_pk")
        if account_pk is not None and account_pk not in accounts:
            accounts[account_pk] = {
                "id": account_pk,
                "shop_account_id": record.get("shop_account_id"),
                "platform": record.get("platform"),
                "platform_shop_id": record.get("platform_shop_id"),
                "store_name": record.get("store_name"),
                "shop_region": record.get("shop_region"),
                "enabled": record.get("enabled"),
                "business_role": record.get("business_role"),
            }
        alias_owner_pk = record.get("alias_owner_pk")
        if alias_owner_pk is None:
            continue
        aliases.append(
            {
                "id": record.get("alias_pk"),
                "shop_account_id": alias_owner_pk,
                "alias_value": record.get("alias_value"),
                "alias_normalized": record.get("alias_normalized"),
                "is_active": record.get("is_active"),
            }
        )

    return list(accounts.values()), aliases


def guard_enabled() -> bool:
    """双基准守卫是否**启用**(环境变量止血开关)。

    ``SHOP_IDENTITY_DUAL_BASELINE_GUARD_ENABLED`` 只有**显式**为假时才关掉。
    """
    raw = os.getenv(GUARD_ENABLED_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in _DISABLED_VALUES


def load_cloud_identity_registry(
    database_url: str | None = None,
) -> CloudIdentityRegistry:
    """**只读**地读云端登记信息, 建反查索引。

    连接串只从环境变量 :envvar:`CLOUD_DATABASE_URL` 读(本参数只为测试/脚本
    留一个显式入口); 源码里**没有任何连接串字面量**。

    连接生命周期: 建引擎 → 查两张表 → **``finally`` 里 ``dispose()``**,
    任何异常路径都不会漏连接。

    Returns:
        :class:`CloudIdentityRegistry` —— 读不到时 ``status`` 是 ``unavailable``,
        ``reason`` 说明原因(脱敏); 守卫被关掉时 ``status`` 是 ``disabled``。
    """
    if not guard_enabled():
        return CloudIdentityRegistry(
            status=LOAD_STATUS_DISABLED,
            reason="guard_disabled_by_env",
        )

    raw_url = (
        database_url
        if database_url is not None
        else (os.getenv("CLOUD_DATABASE_URL") or "")
    ).strip()
    if not raw_url:
        return CloudIdentityRegistry(
            status=LOAD_STATUS_UNAVAILABLE,
            reason="missing_cloud_database_url",
        )

    try:
        parsed = make_url(raw_url)
    except Exception as exc:  # pragma: no cover - 畸形连接串
        return CloudIdentityRegistry(
            status=LOAD_STATUS_UNAVAILABLE,
            reason="unparsable_cloud_database_url:%s" % type(exc).__name__,
        )

    target = _masked_target(parsed)
    engine = None
    try:
        engine = create_engine(raw_url)
        with engine.connect() as conn:
            result = conn.execute(text(_CLOUD_REGISTRY_SQL))
            records = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        reason = _redact(str(exc), raw_url)
        logger.warning(
            "[CloudSyncGuard] 云端登记信息读取失败(%s), 双基准降级为本地单基准: %s",
            target,
            reason,
        )
        return CloudIdentityRegistry(
            status=LOAD_STATUS_UNAVAILABLE,
            reason="cloud_registry_unreadable:%s" % reason,
            target=target,
        )
    finally:
        if engine is not None:
            engine.dispose()

    # ⚠️ **拆行与建索引也必须吞掉异常** —— 守卫的契约是「云端这一侧读不了 / 建不了索引
    #    就退回本地单基准」, **绝不**因为云端的问题把整个同步任务打挂。
    #    (这两步原本在 try 之外 ⇒ 异常会一路冒到 worker ⇒ 整批数据不落云端。)
    try:
        accounts, aliases = _split_registry_rows(records)
        index = build_identity_index(accounts, aliases)
    except Exception as exc:  # noqa: BLE001 - 云端侧的异常绝不能打挂同步
        logger.warning(
            "[CloudSyncGuard] 云端登记信息建索引失败(%s), 双基准降级为本地单基准: %s",
            target,
            type(exc).__name__,
        )
        return CloudIdentityRegistry(
            status=LOAD_STATUS_UNAVAILABLE,
            reason="cloud_registry_index_build_failed:%s" % type(exc).__name__,
            target=target,
        )
    logger.info(
        "[CloudSyncGuard] 云端登记信息已读取: %s (账号 %d / 别名 %d)",
        target,
        len(accounts),
        len(aliases),
    )
    return CloudIdentityRegistry(
        status=LOAD_STATUS_LOADED,
        target=target,
        index=index,
        account_count=len(accounts),
        alias_count=len(aliases),
    )


# ---------------------------------------------------------------------------
# 跨端比较
# ---------------------------------------------------------------------------


def classify_registry_agreement(
    local_accounts: Iterable[str],
    cloud_accounts: Iterable[str],
) -> str | None:
    """比较两边对同一行的解释, 返回**不一致原因码**; 一致时返回 ``None``。

    ⚠️ 前提: ``local_accounts`` 恰好 **1** 个(本地判「自洽」的行)。
    本地认不出账号的行(未归属)**不做跨端比较** —— 没有「本地认出的账号」,
    也就没有可比对的基准, 行为保持不变(照常落库 + 计数 + 告警)。
    """
    local = set(local_accounts)
    cloud = set(cloud_accounts)

    if not cloud:
        # 本地认出的账号, 云端认不出。
        return REASON_CLOUD_UNRESOLVED
    if len(cloud) > 1:
        # 云端自己都认不唯一 ⇒ 推上去也是歧义(语义层会落 unknown)。
        return REASON_CLOUD_AMBIGUOUS
    if cloud != local:
        # 云端把它指向了**另一个**账号。
        return REASON_CLOUD_DIFFERENT_ACCOUNT
    return None


def build_registry_mismatch_event(
    row: Mapping[str, Any],
    *,
    row_index: int,
    local_accounts: Iterable[str],
    cloud_accounts: Iterable[str],
    reason: str,
    platform_code: str,
) -> RegistryMismatchEvent:
    """构造一条降级事件(只放定位信息, 不放行体)。"""
    business_date = extract_business_date(row)
    return RegistryMismatchEvent(
        reason=reason,
        local_accounts=tuple(sorted(local_accounts)),
        cloud_accounts=tuple(sorted(cloud_accounts)),
        platform_code=platform_code,
        row_index=row_index,
        identity_tokens=row_identity_tokens(row),
        source_row_id=row.get("id"),
        data_hash=str(row.get("data_hash") or ""),
        business_date=business_date,
    )


def collect_registry_mismatch_events(
    rows: list[dict[str, Any]],
    *,
    consistent_indexes: Iterable[int],
    local_index: IdentityIndex | None,
    cloud_index: IdentityIndex,
) -> list[RegistryMismatchEvent]:
    """把「本地自洽、云端不自洽/指向别处」的行挑出来, 各自生成一条事件。

    Args:
        rows: 本批待同步的行。
        consistent_indexes: 本地判「自洽」的行在 ``rows`` 中的下标。
        local_index: 本地反查索引(None ⇒ 本地没台账, 无从比较)。
        cloud_index: 云端反查索引。
    """
    events: list[RegistryMismatchEvent] = []
    if local_index is None:
        return events

    for row_index in consistent_indexes:
        row = rows[row_index]
        platform_code = str(row.get("platform_code") or "")
        local_accounts = row_identity_accounts(row, local_index, platform_code)
        if len(local_accounts) != 1:
            # 本地没唯一认出来(未归属)⇒ 没有可比对的基准, 行为不变。
            continue
        cloud_accounts = row_identity_accounts(row, cloud_index, platform_code)
        reason = classify_registry_agreement(local_accounts, cloud_accounts)
        if reason is None:
            continue
        events.append(
            build_registry_mismatch_event(
                row,
                row_index=row_index,
                local_accounts=local_accounts,
                cloud_accounts=cloud_accounts,
                reason=reason,
                platform_code=platform_code,
            )
        )
    return events


# ---------------------------------------------------------------------------
# 可观测事件落点
# ---------------------------------------------------------------------------


class CloudSyncIdentityGuardEventRecorder:
    """把双基准守卫的可观测事件写进**本地** ``ops.pipeline_run_log``。

    为什么落**本地**
    ----------------
    「云端不可达」这条事件在云端连不上时**根本写不到云端** ⇒ 落点必须
    在**采集机本地库**(同步 worker 本来就在那儿)。两边的事件落在同一个地方,
    计数口径才统一。

    为什么不新建表
    --------------
    ``ops.pipeline_run_log`` 已经有 ``context``(jsonb)这一列, 巡检
    (:mod:`backend.services.data_pipeline.cloud_sync_integrity_service`)
    与新鲜度巡检都在用它 ⇒ **不新增表、不加迁移链**。

    怎么计数
    --------
    .. code-block:: sql

        SELECT count(*) AS degraded_batches
        FROM ops.pipeline_run_log
        WHERE pipeline_name = 'cloud_sync_identity_guard'
          AND status = 'partial_failed';

        SELECT sum((context->>'degraded_rows')::int) AS degraded_rows
        FROM ops.pipeline_run_log
        WHERE pipeline_name = 'cloud_sync_identity_guard';

    ⚠️ **记录失败绝不能阻塞同步** ⇒ 本类内部吞掉所有异常, 只返回状态。
    """

    PIPELINE_NAME = GUARD_PIPELINE_NAME
    TRIGGER_SOURCE = GUARD_TRIGGER_SOURCE

    def __init__(self, engine):
        self.engine = engine

    def _insert(self, *, status: str, error_message: str, context: dict[str, Any]):
        if self.engine is None:
            return {"status": "skipped", "reason": "no_local_engine"}
        run_id = "cloud_sync_identity_guard_%s" % uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ops.pipeline_run_log (
                        run_id, pipeline_name, status, trigger_source,
                        started_at, completed_at, error_message, context
                    ) VALUES (
                        :run_id, :pipeline_name, :status, :trigger_source,
                        :started_at, :completed_at, :error_message,
                        CAST(:context AS jsonb)
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "pipeline_name": self.PIPELINE_NAME,
                    "status": status,
                    "trigger_source": self.TRIGGER_SOURCE,
                    "started_at": now,
                    "completed_at": now,
                    "error_message": error_message,
                    "context": json.dumps(context, ensure_ascii=False, default=str),
                },
            )
        return {"status": "recorded", "run_id": run_id}

    def record_mismatch(
        self,
        *,
        source_table_name: str,
        data_domain: str | None,
        events: Iterable[Mapping[str, Any]],
        registry: CloudIdentityRegistry | None = None,
        reason_summary: str = "",
    ) -> dict[str, Any]:
        """记一条「双基准不一致」事件。

        Args:
            events: 事件负载(``RegistryMismatchEvent.to_payload()`` 的产物)。
        """
        payload = [dict(event) for event in events]
        context: dict[str, Any] = {
            "dual_baseline_status": DUAL_BASELINE_MISMATCH,
            "source_table_name": source_table_name,
            "data_domain": data_domain,
            "degraded_rows": len(payload),
            "event_count": len(payload),
            "events": payload[:MAX_EVENT_SAMPLES],
            "events_truncated": len(payload) > MAX_EVENT_SAMPLES,
            "reason_summary": reason_summary,
        }
        if registry is not None:
            context["cloud_registry"] = registry.to_summary()
        message = "%s: %d 行因本地/云端登记信息不一致被降级(未写云端)" % (
            source_table_name,
            len(payload),
        )
        try:
            return self._insert(
                status="partial_failed",
                error_message=message,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001 - 记录失败绝不阻塞同步
            logger.warning(
                "[CloudSyncGuard] 双基准不一致事件写入失败(不影响同步): %s", exc
            )
            return {"status": "failed", "error": str(exc)}

    def record_unavailable(
        self,
        *,
        source_table_name: str,
        reason: str,
        registry: CloudIdentityRegistry | None = None,
    ) -> dict[str, Any]:
        """记一条「双基准不可用」事件(云端连不上 ⇒ 退回本地单基准)。"""
        context: dict[str, Any] = {
            "dual_baseline_status": DUAL_BASELINE_UNAVAILABLE,
            "source_table_name": source_table_name,
            "degraded_rows": 0,
            "event_count": 0,
            "events": [],
            "reason": reason,
            "fallback": "local_single_baseline",
        }
        if registry is not None:
            context["cloud_registry"] = registry.to_summary()
        message = "%s: 双基准不可用(%s), 已退回本地单基准判定" % (
            source_table_name,
            reason,
        )
        try:
            return self._insert(
                status="partial_failed",
                error_message=message,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001 - 记录失败绝不阻塞同步
            logger.warning(
                "[CloudSyncGuard] 双基准不可用事件写入失败(不影响同步): %s", exc
            )
            return {"status": "failed", "error": str(exc)}
