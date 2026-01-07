"""
用户权限数据模型（v4.12.0 SSOT迁移）

v4.12.0更新：
- 所有表定义已迁移到 modules/core/db/schema.py（SSOT合规性）
- 本文件仅作为向后兼容的导入接口
- 所有代码应直接从 modules.core.db 导入

向后兼容导入：
- from backend.models.users import DimUser, DimRole, FactAuditLog
- 等同于：from modules.core.db import DimUser, DimRole, FactAuditLog
"""

# v4.12.0 SSOT迁移：从schema.py导入，不再重复定义
from modules.core.db import (
    DimUser,
    DimRole,
    FactAuditLog,
    user_roles,
)

# 向后兼容导出
__all__ = [
    "DimUser",
    "DimRole",
    "FactAuditLog",
    "user_roles",
]

