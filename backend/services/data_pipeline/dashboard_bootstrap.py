from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import text
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


def _normalize_json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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
            runs[module_name] = dict(row)
            runs[module_name]["context"] = context
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
            rows[row["module_name"]] = dict(row)
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
        "active_refresh_run": active_refresh_run,
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

    return {
        "ready": ready,
        "existing_schemas": sorted(existing_schemas),
        "missing_schemas": missing_schemas,
        "missing_objects": missing_objects,
        "assets_drift": assets_drift,
        "modules": modules,
    }


async def bootstrap_dashboard_assets(
    session: AsyncSession,
    *,
    module: str = "all",
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

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
    return report


async def refresh_dashboard_materialization_assets(
    session: AsyncSession,
    *,
    module: str = "all",
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
            asset_fingerprint_expected=state.get("asset_fingerprint_expected"),
            asset_fingerprint_applied=state.get("asset_fingerprint_applied"),
            status="ready",
            run_id=run_id,
            details_json={
                **details,
                "refresh_fingerprint_expected": refresh_expected,
                "refresh_fingerprint_applied": refresh_expected,
                "refresh_run_id": refresh_run_id,
                "refresh_targets": refresh_targets,
                "core_targets": core_targets,
            },
        )

    report = await inspect_dashboard_assets(session)
    report["run_ids"] = module_run_ids
    report["module"] = module
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
