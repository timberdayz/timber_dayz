from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    LOGICAL_TARGET_OBJECTS,
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)
from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    execute_sql_file,
    extract_run_id,
)


logger = logging.getLogger(__name__)


# ── 积压资产组 ──────────────────────────────────────────────────────────
# ⚠️ `mart.inventory_backlog_base` 删列 → 必须 DROP 重建 → DROP 会**连带删掉**
#    它的下游 api 视图。bootstrap / 采集后刷新 / 安全网自愈 **三条路径**
#    都会重建基表，而每条路径只重建「自己计划里列出来的」目标 →
#    少列一个下游就少重建一个（表现为「跑完了，但某个视图 missing」）。
#
#    → 正解：**基表与它的全部下游必须放在同一个模块里**，且该模块列全下游。
#      business_overview 不持有积压视图 → 它的运行不会碰基表；
#      inventory_backlog = 积压资产组 → 重建基表时下游一起重建回来。
#
# 前端 `blocked` 同时检查两个模块 → 业务概览的「库存积压」面板照样受保护。
_INVENTORY_BACKLOG_ASSET_GROUP = [
    "mart.inventory_backlog_base",
    "api.business_overview_inventory_backlog_module",
    "api.inventory_backlog_summary_module",
    # SKU 级滞销清单（判据来自状态层）—— 缺了它，新环境/部署就没有这个视图
    "api.sku_clearance_ranking_module",
]

DASHBOARD_MODULE_TARGETS: dict[str, dict[str, list[str]]] = {
    "business_overview": {
        "core_targets": [
            "api.business_overview_kpi_module",
            "api.business_overview_comparison_platform_module",
            "api.business_overview_comparison_module",
            "api.business_overview_shop_racing_module",
            "api.business_overview_shop_racing_monthly_module",
            "api.business_overview_traffic_ranking_module",
            "api.business_overview_operational_metrics_module",
        ],
        "refresh_targets": [
            # 月度链（既有）
            "semantic.fact_orders_monthly_atomic_mv",
            "semantic.fact_analytics_monthly_atomic_mv",
            # 原子层物化副本（2026-11-04）：把「每行跑一次店铺别名解析」
            # 从请求路径搬到刷新路径。口径零变化（正文 = 普通视图正文）。
            # 日/周粒度 KPI 与 B 成本页读的都是这一层。
            "semantic.fact_orders_atomic_mv",
            "semantic.fact_analytics_atomic_mv",
        ],
    },
    "inventory_backlog": {
        "core_targets": list(_INVENTORY_BACKLOG_ASSET_GROUP),
        "refresh_targets": [],
    },
}

DASHBOARD_REQUIRED_SCHEMAS = ("semantic", "mart", "api", "ops")
OPS_TABLES = (
    "ops.pipeline_run_log",
    "ops.pipeline_step_log",
    "ops.data_freshness_log",
    "ops.data_lineage_registry",
    "ops.dashboard_asset_state",
)
EXTRA_TABLES = ("core.field_alias_rules",)

DASHBOARD_BOOTSTRAP_TARGETS = sorted(
    {
        target
        for module in DASHBOARD_MODULE_TARGETS.values()
        for target in module["core_targets"]
    }
)
DASHBOARD_REQUIRED_OBJECTS = [
    *sorted(
        {
            target
            for module in DASHBOARD_MODULE_TARGETS.values()
            for target in [*module["core_targets"], *module["refresh_targets"]]
        }
    ),
    *OPS_TABLES,
    *EXTRA_TABLES,
]

_DASHBOARD_BOOTSTRAP_LOCK_KEY = 918_240_113

#: 模块**可用**的状态（除 ``drift`` 外一律放行，页面照常展示）。
#:
#: 运行期门禁（``dashboard_api_postgresql._require_dashboard_assets_ready``）与
#: 刷新验收（``refresh_validation._module_status_is_ready``）**必须用同一份判定**。
#: 两边口径不一致 ⇒ 修复方把自己制造的 ``refreshing`` 状态当成失败条件 ⇒
#: 任务失败 ⇒ 退避重排 ⇒ 无限自锁（2026-11-07 事故链的一环）。
DASHBOARD_ASSET_AVAILABLE_STATUSES: frozenset[str] = frozenset({"ready", "refreshing"})


def _resolve_module_names(module: str = "all") -> list[str]:
    if module == "all":
        return list(DASHBOARD_MODULE_TARGETS.keys())
    if module not in DASHBOARD_MODULE_TARGETS:
        raise ValueError(f"Unknown dashboard module: {module}")
    return [module]


def _topological_sort_targets(
    targets: list[str],
    *,
    blocked_targets: set[str] | None = None,
) -> list[str]:
    ordered: list[str] = []
    blocked = blocked_targets or set()
    temporary: set[str] = set()
    permanent: set[str] = set(blocked)

    def visit(target: str) -> None:
        if target in permanent:
            return
        if target in temporary:
            raise ValueError(f"Cycle detected in refresh dependency graph at {target}")
        temporary.add(target)
        for dependency in PIPELINE_DEPENDENCIES.get(target, []):
            visit(dependency)
        temporary.remove(target)
        permanent.add(target)
        if target not in ordered:
            ordered.append(target)

    for target in targets:
        visit(target)
    return ordered


def _module_core_plan(module_name: str) -> list[str]:
    module = DASHBOARD_MODULE_TARGETS[module_name]
    return _topological_sort_targets(
        module["core_targets"],
        blocked_targets=set(module["refresh_targets"]),
    )


def _module_refresh_plan(module_name: str) -> list[str]:
    module = DASHBOARD_MODULE_TARGETS[module_name]
    refresh_targets = module["refresh_targets"]
    return _topological_sort_targets(refresh_targets) if refresh_targets else []


def _all_dashboard_core_plan() -> list[str]:
    targets: list[str] = []
    for module_name in DASHBOARD_MODULE_TARGETS:
        targets.extend(_module_core_plan(module_name))
    ordered: list[str] = []
    for target in targets:
        if target not in ordered:
            ordered.append(target)
    return ordered


def _compute_targets_fingerprint(targets: list[str]) -> str | None:
    if not targets:
        return None

    hasher = hashlib.sha256()
    root = Path(__file__).resolve().parents[3]
    for target in sorted(set(targets)):
        relative_path = SQL_TARGET_PATHS[target]
        path = root / relative_path
        hasher.update(target.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(relative_path.replace("\\", "/").encode("utf-8"))
        hasher.update(b"\0")
        try:
            hasher.update(path.read_bytes())
        except FileNotFoundError:
            hasher.update(b"")
        hasher.update(b"\0")
    return hasher.hexdigest()


def _json_safe_value(value: Any) -> Any:
    """把任意值**递归**收敛成 JSON 原生类型。

    为什么要有这个函数
    ------------------
    看板资产报告是**机器可读**产物（``--check --json``）⇒ 必须能直接
    ``json.dumps``。而报告里的值有一半是**从库里直接搬过来**的
    （``ops.pipeline_run_log.started_at`` / ``ops.dashboard_asset_state.updated_at``
    都是 ``timestamptz`` ⇒ 驱动返回 ``datetime``）⇒ 只要有一趟合法的刷新
    正在跑，``json.dumps`` 就抛 ``TypeError: Object of type datetime is not
    JSON serializable``。

    ⇒ 运维最需要机器可读结论的时刻，恰恰是这条命令不可用的时刻。

    规则
    ----
    * ``datetime`` / ``date`` → ISO 字符串（机器可读、且不丢时区信息）
    * ``Decimal`` → ``float``（jsonb 数值没有十进制语义）
    * ``dict`` / ``list`` / ``tuple`` → 逐层递归
    * ``str`` / ``int`` / ``float`` / ``bool`` / ``None`` → 原样保留
    * 其它对象 → ``str()`` 兜底（宁可给个可读字符串，也不要让序列化崩掉）
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _normalize_json_value(value: Any) -> dict[str, Any]:
    """把 jsonb 载荷归一化成 **JSON 安全的** dict。

    顶层契约**保持不变**：非 dict 一律返回 ``{}``
    （``context`` / ``details_json`` 两个 jsonb 列 + 既有 4 个调用点都依赖它）。

    与旧版的差别只有一处：dict **内部**会被递归 JSON 化
    （嵌套的 ``datetime`` / ``date`` / ``Decimal`` 不再漏到 ``json.dumps``）。
    """
    if not isinstance(value, dict):
        return {}
    return _json_safe_value(value)


async def _load_active_dashboard_refresh_runs(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    try:
        reg = await session.execute(text("SELECT to_regclass('ops.pipeline_run_log')"))
        if reg.scalar_one_or_none() is None:
            return {}
        result = await session.execute(
            text(
                """
                SELECT pipeline_name,
                       run_id,
                       status,
                       started_at,
                       completed_at,
                       context
                FROM ops.pipeline_run_log
                WHERE status = 'running'
                  AND (
                      pipeline_name LIKE 'dashboard_materialization_refresh.%'
                      OR pipeline_name LIKE 'dashboard_materialization_rebuild_core.%'
                      OR (
                          trigger_source = 'materialization_refresh'
                          AND context ? 'module_name'
                      )
                  )
                ORDER BY started_at DESC
                """
            )
        )
        runs: dict[str, dict[str, Any]] = {}
        for row in result.mappings():
            context = _normalize_json_value(row.get("context"))
            pipeline_name = str(row.get("pipeline_name") or "")
            module_name = context.get("module_name")
            if not module_name and "." in pipeline_name:
                module_name = pipeline_name.rsplit(".", 1)[-1]
            if not module_name:
                continue
            # 整行先归一化再进 report ⇒ ``started_at`` / ``completed_at``
            # 这两个 ``datetime`` 不会漏到 ``json.dumps``（见 ``_json_safe_value``）。
            normalized_row = _json_safe_value(dict(row))
            normalized_row["context"] = context
            runs[module_name] = normalized_row
        return runs
    except Exception:
        return {}


async def _try_advisory_lock(session: AsyncSession, key: int) -> bool:
    result = await session.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
    )
    return bool(result.scalar_one())


async def _advisory_unlock(session: AsyncSession, key: int) -> None:
    try:
        await session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    except Exception:
        pass


async def _advisory_lock(session: AsyncSession, key: int) -> None:
    await session.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})


async def _load_dashboard_asset_state(
    session: AsyncSession,
) -> dict[str, dict[str, Any]]:
    try:
        reg = await session.execute(
            text("SELECT to_regclass('ops.dashboard_asset_state')")
        )
        if reg.scalar_one_or_none() is None:
            return {}
        result = await session.execute(
            text(
                """
                SELECT module_name,
                       asset_fingerprint_expected,
                       asset_fingerprint_applied,
                       status,
                       run_id,
                       updated_at,
                       details_json
                FROM ops.dashboard_asset_state
                """
            )
        )
        rows = {}
        for row in result.mappings():
            # ``updated_at`` 是 ``timestamptz`` ⇒ 驱动返回 ``datetime``
            # ⇒ 整行归一化，别让它顺着 report 流到 ``json.dumps``。
            rows[row["module_name"]] = _json_safe_value(dict(row))
        return rows
    except Exception:
        return {}


async def _upsert_dashboard_asset_state(
    session: AsyncSession,
    *,
    module_name: str,
    asset_fingerprint_expected: str | None,
    asset_fingerprint_applied: str | None,
    status: str,
    run_id: str | None,
    details_json: dict[str, Any] | None = None,
) -> None:
    # 指纹回写入口的**唯一**一致性闸门（批次 3.6）：
    # 写入的 applied 必须等于本次算出的 expected —— 否则「跑一次就一定收敛」是假的
    # （库里是旧定义，表里却写着"已应用新指纹"）。
    if (
        asset_fingerprint_applied is not None
        and asset_fingerprint_expected is not None
        and asset_fingerprint_applied != asset_fingerprint_expected
    ):
        logger.warning(
            "[DashboardBootstrap] %s 写入的 applied 指纹与本次算出的 expected 不一致: "
            "applied=%s expected=%s",
            module_name,
            asset_fingerprint_applied,
            asset_fingerprint_expected,
        )
    await session.execute(
        text(
            """
            INSERT INTO ops.dashboard_asset_state (
                module_name,
                asset_fingerprint_expected,
                asset_fingerprint_applied,
                status,
                run_id,
                updated_at,
                details_json
            ) VALUES (
                :module_name,
                :asset_fingerprint_expected,
                :asset_fingerprint_applied,
                :status,
                :run_id,
                NOW(),
                CAST(:details_json AS jsonb)
            )
            ON CONFLICT (module_name) DO UPDATE
            SET asset_fingerprint_expected = EXCLUDED.asset_fingerprint_expected,
                asset_fingerprint_applied = EXCLUDED.asset_fingerprint_applied,
                status = EXCLUDED.status,
                run_id = EXCLUDED.run_id,
                updated_at = NOW(),
                details_json = EXCLUDED.details_json
            """
        ),
        {
            "module_name": module_name,
            "asset_fingerprint_expected": asset_fingerprint_expected,
            "asset_fingerprint_applied": asset_fingerprint_applied,
            "status": status,
            "run_id": run_id,
            "details_json": __import__("json").dumps(details_json or {}),
        },
    )


# ── 孤儿记账行清理（P3-1 / 批次 4.1）────────────────────────────────────
#
# ``ops.dashboard_asset_state`` 是**运维台账**：每个看板模块一行，记录该模块
# 资产的「期望指纹 / 已应用指纹 / 状态」。它**不是**业务事实数据。
#
# **孤儿记账行** = ``module_name`` 不在 ``DASHBOARD_MODULE_TARGETS`` 里的行
# —— 模块定义已经下线（或被并进别的模块），台账行还挂着。典型现场两种：
# * 模块被并进别的模块：``clearance_ranking`` → ``inventory_backlog``
#   （``api.sku_clearance_ranking_module`` 现在是 inventory_backlog 的 core target）；
# * 模块直接下线：台账里残留的 ``annual_summary``（2026-11-11 实测开发库可见）。
#
# ⚠️ 处置边界（硬约束，动这段代码前先读完）
# ----------------------------------------
# * **只删记账行**：物化视图 / 视图 / 表 / 模块定义**一律不碰**
#   ⇒ 允许出现的写语句只有 ``DELETE FROM ops.dashboard_asset_state``；
# * **默认不自动删**：必须显式开启（CLI ``--prune-orphan-asset-state``），
#   预览用 ``--dry-run``；
# * **删除前写日志**（module_name / 删除时间 / 行数）；
# * **与写记账同事务**（同一个 ``AsyncSession``、中间不 commit）
#   ⇒ 不会出现「新的写了、旧的还挂着」的中间态。


def _known_asset_state_module_names() -> list[str]:
    """``ops.dashboard_asset_state`` 里合法的模块名（= ``DASHBOARD_MODULE_TARGETS`` 的键）。"""
    return sorted(DASHBOARD_MODULE_TARGETS)


#: 删除孤儿记账行的**唯一**写语句 —— 只碰 ``ops.dashboard_asset_state`` 一张表，
#: 不带 CASCADE、不带任何 DDL ⇒ 物化视图 / 视图 / 表 / 模块定义一律不受影响。
_ORPHAN_ASSET_STATE_DELETE_SQL = text(
    "DELETE FROM ops.dashboard_asset_state WHERE module_name IN :module_names"
).bindparams(bindparam("module_names", expanding=True))


async def find_orphan_dashboard_asset_state_rows(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """列出孤儿记账行（**只读**，一条写语句都不发）。

    孤儿 = ``module_name`` 不在 ``DASHBOARD_MODULE_TARGETS`` 里。
    返回行已做 JSON 归一化（``updated_at`` 是 ``timestamptz`` ⇒ 驱动返回
    ``datetime`` ⇒ 直接进 ``json.dumps`` 会炸）。
    """
    reg = await session.execute(text("SELECT to_regclass('ops.dashboard_asset_state')"))
    if reg.scalar_one_or_none() is None:
        # 台账表都还没有 ⇒ 没有孤儿行（不是错误：新库的第一步）。
        return []
    result = await session.execute(
        text(
            """
            SELECT module_name,
                   status,
                   run_id,
                   updated_at,
                   asset_fingerprint_expected,
                   asset_fingerprint_applied
            FROM ops.dashboard_asset_state
            ORDER BY module_name
            """
        )
    )
    known = set(DASHBOARD_MODULE_TARGETS)
    orphans: list[dict[str, Any]] = []
    for row in result.mappings():
        module_name = str(row.get("module_name") or "")
        if module_name in known:
            continue
        orphans.append(_json_safe_value(dict(row)))
    return orphans


async def prune_orphan_dashboard_asset_state(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """清理孤儿记账行 —— **只删** ``ops.dashboard_asset_state`` 的行。

    ⚠️ 边界（改这段代码前先读上面的说明）：
    * 物化视图 / 视图 / 表 / 模块定义**一律不碰**；
    * ``dry_run=True`` 时**一个字节都不写**（只发 SELECT）；
    * 真删时**先写日志再删**；
    * 本函数**自己不 commit** —— 由调用方在同一个事务里提交
      ⇒ 与记账写入要么一起落库、要么一起回滚。
    """
    orphan_rows = await find_orphan_dashboard_asset_state_rows(session)
    module_names = sorted(
        {str(row.get("module_name") or "") for row in orphan_rows} - {""}
    )
    report: dict[str, Any] = {
        "dry_run": dry_run,
        "pruned": False,
        "deleted_count": 0,
        "deleted_module_names": [],
        "orphan_rows": orphan_rows,
        "known_module_names": _known_asset_state_module_names(),
    }
    if not module_names:
        return report

    if dry_run:
        report["would_delete_count"] = len(module_names)
        report["would_delete_module_names"] = module_names
        logger.info(
            "[DashboardBootstrap] 孤儿记账行预览（不写入）：module_name=%s 行数=%d",
            ",".join(module_names),
            len(module_names),
        )
        return report

    # ── 删除前写日志（硬约束）──
    deleted_at = datetime.now(timezone.utc).isoformat()
    logger.warning(
        "[DashboardBootstrap] 清理孤儿记账行：module_name=%s 行数=%d 删除时间=%s",
        ",".join(module_names),
        len(module_names),
        deleted_at,
    )
    await session.execute(
        _ORPHAN_ASSET_STATE_DELETE_SQL,
        {"module_names": module_names},
    )
    report.update(
        {
            "pruned": True,
            "deleted_count": len(module_names),
            "deleted_module_names": module_names,
            "deleted_at": deleted_at,
        }
    )
    return report


async def _collect_existing_assets(session: AsyncSession) -> tuple[set[str], set[str]]:
    schema_result = await session.execute(
        text(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = ANY(:schemas)
            ORDER BY schema_name
            """
        ),
        {"schemas": list(DASHBOARD_REQUIRED_SCHEMAS)},
    )
    existing_schemas = {row[0] for row in schema_result.fetchall()}

    object_result = await session.execute(
        text(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = ANY(:schemas)
            UNION
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema = ANY(:schemas)
            UNION
            SELECT schemaname AS table_schema, matviewname AS table_name
            FROM pg_matviews
            WHERE schemaname = ANY(:schemas)
            UNION
            -- **函数**型目标（如共享的店铺身份解析函数 semantic.resolve_shop_identity）
            -- 不在 information_schema.tables / views 里 ⇒ 只查关系会把它永远算成
            -- missing ⇒ 模块被判 drift ⇒ 部署 bootstrap 失败。
            SELECT n.nspname AS table_schema, p.proname AS table_name
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = ANY(:schemas)
            """
        ),
        {"schemas": ["semantic", "mart", "api", "ops", "core"]},
    )
    existing_objects = {f"{row[0]}.{row[1]}" for row in object_result.fetchall()}

    # 逻辑目标 ↔ 真实对象名 是**双向**的：
    # 存在性核对用的是逻辑名（如 ``semantic.shop_identity_resolver``），
    # 库里躺着的是真实名（如 ``semantic.resolve_shop_identity``）
    # ⇒ 真实名存在时，逻辑名也算存在。
    # 不做这一步 ⇒ 函数型目标永远被判 missing ⇒ 模块 drift ⇒ 部署被拦。
    for logical_name, object_name in LOGICAL_TARGET_OBJECTS.items():
        if object_name in existing_objects:
            existing_objects.add(logical_name)
    return existing_schemas, existing_objects


def _build_module_report(
    *,
    module_name: str,
    module_state: dict[str, Any] | None,
    existing_objects: set[str],
    active_refresh_run: dict[str, Any] | None,
) -> dict[str, Any]:
    core_targets = _module_core_plan(module_name)
    refresh_targets = _module_refresh_plan(module_name)
    core_expected = _compute_targets_fingerprint(core_targets)
    refresh_expected = _compute_targets_fingerprint(refresh_targets)

    details = _normalize_json_value((module_state or {}).get("details_json"))
    core_applied = (module_state or {}).get("asset_fingerprint_applied")
    refresh_applied = details.get("refresh_fingerprint_applied")
    core_missing = [
        target
        for target in core_targets
        if target not in existing_objects
        and LOGICAL_TARGET_OBJECTS.get(target) not in existing_objects
    ]
    refresh_missing = [
        target
        for target in refresh_targets
        if target not in existing_objects
        and LOGICAL_TARGET_OBJECTS.get(target) not in existing_objects
    ]
    stored_status = (module_state or {}).get("status")
    active_refreshing = active_refresh_run is not None

    # 刷新（物化）资产的**定义漂移** = 资产文件变了、但库里这批对象没重建。
    #
    # 为什么它**不参与状态判定**
    # ----------------------
    # 物化资产文件是「存在则 REFRESH / 不存在则 CREATE」
    # （见 ``sql/semantic/orders_atomic_mv.sql``）⇒ **对已存在的对象从不重建定义**。
    # 于是「文件哈希 != 账本里的 applied」这个差值，**没有任何自愈路径能消掉**
    # （安全网/刷新/重试全都只原地刷新或跳过）⇒ 拿它当状态判据 =
    # 制造一个「没人能修、却一直被当成异常、还被安全网无限重试」的死区。
    #
    # 2026-11-07 的自锁循环就是这么来的：迁移
    # ``20261112_realign_identity_candidates_anchor`` 重建了身份候选集视图与物化副本
    # （事实已是新的），但**没有回写** ``ops.dashboard_asset_state`` 的记账 ⇒
    # 记账停在旧文件哈希 ⇒ 模块被判 ``refreshing`` ⇒ 修复方把它当失败条件 ⇒
    # 退避重排 ⇒ 每 2~5 分钟一轮，攒出 859 次 failed 任务。
    #
    # 现在它降级为**纯可见性字段**（``refresh_fingerprint_drift``）：
    # 资产文件的定义对齐由**部署/迁移**负责（那是唯一能真正重建定义的地方），
    # 运行期状态机不再对它做任何判定 ⇒ 自锁从根上断开。
    refresh_fingerprint_drift = bool(
        refresh_expected and refresh_applied != refresh_expected
    )

    if (
        core_missing
        # 刷新资产缺失同样是**硬伤**（看板直接读不到）⇒ 与 core 缺失同级阻断。
        # 旧口径把它算成 ``refreshing`` ⇒ 页面照常展示（数据是空的），
        # 而修复路径对「已存在的普通视图」是跳过的 ⇒ 同样修不掉 ⇒ 又一个死区。
        or refresh_missing
        or (core_expected and core_applied != core_expected)
        or stored_status == "failed"
    ):
        status = "drift"
        ready = False
    elif active_refreshing:
        # 真的有一趟刷新在跑 ⇒ 「正在刷新」（可用，页面附带提示）。
        status = "refreshing"
        ready = True
    else:
        status = "ready"
        ready = True

    return {
        "module_name": module_name,
        "status": status,
        "ready": ready,
        "core_targets": core_targets,
        "refresh_targets": refresh_targets,
        "core_missing_objects": core_missing,
        "refresh_missing_objects": refresh_missing,
        "assets_drift": status == "drift",
        "asset_fingerprint_expected": core_expected,
        "asset_fingerprint_applied": core_applied,
        "refresh_fingerprint_expected": refresh_expected,
        "refresh_fingerprint_applied": refresh_applied,
        # 可见性字段：资产文件自上次落库以来有改动（**不阻断、不驱动修复**）。
        "refresh_fingerprint_drift": refresh_fingerprint_drift,
        "run_id": (module_state or {}).get("run_id"),
        "details": details,
        "active_refresh_run": _json_safe_value(active_refresh_run),
    }


async def inspect_dashboard_assets(session: AsyncSession) -> dict[str, Any]:
    existing_schemas, existing_objects = await _collect_existing_assets(session)
    state_rows = await _load_dashboard_asset_state(session)
    active_refresh_runs = await _load_active_dashboard_refresh_runs(session)

    modules: dict[str, dict[str, Any]] = {}
    for module_name in DASHBOARD_MODULE_TARGETS:
        modules[module_name] = _build_module_report(
            module_name=module_name,
            module_state=state_rows.get(module_name),
            existing_objects=existing_objects,
            active_refresh_run=active_refresh_runs.get(module_name),
        )

    missing_schemas = [
        schema
        for schema in DASHBOARD_REQUIRED_SCHEMAS
        if schema not in existing_schemas
    ]
    missing_objects = [
        name for name in DASHBOARD_REQUIRED_OBJECTS if name not in existing_objects
    ]
    ready = all(report["ready"] for report in modules.values())
    assets_drift = any(report["status"] == "drift" for report in modules.values())

    return _json_safe_value(
        {
            "ready": ready,
            "existing_schemas": sorted(existing_schemas),
            "missing_schemas": missing_schemas,
            "missing_objects": missing_objects,
            "assets_drift": assets_drift,
            "modules": modules,
        }
    )


async def bootstrap_dashboard_assets(
    session: AsyncSession,
    *,
    module: str = "all",
    prune_orphan_asset_state: bool = False,
) -> dict[str, Any]:
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    await execute_sql_file(session, "sql/ops/create_pipeline_tables.sql")
    await execute_sql_file(session, "sql/ops/create_field_alias_rules.sql")

    selected_modules = _resolve_module_names(module)
    module_run_ids: dict[str, str | None] = {}

    for module_name in selected_modules:
        core_targets = _module_core_plan(module_name)
        refresh_targets = _module_refresh_plan(module_name)
        core_expected = _compute_targets_fingerprint(core_targets)
        refresh_expected = _compute_targets_fingerprint(refresh_targets)
        existing_state = (await _load_dashboard_asset_state(session)).get(
            module_name, {}
        )
        existing_details = _normalize_json_value(existing_state.get("details_json"))

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            asset_fingerprint_expected=core_expected,
            asset_fingerprint_applied=existing_state.get("asset_fingerprint_applied"),
            status="drift",
            run_id=existing_state.get("run_id"),
            details_json={
                **existing_details,
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": existing_details.get(
                    "refresh_fingerprint_applied"
                ),
                "core_targets": core_targets,
                "refresh_targets": refresh_targets,
            },
        )

        refresh_run_id = None
        if refresh_targets:
            refresh_run_result = await execute_refresh_plan(
                session,
                targets=refresh_targets,
                pipeline_name=f"bootstrap_postgresql_dashboard_refresh.{module_name}",
                trigger_source="bootstrap",
                context={
                    "module_name": module_name,
                    "target_count": len(refresh_targets),
                    "refresh_fingerprint": refresh_expected,
                },
                preordered=True,
            )
            refresh_run_id = extract_run_id(refresh_run_result)

        run_result = await execute_refresh_plan(
            session,
            targets=core_targets,
            pipeline_name=f"bootstrap_postgresql_dashboard.{module_name}",
            trigger_source="bootstrap",
            context={
                "module_name": module_name,
                "target_count": len(core_targets),
                "asset_fingerprint": core_expected,
                "refresh_target_count": len(refresh_targets),
                "refresh_run_id": refresh_run_id,
            },
            preordered=True,
            # core 计划 = **定义**计划（普通视图 + 物化视图）。
            # 必须真的重建：跑完之后会把 asset_fingerprint_applied 写成 expected，
            # 跳过的目标就变成「系统以为定义已生效、库里其实还是旧定义」的静默漂移。
            # 这条计划在部署/迁移期跑（应用层已停），排他锁不会挡线上查询。
            recreate_views=True,
        )
        run_id = extract_run_id(run_result)
        module_run_ids[module_name] = run_id

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            asset_fingerprint_expected=core_expected,
            asset_fingerprint_applied=core_expected,
            status="ready",
            run_id=run_id,
            details_json={
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": (
                    refresh_expected
                    if refresh_targets
                    else existing_details.get("refresh_fingerprint_applied")
                ),
                "refresh_run_id": refresh_run_id,
                "core_targets": core_targets,
                "refresh_targets": refresh_targets,
            },
        )

    # ⚠️ 孤儿记账行清理与上面的记账写入**在同一个事务里**
    # （同一个 session、中间不 commit）⇒ 要么「新记账 + 删旧孤儿」一起落库，
    # 要么一起回滚 —— 不会出现「新的写了、旧的还挂着」的中间态。
    prune_report: dict[str, Any] | None = None
    if prune_orphan_asset_state:
        prune_report = await prune_orphan_dashboard_asset_state(session)

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
    if prune_report is not None:
        report["orphan_asset_state_prune"] = prune_report
    return report


async def refresh_dashboard_materialization_assets(
    session: AsyncSession,
    *,
    module: str = "all",
    prune_orphan_asset_state: bool = False,
) -> dict[str, Any]:
    await session.execute(text("SET LOCAL statement_timeout = 0"))
    selected_modules = _resolve_module_names(module)
    module_run_ids: dict[str, str | None] = {}

    for module_name in selected_modules:
        refresh_targets = _module_refresh_plan(module_name)
        if not refresh_targets:
            continue
        core_targets = _all_dashboard_core_plan()

        state = (await _load_dashboard_asset_state(session)).get(module_name, {})
        details = _normalize_json_value(state.get("details_json"))
        refresh_expected = _compute_targets_fingerprint(refresh_targets)
        # ⚠ 指纹口径必须与 ``bootstrap_dashboard_assets`` **完全一致**
        # (那边用的是 ``_module_core_plan(module_name)``) —— 否则两条路径写进
        # ``ops.dashboard_asset_state`` 的 expected/applied 互相打架,
        # 「跑一次就一定收敛」就成了假话(批次 3.6)。
        core_expected = _compute_targets_fingerprint(_module_core_plan(module_name))

        refresh_run_result = await execute_refresh_plan(
            session,
            targets=refresh_targets,
            pipeline_name=f"dashboard_materialization_refresh.{module_name}",
            trigger_source="materialization_refresh",
            context={
                "module_name": module_name,
                "target_count": len(refresh_targets),
                "refresh_fingerprint": refresh_expected,
            },
            preordered=True,
        )
        refresh_run_id = extract_run_id(refresh_run_result)
        run_result = await execute_refresh_plan(
            session,
            targets=core_targets,
            pipeline_name=f"dashboard_materialization_rebuild_core.{module_name}",
            trigger_source="materialization_refresh",
            context={
                "module_name": module_name,
                "target_count": len(core_targets),
                "asset_fingerprint": state.get("asset_fingerprint_expected"),
                "refresh_run_id": refresh_run_id,
            },
            preordered=True,
            # core 计划是**定义**计划 —— 必须真的重建，否则指纹会撒谎
            # （asset_fingerprint_applied 被写成 expected，库里却还是旧定义）。
            recreate_views=True,
        )
        run_id = extract_run_id(run_result)
        module_run_ids[module_name] = run_id

        await _upsert_dashboard_asset_state(
            session,
            module_name=module_name,
            # 回写**本次实算**的 core 指纹 —— 上面刚 ``recreate_views=True`` 真的
            # 重建了 core 定义, 沿用旧 state 的值等于让指纹撒谎(批次 3.6)。
            asset_fingerprint_expected=core_expected,
            asset_fingerprint_applied=core_expected,
            status="ready",
            run_id=run_id,
            details_json={
                **details,
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": refresh_expected,
                "refresh_run_id": refresh_run_id,
                "refresh_targets": refresh_targets,
                "core_targets": core_targets,
                "core_fingerprint": core_expected,
            },
        )

    # ⚠️ 与上面那次记账写入**同一个事务**（中间不 commit）——
    # 删旧孤儿与写新记账要么一起落库、要么一起回滚。
    prune_report: dict[str, Any] | None = None
    if prune_orphan_asset_state:
        prune_report = await prune_orphan_dashboard_asset_state(session)

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
    if prune_report is not None:
        report["orphan_asset_state_prune"] = prune_report
    return report


async def converge_dashboard_assets(
    session: AsyncSession,
    *,
    module: str = "all",
    prune_orphan_asset_state: bool = False,
) -> dict[str, Any]:
    """核心 bootstrap → 刷新物化资产 → 回写指纹 ⇒「跑一次就一定收敛」。

    为什么要有这条顺序链（批次 3.6）
    -------------------------------
    原来 CLI 的默认路径只做 ``bootstrap_dashboard_assets``（重建 core 定义 + 算指纹回写），
    而 ``--refresh-materializations`` 是**早返回**的另一条路径（只刷物化、不重建 core）。于是：

    * 只跑 bootstrap ⇒ 物化资产可能还是旧内容，指纹却已写成「已应用」⇒ **撒谎**；
    * 只跑 ``--refresh-materializations`` ⇒ core 定义没重建，回写的指纹还沿用旧值 ⇒ **不收敛**。

    ⇒ 合并成一条顺序链：先重建 core 并算出指纹，再刷物化，最后由
    ``refresh_dashboard_materialization_assets`` 用**本次实算**的指纹回写 ⇒
    跑一次就一定收敛。
    """
    core_report = await bootstrap_dashboard_assets(
        session,
        module=module,
        prune_orphan_asset_state=prune_orphan_asset_state,
    )
    await session.commit()
    refresh_report = await refresh_dashboard_materialization_assets(
        session,
        module=module,
        prune_orphan_asset_state=prune_orphan_asset_state,
    )
    await session.commit()
    report = dict(refresh_report)
    report["converged"] = True
    report["core_status"] = core_report.get("status")
    return report


async def bootstrap_dashboard_assets_if_needed(
    session: AsyncSession,
    *,
    wait_for_lock: bool = False,
    module: str = "all",
) -> dict[str, Any]:
    report = await inspect_dashboard_assets(session)
    selected_modules = _resolve_module_names(module)
    if all(
        report["modules"][module_name]["status"] in DASHBOARD_ASSET_AVAILABLE_STATUSES
        for module_name in selected_modules
    ):
        report["bootstrapped"] = False
        return report

    acquired = False
    if wait_for_lock:
        await session.execute(text("SET LOCAL statement_timeout = 0"))
        import asyncio

        deadline_seconds = 240.0
        poll_interval = 2.0
        waited = 0.0
        while waited <= deadline_seconds:
            acquired = await _try_advisory_lock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)
            if acquired:
                break
            await asyncio.sleep(poll_interval)
            waited += poll_interval
    else:
        acquired = await _try_advisory_lock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)

    if not acquired:
        report["bootstrapped"] = False
        report["bootstrap_in_progress"] = True
        return report

    try:
        report = await bootstrap_dashboard_assets(session, module=module)
        report["bootstrapped"] = True
        return report
    finally:
        await _advisory_unlock(session, _DASHBOARD_BOOTSTRAP_LOCK_KEY)
