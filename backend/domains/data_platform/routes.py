from backend.routers import (
    auto_ingest,
    cloud_sync as cloud_sync_router,
    data_migration,
    data_pipeline,
    data_quality,
    data_quarantine,
    data_sync,
    data_sync_mapping_quality,
    field_mapping,
    field_mapping_dictionary,
    field_mapping_templates,
    management,
    refresh_queue,
)


def register_data_platform_routes(app, logger) -> None:
    app.include_router(management.router, prefix="/api/management", tags=["数据管理"])
    app.include_router(field_mapping.router, prefix="/api/field-mapping", tags=["字段映射"])
    app.include_router(
        field_mapping_dictionary.router, prefix="/api/field-mapping", tags=["字段映射词典"]
    )
    app.include_router(
        field_mapping_templates.router, prefix="/api/field-mapping", tags=["字段映射模板"]
    )
    app.include_router(data_sync.router, prefix="/api", tags=["数据同步"])
    app.include_router(data_sync_mapping_quality.router, prefix="/api", tags=["数据同步"])
    app.include_router(data_pipeline.router, tags=["数据管道"])
    app.include_router(
        auto_ingest.router,
        prefix="/api/field-mapping",
        tags=["数据治理统计"],
    )
    app.include_router(refresh_queue.router, prefix="/api")
    app.include_router(data_quarantine.router, prefix="/api", tags=["数据隔离区"])
    app.include_router(data_quality.router, prefix="/api", tags=["数据质量监控"])
    app.include_router(data_migration.router, prefix="/api", tags=["数据迁移"])
    app.include_router(cloud_sync_router.router, tags=["云端同步管理"])
