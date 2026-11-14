from __future__ import annotations

from pathlib import Path
import asyncio
import hashlib
import re
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.refresh_registry import (
    ASSET_PREREQUISITES,
    SQL_TARGET_PATHS,
    topologically_sort_targets,
)
from backend.services.data_pipeline.sql_loader import (
    load_sql_text,
    split_sql_statements,
)
from modules.core.logger import get_logger


_OPS_TABLES_LOCK = asyncio.Lock()
_OPS_REQUIRED_TABLES = {
    "pipeline_run_log",
    "pipeline_step_log",
    "data_freshness_log",
    "data_lineage_registry",
}
_OPS_TABLES_READY_SIGNATURE: tuple[str, str] | None = None
logger = get_logger(__name__)

#: 物化视图目标名（``schema.name``）。目标名来自 ``SQL_TARGET_PATHS``（仓库常量），
#: 这里再校验一次，避免任何拼接出来的名字变成可执行 SQL。
_MATERIALIZED_VIEW_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)
_CREATE_INDEX_PATTERN = re.compile(
    r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", re.IGNORECASE | re.MULTILINE
)
_LINE_COMMENT_PATTERN = re.compile(r"--[^\n]*")

#: 物化视图资产正文里「``AS SELECT * FROM <源视图>``」的形状。
#: 只有这种写法的副本才与源视图**严格同构**（列集一致）⇒ 形状守卫才有意义；
#: 正文带列裁剪的资产解析不到 ⇒ 不做守卫（不会误报）。
_MV_SELECT_STAR_SOURCE_PATTERN = re.compile(
    r"AS\s+SELECT\s+\*\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

#: 物化视图刷新的**语句超时预算**（毫秒）。
#:
#: 为什么需要
#: ----------
#: 连接池给每条连接设了 ``statement_timeout=120s``（``backend/models/database.py``），
#: 而 ``REFRESH MATERIALIZED VIEW`` 要**全量重算**：
#:
#: - ``semantic.fact_orders_atomic_mv``：生产实测 **115 秒**（贴着 120 秒的边）
#: - ``semantic.fact_products_atomic_mv``：生产实测 **23.2 秒**
#:
#: 115 秒离 120 秒只差 5 秒 —— 机器一忙就被数据库静默掐断，
#: 表现为「刷新任务莫名失败」。给它 10 分钟（最坏情况的 5 倍余量），
#: 既不会被掐断，也不会无上限地占着锁。
#:
#: 用 ``SET LOCAL``（事务级）而不是会话级 ``SET``：事务结束自动恢复，
#: 不污染连接池里归还给业务查询的连接。
MATERIALIZED_VIEW_REFRESH_TIMEOUT_MS = 10 * 60 * 1000


def extract_run_id(refresh_result: str | dict[str, Any]) -> str:
    if isinstance(refresh_result, dict):
        return str(refresh_result.get("run_id", ""))
    return str(refresh_result)


def extract_refresh_status(refresh_result: str | dict[str, Any]) -> str:
    if isinstance(refresh_result, dict):
        return str(refresh_result.get("status", "failed"))
    return "success"


def extract_failed_targets(refresh_result: str | dict[str, Any]) -> list[str]:
    if isinstance(refresh_result, dict):
        return [
            str(target) for target in (refresh_result.get("failed_targets", []) or [])
        ]
    return []


def extract_sqlstate(exc: BaseException | None) -> str:
    """取异常的 SQLSTATE（PostgreSQL 五位错误码）。

    取不到就返回空串 —— 调用方据此判断「该不该自动重排队」。
    """
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        sqlstate = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if sqlstate:
            return str(sqlstate)
    return ""


def _describe_failure(exc: BaseException) -> dict[str, str]:
    """把异常压成「错误原文 + SQLSTATE」，供队列判断能不能自动重试。"""
    return {
        "message": str(exc),
        "sqlstate": extract_sqlstate(exc),
    }


async def _commit_if_possible(db: Any) -> None:
    """能提交就提交（测试用的假 session 没有 ``commit``，跳过即可）。"""
    commit = getattr(db, "commit", None)
    if callable(commit):
        await commit()


def build_refresh_plan(targets: list[str]) -> list[str]:
    return topologically_sort_targets(targets)


def _target_type(target: str) -> str:
    if "." not in target:
        return "unknown"
    return target.split(".", 1)[0]


async def _ensure_ops_tables(db: AsyncSession) -> None:
    global _OPS_TABLES_READY_SIGNATURE
    try:
        bind = getattr(db, "get_bind", None)
        if callable(bind):
            engine = db.get_bind()
            db_url = str(getattr(engine, "url", "")) if engine is not None else ""
        else:
            engine = getattr(db, "bind", None)
            db_url = str(getattr(engine, "url", "")) if engine is not None else ""
    except Exception:
        db_url = ""

    signature = (db_url, "ops_tables_ready_v1")
    if _OPS_TABLES_READY_SIGNATURE == signature:
        return
    async with _OPS_TABLES_LOCK:
        if _OPS_TABLES_READY_SIGNATURE == signature:
            return
        existing_tables_result = await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'ops'
                  AND table_name IN (
                      'pipeline_run_log',
                      'pipeline_step_log',
                      'data_freshness_log',
                      'data_lineage_registry'
                  )
                """
            )
        )
        existing_tables_count = existing_tables_result.scalar() or 0
        if existing_tables_count >= len(_OPS_REQUIRED_TABLES):
            _OPS_TABLES_READY_SIGNATURE = signature
            return

        await execute_sql_file(db, "sql/ops/create_pipeline_tables.sql")
        _OPS_TABLES_READY_SIGNATURE = signature


async def _insert_run_log(
    db: AsyncSession,
    run_id: str,
    pipeline_name: str,
    trigger_source: str,
    context: dict | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.pipeline_run_log (
                run_id, pipeline_name, status, trigger_source, context
            ) VALUES (
                :run_id, :pipeline_name, 'running', :trigger_source, CAST(:context AS jsonb)
            )
            """
        ),
        {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "trigger_source": trigger_source,
            "context": "{}" if context is None else __import__("json").dumps(context),
        },
    )


async def _update_run_log(
    db: AsyncSession,
    run_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_run_log
            SET status = :status,
                completed_at = NOW(),
                error_message = :error_message
            WHERE run_id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "error_message": error_message,
        },
    )


async def _insert_step_log(
    db: AsyncSession,
    run_id: str,
    step_name: str,
    target_name: str,
    status: str,
    details: dict | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.pipeline_step_log (
                run_id, step_name, target_name, status, details
            ) VALUES (
                :run_id, :step_name, :target_name, :status, CAST(:details AS jsonb)
            )
            """
        ),
        {
            "run_id": run_id,
            "step_name": step_name,
            "target_name": target_name,
            "status": status,
            "details": "{}" if details is None else __import__("json").dumps(details),
        },
    )


async def _insert_skipped_step_log(
    db: AsyncSession,
    run_id: str,
    target_name: str,
    reason: str,
) -> None:
    await _insert_step_log(
        db,
        run_id=run_id,
        step_name="execute_sql_target",
        target_name=target_name,
        status="skipped",
        details={"reason": reason},
    )
    await _update_step_log(
        db,
        run_id=run_id,
        target_name=target_name,
        status="skipped",
        error_message=reason,
    )


async def _update_step_log(
    db: AsyncSession,
    run_id: str,
    target_name: str,
    status: str,
    affected_rows: int | None = None,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_step_log
            SET status = :status,
                completed_at = NOW(),
                affected_rows = :affected_rows,
                error_message = :error_message
            WHERE id = (
                SELECT id
                FROM ops.pipeline_step_log
                WHERE run_id = :run_id
                  AND target_name = :target_name
                ORDER BY id DESC
                LIMIT 1
            )
            """
        ),
        {
            "run_id": run_id,
            "target_name": target_name,
            "status": status,
            "affected_rows": affected_rows,
            "error_message": error_message,
        },
    )


async def _upsert_freshness_log(
    db: AsyncSession,
    target: str,
    status: str,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO ops.data_freshness_log (
                target_name, target_type, last_started_at, last_succeeded_at, status
            ) VALUES (
                :target_name, :target_type, NOW(),
                CASE WHEN :status = 'success' THEN NOW() ELSE NULL END,
                :status
            )
            ON CONFLICT (target_name) DO UPDATE
            SET target_type = EXCLUDED.target_type,
                last_started_at = NOW(),
                last_succeeded_at = CASE WHEN EXCLUDED.status = 'success' THEN NOW() ELSE ops.data_freshness_log.last_succeeded_at END,
                status = EXCLUDED.status
            """
        ),
        {
            "target_name": target,
            "target_type": _target_type(target),
            "status": status,
        },
    )


async def _sync_lineage_registry(db: AsyncSession, target: str) -> None:
    from backend.services.data_pipeline.refresh_registry import PIPELINE_DEPENDENCIES

    for dependency in PIPELINE_DEPENDENCIES.get(target, []):
        await db.execute(
            text(
                """
                INSERT INTO ops.data_lineage_registry (
                    target_name, target_type, source_name, source_type, dependency_level, active
                ) VALUES (
                    :target_name, :target_type, :source_name, :source_type, 1, TRUE
                )
                ON CONFLICT (target_name, source_name) DO UPDATE
                SET target_type = EXCLUDED.target_type,
                    source_type = EXCLUDED.source_type,
                    dependency_level = EXCLUDED.dependency_level,
                    active = TRUE
                """
            ),
            {
                "target_name": target,
                "target_type": _target_type(target),
                "source_name": dependency,
                "source_type": _target_type(dependency),
            },
        )


async def execute_sql_text(db: AsyncSession, sql_text: str) -> None:
    for statement in split_sql_statements(sql_text):
        await db.execute(text(statement))


async def execute_sql_file(db: AsyncSession, path: str | Path) -> None:
    await execute_sql_text(db, load_sql_text(path))


async def _replace_step_details(
    db: AsyncSession,
    *,
    run_id: str,
    target_name: str,
    details: dict,
) -> None:
    await db.execute(
        text(
            """
            UPDATE ops.pipeline_step_log
            SET details = CAST(:details AS jsonb)
            WHERE id = (
                SELECT id
                FROM ops.pipeline_step_log
                WHERE run_id = :run_id
                  AND target_name = :target_name
                ORDER BY id DESC
                LIMIT 1
            )
            """
        ),
        {
            "run_id": run_id,
            "target_name": target_name,
            "details": __import__("json").dumps(details),
        },
    )


async def _target_view_kind(db: AsyncSession, target: str) -> Optional[str]:
    """目标在库里是什么类型。

    返回 ``'v'``=普通视图、``'m'``=物化视图、``None``=不存在（或不是视图）。

    用 ``pg_class`` 目录查（一次索引查找，很便宜）。

    ⚠️ ``pg_class.relkind`` 的列类型是 PostgreSQL 内部的 ``"char"``，
    asyncpg 把它映射成 **bytes**（``b'v'`` / ``b'm'``），不是 str。
    不解码就直接和 ``("v", "m")`` 比会**永远不相等** ——
    于是「普通视图跳过重建」这条对策（2026-10-26 排他锁事故的正解）
    从来没生效过，每次数据刷新都在 ``CREATE OR REPLACE VIEW``。
    """
    if "." not in target:
        return None
    schema, name = target.split(".", 1)
    try:
        result = await db.execute(
            text(
                """
                SELECT c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :schema AND c.relname = :name
                """
            ),
            {"schema": schema, "name": name},
        )
    except Exception:  # noqa: BLE001
        return None
    kind = result.scalar_one_or_none()
    if isinstance(kind, (bytes, bytearray)):
        kind = bytes(kind).decode("ascii", errors="replace")
    return kind if kind in ("v", "m") else None


def _materialized_view_lock_key(target: str) -> int:
    """物化视图的互斥锁键（稳定哈希 → 有符号 64 位整数）。

    同一个目标名永远得到同一个键 ⇒ 不同进程/不同连接之间也一致。
    """
    digest = hashlib.blake2b(target.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


async def _is_postgresql(db: AsyncSession) -> bool:
    """当前连接是不是 PostgreSQL（advisory lock 是 PG 独有的）。"""
    try:
        bind = db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", ""))
    except Exception:  # noqa: BLE001
        return False
    return dialect_name == "postgresql"


async def _try_lock_materialized_view(db: AsyncSession, target: str) -> bool:
    """尝试拿到这个物化视图的刷新互斥锁。

    为什么需要
    ----------
    刷新队列现在**按业务域分道并发**（最多 2 道）。两个域都依赖同一个共享
    物化视图 ``semantic.shop_identity_resolution_candidates_v2_mv``
    ⇒ 可能同时去 REFRESH 它 ⇒ 互相等锁，甚至沿视图链 ABBA 死锁。

    用 ``pg_try_advisory_xact_lock``（事务级、非阻塞）：
    拿不到就**跳过这个物化视图**，并记一条 step log。
    跳过是安全的 —— 另一道正在刷它，刷完的数据是一样的（甚至更新）。
    """
    if not await _is_postgresql(db):
        return True
    result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
        {"lock_key": _materialized_view_lock_key(target)},
    )
    return bool(result.scalar_one_or_none())


async def _current_statement_timeout(db: AsyncSession) -> str:
    """读当前连接的语句超时（形如 ``2min`` / ``120s`` / ``0``）。"""
    try:
        result = await db.execute(text("SELECT current_setting('statement_timeout')"))
        value = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        value = None
    return str(value) if value else "0"


async def _set_local_statement_timeout(db: AsyncSession, value: str | int) -> None:
    """把语句超时**临时**改成 ``value``（事务级，事务结束自动恢复）。

    为什么用 ``set_config`` 而不是 ``SET``
    ------------------------------------
    ``SET`` 是 utility statement，**不接受参数占位符**（只能拼字面量）。
    ``set_config(name, value, is_local)`` 是普通函数，能绑参数 ⇒ 没有注入面。

    第三个参数 ``true`` = 只在当前事务内生效（等价于 ``SET LOCAL``）。
    """
    await db.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": str(value)},
    )


def _materialized_view_source(asset_text: str) -> Optional[str]:
    """从物化视图资产文件里解析出源视图（正文 = ``SELECT * FROM <源>``）。

    解析不到 ⇒ 返回 ``None`` = 不做形状检查（正文带列裁剪、或用了
    ``DROP ... CASCADE`` 写法的资产）—— 只对**严格同构**的副本做守卫。

    匹配前先剥掉行注释：注释里写一句 ``AS SELECT * FROM x`` 不该被当成定义。
    """
    without_comments = _LINE_COMMENT_PATTERN.sub("", asset_text)
    match = _MV_SELECT_STAR_SOURCE_PATTERN.search(without_comments)
    if not match:
        return None
    return match.group(1)


async def _relation_columns(db: AsyncSession, relation_name: str) -> Optional[str]:
    """取一个关系的列名序列（按列序），关系不存在时返回 ``None``。

    必须用 ``pg_attribute``：**``information_schema.columns`` 不含物化视图**
    （relkind='m' 不在它的范围内）⇒ 用它查副本永远得到 NULL。
    """
    result = await db.execute(
        text(
            """
            SELECT string_agg(a.attname, ',' ORDER BY a.attnum)
              FROM pg_attribute a
             WHERE a.attrelid = to_regclass(:name)
               AND a.attnum > 0
               AND NOT a.attisdropped
            """
        ),
        {"name": relation_name},
    )
    return result.scalar_one_or_none()


async def _assert_materialized_view_shape(
    db: AsyncSession, target: str, source: str
) -> None:
    """副本与源视图的列集必须一致，否则 ``REFRESH`` 会**静默丢列**。

    为什么需要这道守卫
    ------------------
    源视图是普通视图（``CREATE OR REPLACE VIEW``）⇒ 加列时**不会**连带删掉下游；
    而 ``REFRESH MATERIALIZED VIEW`` **不会新增列** ⇒ 副本会静默少一列，
    后面所有读副本的查询都缺那一列，而且**全程不报错**。

    fail-closed：列集不一致就报错停下（修法：手工删掉副本后重跑刷新计划）。
    """
    target_columns = await _relation_columns(db, target)
    source_columns = await _relation_columns(db, source)
    if target_columns is None or source_columns is None:
        # 有一侧不存在 ⇒ 不比较（创建/自愈路径由资产文件自己处理）。
        return
    if target_columns != source_columns:
        raise RuntimeError(
            "物化视图 {target} 的列集与源视图 {source} 不一致："
            "REFRESH MATERIALIZED VIEW 不会新增列，继续刷新会静默丢列。"
            "请手工删除该物化视图（连带删掉的下游视图由刷新计划重建）后重跑刷新计划。".format(
                target=target, source=source
            )
        )


async def _refresh_materialized_view(
    db: AsyncSession, target: str, sql_path: str | Path
) -> bool:
    """数据刷新时**原地刷新**物化视图，不执行它的 SQL 资产文件。

    返回 ``True`` = 刷了；``False`` = 别的道正在刷同一个视图，本次跳过。

    为什么不能直接跑资产文件
    ----------------------
    物化视图的资产文件里带 ``DROP MATERIALIZED VIEW ... CASCADE``
    （见 ``sql/semantic/orders_monthly_atomic_mv.sql``），而资产文件
    **每次数据刷新都会被执行**。于是每次刷新都会：

    1. 连带删掉全部下游视图（monthly 那条链有 10 个对象：
       ``semantic.fact_orders_monthly_atomic``、``mart.shop_month_kpi``、
       ``mart.platform_month_kpi``、``api.business_overview_*`` 共 8 个），
       它们必须被重新建回来 → 期间看板查询直接报 ``relation does not exist``；
    2. 长时间持排他锁，把并发读写的 ``pg_dump`` 堵死 ——
       2026-11 本地启动失败事故（``migration_backup_failed``）的放大器就是它；
    3. 全量重算 + 重建 10 个下游，刷新窗口被拉长到分钟级。

    数据刷新要的是「**数据变新**」，不是「定义变新」。
    定义变更走 ``scripts/rebuild_views.py``（显式重建）那条路 ——
    那条路本来就会重建下游，语义保持不变。

    索引照旧补齐
    ------------
    索引是 MV 创建时带出来的，``REFRESH`` 不会重建它 —— 所以这里把资产文件里
    的 ``CREATE INDEX IF NOT EXISTS`` 照常执行（它们是幂等的），
    这样「新增索引」仍然能自动生效。

    物化视图**不存在**时：回落到跑资产文件
    -------------------------------------
    物化视图有可能被**普通视图的重建**连带删掉 ——
    ``sql/semantic/analytics_atomic.sql`` 开头是
    ``DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE``，
    而 ``semantic.fact_analytics_atomic_mv`` 正是它的下游
    （生产实测的 pg_depend 闭包）。这类资产文件里的
    「存在则 REFRESH / 不存在则 CREATE」（见 ``analytics_atomic_mv.sql``）
    本来就是为这个场景准备的**自愈**机制。

    所以这里必须保留这条回落路径：只 ``REFRESH`` 会直接报
    ``relation "..." does not exist``，看板当场查不出来。
    """
    if not _MATERIALIZED_VIEW_PATTERN.match(target):
        raise ValueError(f"invalid materialized view target: {target}")
    if await _target_view_kind(db, target) != "m":
        # 不存在 → 跑资产文件：它的正文自带「存在则 REFRESH / 不存在则 CREATE」。
        await execute_sql_file(db, sql_path)
        return True
    if not await _try_lock_materialized_view(db, target):
        # 另一道正在刷这个物化视图 → 本次跳过（数据不会更旧：对方刷完就是最新的）。
        logger.info(
            "[refresh_runner] target=%s 跳过刷新（另一条刷新道正在刷它）", target
        )
        return False
    # 形状守卫：副本与源视图的列集必须一致（不一致 ⇒ REFRESH 会静默丢列）。
    # 源视图从资产文件解析（资产文件是 SSOT，不另立一份声明）。
    asset_text = load_sql_text(sql_path)
    source_view = _materialized_view_source(asset_text)
    if source_view:
        await _assert_materialized_view_shape(db, target, source_view)
    # 临时抬高语句超时预算：REFRESH 要全量重算，生产实测最慢 115 秒，
    # 而连接池默认 120 秒 —— 差 5 秒就被掐断。
    baseline_timeout = await _current_statement_timeout(db)
    await _set_local_statement_timeout(db, MATERIALIZED_VIEW_REFRESH_TIMEOUT_MS)
    try:
        await db.execute(text(f"REFRESH MATERIALIZED VIEW {target}"))
    finally:
        # 事务级设置：就算 REFRESH 抛错，这里的 SET 也会随 savepoint 回滚；
        # 显式恢复是为了让**同一事务里后面的语句**回到正常预算。
        try:
            await _set_local_statement_timeout(db, baseline_timeout)
        except Exception:  # noqa: BLE001
            pass
    for statement in split_sql_statements(asset_text):
        without_comments = _LINE_COMMENT_PATTERN.sub("", statement)
        if _CREATE_INDEX_PATTERN.match(without_comments):
            await db.execute(text(statement))
    return True


async def execute_sql_target(
    db: AsyncSession,
    target: str,
    pipeline_name: str = "refresh_sql_target",
    trigger_source: str = "system",
    context: dict | None = None,
    run_id: str | None = None,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
    resolve_dependencies: bool = False,
    recreate_views: bool = False,
) -> str:
    """执行一个刷新目标（及其上游依赖，若显式要求）。"""
    active_run_id = run_id or f"run_{uuid.uuid4().hex}"
    await _ensure_ops_tables(db)
    if run_id is None:
        await _insert_run_log(
            db,
            run_id=active_run_id,
            pipeline_name=pipeline_name,
            trigger_source=trigger_source,
            context={"target": target, **(context or {})},
        )
    await _insert_step_log(
        db,
        run_id=active_run_id,
        step_name="execute_sql_target",
        target_name=target,
        status="running",
        details={"target_type": _target_type(target)},
    )
    if resolve_dependencies:
        ordered_targets = build_refresh_plan([target])
    else:
        ordered_targets = [target]
    # 建对象前置：目标资产的正文引用了别的对象，那些对象必须先在。
    # 例：``semantic.fact_orders_atomic`` 读候选集物化副本
    # ``semantic.shop_identity_resolution_candidates_v2_mv`` —— 副本不存在时
    # 建视图会直接报 ``relation does not exist``。
    prerequisites: list[str] = []
    for planned_target in ordered_targets:
        for prerequisite in ASSET_PREREQUISITES.get(planned_target, []):
            if (
                prerequisite not in prerequisites
                and prerequisite not in ordered_targets
            ):
                prerequisites.append(prerequisite)
    if prerequisites:
        ordered_targets = prerequisites + ordered_targets
    last_error: Exception | None = None
    last_sql_path: str | None = None
    last_attempt = 0
    last_success_target: str | None = None
    try:
        for planned_target in ordered_targets:
            if planned_target == "ops.pipeline_run_log":
                sql_path = "sql/ops/create_pipeline_tables.sql"
            else:
                sql_path = SQL_TARGET_PATHS[planned_target]
            last_sql_path = str(sql_path)
            target_kind = None
            if not recreate_views:
                target_kind = await _target_view_kind(db, planned_target)
            if not recreate_views and target_kind == "v":
                # 普通视图的数据是**查询时实时算**的 → 数据刷新时根本不需要重建它。
                # 而重建要走 CREATE OR REPLACE VIEW → 拿 ACCESS EXCLUSIVE 排他锁 →
                # 期间**所有**并发读写都被挡住（商品中心保存会卡住），
                # 两个刷新进程还会沿视图链 ABBA 死锁（2026-10-26 线上事故）。
                # 视图**定义**变更请走 scripts/rebuild_views.py 显式重建。
                logger.info(
                    "[refresh_runner] run_id=%s target=%s 跳过重建（普通视图已存在，定义变更请走 rebuild_views）",
                    active_run_id,
                    planned_target,
                )
                await _insert_step_log(
                    db,
                    run_id=active_run_id,
                    step_name="execute_sql_target",
                    target_name=planned_target,
                    status="skipped",
                    details={"reason": "view_not_recreated_on_data_refresh"},
                )
                last_success_target = planned_target
                continue
            attempts = max(1, max_attempts)
            for attempt in range(1, attempts + 1):
                last_attempt = attempt
                logger.info(
                    "[refresh_runner] run_id=%s target=%s sql=%s attempt=%s/%s",
                    active_run_id,
                    planned_target,
                    sql_path,
                    attempt,
                    attempts,
                )
                try:
                    refreshed = True
                    async with db.begin_nested():
                        if not recreate_views and target_kind == "m":
                            # 物化视图：数据刷新只做**原地 REFRESH**，
                            # 不跑资产文件（文件里的 DROP ... CASCADE 会删掉下游，
                            # 还会长时间持锁把 pg_dump 堵死）。
                            refreshed = await _refresh_materialized_view(
                                db, planned_target, sql_path
                            )
                        else:
                            await execute_sql_file(db, sql_path)
                    if not refreshed:
                        # 另一条刷新道正在刷这个物化视图 → 本次跳过，不算失败。
                        await _insert_step_log(
                            db,
                            run_id=active_run_id,
                            step_name="execute_sql_target",
                            target_name=planned_target,
                            status="skipped",
                            details={
                                "reason": "materialized_view_refreshed_by_other_lane"
                            },
                        )
                        last_success_target = planned_target
                        break
                    await _sync_lineage_registry(db, planned_target)
                    await _upsert_freshness_log(db, planned_target, "success")
                    last_success_target = planned_target
                    break
                except Exception as exc:
                    last_error = exc
                    logger.error(
                        "[refresh_runner] target failed run_id=%s target=%s sql=%s attempt=%s/%s error=%s",
                        active_run_id,
                        planned_target,
                        sql_path,
                        attempt,
                        attempts,
                        exc,
                    )
                    if attempt < attempts and retry_backoff_seconds > 0:
                        await asyncio.sleep(retry_backoff_seconds * attempt)
            else:
                assert last_error is not None
                raise last_error

        await _update_step_log(
            db,
            active_run_id,
            target,
            "success",
        )
        await _replace_step_details(
            db,
            run_id=active_run_id,
            target_name=target,
            details={
                "target_type": _target_type(target),
                "attempts": str(last_attempt or max(1, max_attempts)),
                "ordered_targets": ordered_targets,
                "sql_path": last_sql_path,
                "last_success_target": last_success_target,
            },
        )
        if run_id is None:
            await _update_run_log(db, active_run_id, "success")
        return active_run_id
    except Exception as exc:
        last_error = exc
        await _upsert_freshness_log(db, target, "failed")
        await _update_step_log(
            db, active_run_id, target, "failed", error_message=str(last_error)
        )
        await _replace_step_details(
            db,
            run_id=active_run_id,
            target_name=target,
            details={
                "target_type": _target_type(target),
                "attempts": str(last_attempt or max(1, max_attempts)),
                "ordered_targets": ordered_targets,
                "sql_path": last_sql_path,
                "last_success_target": last_success_target,
                "error_summary": str(last_error),
            },
        )
        if run_id is None:
            await _update_run_log(
                db, active_run_id, "failed", error_message=str(last_error)
            )
        raise


async def execute_refresh_plan(
    db: AsyncSession,
    targets: list[str],
    pipeline_name: str = "refresh_plan",
    trigger_source: str = "system",
    context: dict | None = None,
    continue_on_error: bool = False,
    max_attempts: int = 1,
    retry_backoff_seconds: float = 0.0,
    preordered: bool = False,
    recreate_views: bool = False,
) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex}"
    ordered_targets = list(targets) if preordered else build_refresh_plan(targets)
    await _ensure_ops_tables(db)
    await _insert_run_log(
        db,
        run_id=run_id,
        pipeline_name=pipeline_name,
        trigger_source=trigger_source,
        context={
            "targets": targets,
            "ordered_targets": ordered_targets,
            **(context or {}),
        },
    )
    failed_targets: set[str] = set()
    #: 每个失败目标的「错误原文 + SQLSTATE」。
    #: SQLSTATE 是「这条失败该不该自动重排队」的判据（见 ``refresh_queue_tasks``）——
    #: 只看错误字符串分不出来「锁冲突（该重试）」和「口径写错（重试没用）」。
    failed_target_errors: dict[str, dict[str, str]] = {}
    try:
        for target in ordered_targets:
            from backend.services.data_pipeline.refresh_registry import (
                PIPELINE_DEPENDENCIES,
            )

            failed_dependencies = [
                dependency
                for dependency in PIPELINE_DEPENDENCIES.get(target, [])
                if dependency in failed_targets
            ]
            if failed_dependencies:
                await _insert_skipped_step_log(
                    db,
                    run_id=run_id,
                    target_name=target,
                    reason=f"dependency_failed:{','.join(failed_dependencies)}",
                )
                continue
            await execute_sql_target(
                db,
                target,
                pipeline_name=pipeline_name,
                trigger_source=trigger_source,
                context=context,
                run_id=run_id,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                recreate_views=recreate_views,
            )
            # 逐目标提交（2026-11-11）：
            # 物化视图的 ACCESS EXCLUSIVE 锁是**事务级**的 —— 不提交就一直占着。
            # 以前整个刷新计划是一个大事务 ⇒ 一个域刷新时把另一个域要读的对象
            # 死死锁住，「2 道并发」会退化成「2 道互相等锁」。
            # 逐目标提交后：每个目标做完就落库、就释放锁 ⇒ 两条道真能并行。
            await _commit_if_possible(db)
        if failed_targets:
            await _update_run_log(db, run_id, "partial_failed")
        else:
            await _update_run_log(db, run_id, "success")
        return {
            "run_id": run_id,
            "status": "partial_failed" if failed_targets else "success",
            "failed_targets": sorted(failed_targets),
            "failed_target_errors": failed_target_errors,
        }
    except Exception as exc:
        if continue_on_error:
            failed_targets.add(target)
            failed_target_errors[target] = _describe_failure(exc)
            for remaining_target in ordered_targets[
                ordered_targets.index(target) + 1 :
            ]:
                from backend.services.data_pipeline.refresh_registry import (
                    PIPELINE_DEPENDENCIES,
                )

                failed_dependencies = [
                    dependency
                    for dependency in PIPELINE_DEPENDENCIES.get(remaining_target, [])
                    if dependency in failed_targets
                ]
                if failed_dependencies:
                    await _insert_skipped_step_log(
                        db,
                        run_id=run_id,
                        target_name=remaining_target,
                        reason=f"dependency_failed:{','.join(failed_dependencies)}",
                    )
                else:
                    try:
                        await execute_sql_target(
                            db,
                            remaining_target,
                            pipeline_name=pipeline_name,
                            trigger_source=trigger_source,
                            context=context,
                            run_id=run_id,
                            max_attempts=max_attempts,
                            retry_backoff_seconds=retry_backoff_seconds,
                        )
                        await _commit_if_possible(db)
                    except Exception as remaining_exc:  # noqa: BLE001
                        failed_targets.add(remaining_target)
                        failed_target_errors[remaining_target] = _describe_failure(
                            remaining_exc
                        )
            await _update_run_log(db, run_id, "partial_failed", error_message=str(exc))
            return {
                "run_id": run_id,
                "status": "partial_failed",
                "failed_targets": sorted(failed_targets),
                "failed_target_errors": failed_target_errors,
            }
        await _update_run_log(db, run_id, "failed", error_message=str(exc))
        raise
