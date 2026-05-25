from datetime import datetime

from fastapi import Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session


def register_system_routes(app, settings, app_version, get_db):
    @app.get("/api/healthz/live", tags=["系统"])
    @app.get("/healthz/live", tags=["系统"])
    async def live_health_check():
        return {
            "status": "alive",
            "service": "西虹ERP系统API",
            "version": app_version,
            "timestamp": datetime.now().isoformat(),
        }

    async def build_ready_health_payload(db: Session) -> tuple[dict, int]:
        ready = True
        health_status = {
            "status": "ready",
            "service": "西虹ERP系统API",
            "version": app_version,
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": {
                    "status": "unknown",
                    "type": "PostgreSQL" if "postgresql" in settings.DATABASE_URL else "SQLite",
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

        dashboard_ready = bool(getattr(app.state, "dashboard_assets_ready", True))
        dashboard_report = getattr(app.state, "dashboard_assets_report", None) or {}
        dashboard_modules = dashboard_report.get("modules") if isinstance(dashboard_report, dict) else None
        dashboard_has_non_ready_module = isinstance(dashboard_modules, dict) and any(
            module_report.get("status") != "ready" for module_report in dashboard_modules.values()
        )
        if dashboard_ready and not dashboard_has_non_ready_module:
            health_status["checks"]["dashboard"]["status"] = "ready"
        else:
            health_status["checks"]["dashboard"]["status"] = "degraded"
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
