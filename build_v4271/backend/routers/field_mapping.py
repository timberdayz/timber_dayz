"""
字段映射API路由 - 西虹ERP系统

薄包装层: 聚合 field_mapping_files / field_mapping_ingest / field_mapping_status 三个子模块的路由。
main.py 仍然通过 field_mapping.router 注册,无需修改。
"""

from fastapi import APIRouter

from backend.routers.field_mapping_files import router as files_router
from backend.routers.field_mapping_ingest import router as ingest_router
from backend.routers.field_mapping_status import router as status_router

router = APIRouter()

router.include_router(files_router)
router.include_router(ingest_router)
router.include_router(status_router)
