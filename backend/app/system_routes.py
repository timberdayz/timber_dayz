import os
from datetime import datetime
from datetime import timezone

from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.collection_runtime_health import (
    collect_collection_runtime_health,
)


def register_system_routes(app, settings, app_version, get_db):
    def _safe_age_seconds(value: str | None) -> float:
        if not value:
            return -1.0
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return -1.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds(), 0.0)

    def _emit_metric(lines: list[str], name: str, value: float | int, labels: dict[str, str] | None = None) -> None:
        if labels:
            rendered = ",".join(f'{key}="{str(val).replace(chr(34), "")}"' for key, val in sorted(labels.items()))
            lines.append(f"{name}{{{rendered}}} {value}")
            return
        lines.append(f"{name} {value}")
    @app.get("/api/healthz/live", tags=["系统"])
    @app.get("/healthz/live", tags=["系统"])
    async def live_health_check():
        return {
            "status": "alive",
            "service": "西虹ERP系统API",
            "version": app_version,
            "timestamp": datetime.now().isoformat(),
        }

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        from backend.models.database import AsyncSessionLocal, SessionLocal
        from backend.services.cloud_sync_admin_query_service import CloudSyncAdminQueryService
        from backend.services.postgresql_dashboard_service import PostgresqlDashboardService
        from backend.tasks.scheduled_tasks import detect_auto_ingest_orphan_locks

        runtime = getattr(app.state, "cloud_sync_runtime", None)
        runtime_health = runtime.get_health() if runtime is not None else None

        overview = {}
        runtime_summary = {}
        table_states = []
        try:
            async with AsyncSessionLocal() as session:
                service = CloudSyncAdminQueryService(session)
                overview = await service.get_overview_summary(runtime_health=runtime_health)
                runtime_summary = await service.get_runtime_summary(runtime_health=runtime_health)
                table_states = await service.list_table_states()
        except Exception:
            overview = {}
            runtime_summary = {}
            table_states = []

        freshness_checks = []
        try:
            dashboard_service = PostgresqlDashboardService()
            freshness = await dashboard_service.get_business_overview_data_freshness()
            freshness_checks = freshness.get("table_checks", [])
        except Exception:
            freshness_checks = []

        orphan_lock_count = 0
        try:
            db = SessionLocal()
            try:
                orphan_lock_count = len(detect_auto_ingest_orphan_locks(db))
            finally:
                db.close()
        except Exception:
            orphan_lock_count = 0

        cloud_receive_summary = {
            "available": False,
            "last_receive_at": None,
            "table_receives": {},
        }
        try:
            from backend.services.cloud_sync_receive_log_query import (
                CloudSyncReceiveLogQuery,
            )

            cloud_receive_summary = CloudSyncReceiveLogQuery().get_latest_receive_summary()
        except Exception:
            cloud_receive_summary = {
                "available": False,
                "last_receive_at": None,
                "table_receives": {},
            }

        lines = [
            "# HELP xihong_cloud_sync_pending_catalog_files_total Pending catalog files awaiting local ingest.",
            "# TYPE xihong_cloud_sync_pending_catalog_files_total gauge",
        ]
        _emit_metric(lines, "xihong_cloud_sync_pending_catalog_files_total", int(overview.get("pending_catalog_file_count") or 0))
        lines.extend(
            [
                "# HELP xihong_cloud_sync_pending_catalog_files_overdue_total Pending catalog files older than 10 minutes.",
                "# TYPE xihong_cloud_sync_pending_catalog_files_overdue_total gauge",
            ]
        )
        _emit_metric(lines, "xihong_cloud_sync_pending_catalog_files_overdue_total", int(overview.get("overdue_pending_catalog_file_count") or 0))
        lines.extend(
            [
                "# HELP xihong_cloud_sync_refresh_queue_failed_total Failed refresh queue tasks triggered by cloud sync.",
                "# TYPE xihong_cloud_sync_refresh_queue_failed_total gauge",
            ]
        )
        _emit_metric(lines, "xihong_cloud_sync_refresh_queue_failed_total", int(overview.get("refresh_failed_task_count") or 0))
        lines.extend(
            [
                "# HELP xihong_cloud_sync_orphan_lock_count Idle auto-ingest advisory locks without a running task.",
                "# TYPE xihong_cloud_sync_orphan_lock_count gauge",
            ]
        )
        _emit_metric(lines, "xihong_cloud_sync_orphan_lock_count", orphan_lock_count)
        lines.extend(
            [
                "# HELP xihong_cloud_sync_receive_log_available Whether cloud receive log can be queried.",
                "# TYPE xihong_cloud_sync_receive_log_available gauge",
            ]
        )
        _emit_metric(
            lines,
            "xihong_cloud_sync_receive_log_available",
            1 if cloud_receive_summary.get("available") else 0,
        )
        lines.extend(
            [
                "# HELP xihong_cloud_sync_cloud_db_available Whether cloud database can be queried for receive log.",
                "# TYPE xihong_cloud_sync_cloud_db_available gauge",
            ]
        )
        _emit_metric(
            lines,
            "xihong_cloud_sync_cloud_db_available",
            1 if cloud_receive_summary.get("available") else 0,
        )
        lines.extend(
            [
                "# HELP xihong_cloud_sync_receive_age_seconds Age in seconds since the latest successful cloud receive log.",
                "# TYPE xihong_cloud_sync_receive_age_seconds gauge",
            ]
        )
        _emit_metric(
            lines,
            "xihong_cloud_sync_receive_age_seconds",
            _safe_age_seconds(cloud_receive_summary.get("last_receive_at")),
        )
        lines.extend(
            [
                "# HELP xihong_cloud_sync_runtime_heartbeat_age_seconds Age in seconds since runtime heartbeat.",
                "# TYPE xihong_cloud_sync_runtime_heartbeat_age_seconds gauge",
            ]
        )
        _emit_metric(lines, "xihong_cloud_sync_runtime_heartbeat_age_seconds", _safe_age_seconds(runtime_summary.get("last_runtime_heartbeat_at")))
        lines.extend(
            [
                "# HELP xihong_cloud_sync_task_heartbeat_age_seconds Age in seconds since current task heartbeat.",
                "# TYPE xihong_cloud_sync_task_heartbeat_age_seconds gauge",
            ]
        )
        _emit_metric(lines, "xihong_cloud_sync_task_heartbeat_age_seconds", float(runtime_summary.get("seconds_since_task_heartbeat") or -1))
        lines.extend(
            [
                "# HELP xihong_cloud_sync_table_receive_age_seconds Age in seconds since latest receive log per source table.",
                "# TYPE xihong_cloud_sync_table_receive_age_seconds gauge",
            ]
        )
        table_receives = cloud_receive_summary.get("table_receives") or {}
        for row in table_states:
            source_table_name = row.get("source_table_name", "unknown")
            _emit_metric(
                lines,
                "xihong_cloud_sync_table_receive_age_seconds",
                _safe_age_seconds(table_receives.get(source_table_name)),
                labels={"source_table_name": source_table_name},
            )
        lines.extend(
            [
                "# HELP xihong_business_table_stale_hours Hours since latest ingest per business overview table.",
                "# TYPE xihong_business_table_stale_hours gauge",
            ]
        )
        for check in freshness_checks:
            _emit_metric(
                lines,
                "xihong_business_table_stale_hours",
                float(check.get("stale_hours") or -1),
                labels={"table_name": check.get("table_name", "unknown"), "side": check.get("side", "unknown")},
            )

        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    async def build_ready_health_payload(db: Session) -> tuple[dict, int]:
        runtime_mode = str(getattr(app.state, "runtime_mode", "")).strip().lower()
        ready = True
        health_status = {
            "status": "ready",
            "service": "西虹ERP系统API",
            "version": app_version,
            "timestamp": datetime.now().isoformat(),
            "runtime_mode": runtime_mode or "development",
            "deployment_role": os.getenv("DEPLOYMENT_ROLE", "").strip().lower(),
            "checks": {
                "database": {
                    "status": "unknown",
                    "type": "PostgreSQL"
                    if "postgresql" in settings.DATABASE_URL
                    else "SQLite",
                },
                "dashboard": {
                    "status": "unknown",
                },
            },
        }

        try:
            db.execute(text("SELECT 1"))
            health_status["checks"]["database"]["status"] = "connected"
        except Exception as exc:
            health_status["checks"]["database"]["status"] = "error"
            health_status["checks"]["database"]["error"] = str(exc)
            health_status["status"] = "unready"
            ready = False

        if runtime_mode == "collector":
            collector_health = collect_collection_runtime_health(app, settings)
            health_status["runtime_mode"] = collector_health["runtime_mode"]
            health_status["deployment_role"] = collector_health["deployment_role"]
            health_status["checks"]["dashboard"]["status"] = "ignored"
            health_status["checks"].update(collector_health["checks"])
            if collector_health["status"] != "ready":
                health_status["status"] = "unready"
                ready = False
            return health_status, 200 if ready else 503

        try:
            from backend.models.database import AsyncSessionLocal
            from backend.services.data_pipeline.dashboard_bootstrap import (
                inspect_dashboard_assets,
            )

            async with AsyncSessionLocal() as session:
                dashboard_report = await inspect_dashboard_assets(session)
            app.state.dashboard_assets_report = dashboard_report
            app.state.dashboard_assets_ready = bool(dashboard_report.get("ready"))
        except Exception as exc:
            dashboard_report = getattr(app.state, "dashboard_assets_report", None) or {}
            health_status["checks"]["dashboard"]["refresh_error"] = str(exc)
        else:
            dashboard_report = getattr(app.state, "dashboard_assets_report", None) or {}

        dashboard_ready = bool(getattr(app.state, "dashboard_assets_ready", True))
        dashboard_modules = (
            dashboard_report.get("modules")
            if isinstance(dashboard_report, dict)
            else None
        )
        dashboard_has_non_ready_module = isinstance(dashboard_modules, dict) and any(
            module_report.get("status") != "ready"
            for module_report in dashboard_modules.values()
        )
        if dashboard_ready and not dashboard_has_non_ready_module:
            health_status["checks"]["dashboard"]["status"] = "ready"
        else:
            health_status["checks"]["dashboard"]["status"] = "degraded"
            health_status["status"] = "unready"
            ready = False
            if isinstance(dashboard_report, dict) and dashboard_report:
                health_status["checks"]["dashboard"]["details"] = dashboard_report

        return health_status, 200 if ready else 503

    @app.get("/api/healthz/ready", tags=["系统"])
    @app.get("/healthz/ready", tags=["系统"])
    async def ready_health_check(db: Session = Depends(get_db)):
        payload, status_code = await build_ready_health_payload(db)
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/api/health", tags=["系统"])
    @app.get("/health", tags=["系统"])
    async def health_check(db: Session = Depends(get_db)):
        from backend.models.database import engine
        from backend.services.executor_manager import get_executor_manager

        ready_payload, status_code = await build_ready_health_payload(db)
        health_status = {
            "status": "healthy" if status_code == 200 else "unhealthy",
            "service": ready_payload["service"],
            "version": ready_payload["version"],
            "timestamp": ready_payload["timestamp"],
            "database": ready_payload["checks"]["database"],
            "dashboard": ready_payload["checks"]["dashboard"],
            "routes": {
                "total": len(app.routes),
                "endpoints": len([route for route in app.routes if hasattr(route, "path")]),
            },
            "pool": {"size": 0, "checked_out": 0, "overflow": 0},
            "executors": {
                "status": "unknown",
                "cpu_executor": {},
                "io_executor": {},
            },
        }

        try:
            pool = engine.pool
            health_status["pool"]["size"] = pool.size()
            health_status["pool"]["checked_out"] = pool.checkedout()
            health_status["pool"]["overflow"] = pool.overflow()
        except Exception as exc:
            health_status["pool"]["error"] = str(exc)

        try:
            executor_manager = get_executor_manager()
            executor_health = await executor_manager.check_health(timeout=2.0)
            health_status["executors"] = executor_health
            if executor_health["overall_status"] != "healthy":
                health_status["status"] = "unhealthy"
                health_status["executors"]["status"] = executor_health["overall_status"]
            else:
                health_status["executors"]["status"] = "healthy"
        except Exception as exc:
            health_status["executors"] = {
                "status": "error",
                "error": f"执行器健康检查失败: {exc}",
            }

        return health_status

    @app.get("/", tags=["系统"])
    async def root():
        return {
            "message": "欢迎使用西虹ERP系统API",
            "version": "4.0.0",
            "docs": "/api/docs",
            "health": "/health",
            "readiness": "/healthz/ready",
            "liveness": "/healthz/live",
        }
