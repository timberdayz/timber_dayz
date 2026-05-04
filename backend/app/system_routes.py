from datetime import datetime

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session


def register_system_routes(app, settings, app_version, get_db):
    @app.get("/api/health", tags=["系统"])
    @app.get("/health", tags=["系统"])
    async def health_check(db: Session = Depends(get_db)):
        from backend.models.database import engine
        from backend.services.executor_manager import get_executor_manager

        health_status = {
            "status": "healthy",
            "service": "西虹ERP系统API",
            "version": app_version,
            "timestamp": datetime.now().isoformat(),
            "database": {
                "status": "unknown",
                "type": "PostgreSQL" if "postgresql" in settings.DATABASE_URL else "SQLite",
            },
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
            db.execute(text("SELECT 1"))
            health_status["database"]["status"] = "connected"
        except Exception as exc:
            health_status["database"]["status"] = "error"
            health_status["database"]["error"] = str(exc)
            health_status["status"] = "unhealthy"

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
                "error": f"执行器健康检查失败: {str(exc)}",
            }

        return health_status

    @app.get("/", tags=["系统"])
    async def root():
        return {
            "message": "欢迎使用西虹ERP系统API",
            "version": "4.0.0",
            "docs": "/api/docs",
            "health": "/health",
        }

