# 系统管理模块后端API设计文档

> **创建时间**: 2026-01-06  
> **状态**: 📝 设计阶段

## 设计原则

### Contract-First开发原则

所有API开发必须遵循以下顺序：

1. **定义数据模型** → `modules/core/db/schema.py` + Alembic迁移
2. **定义API契约** → `backend/schemas/` 中的Pydantic模型（禁止在routers/定义）
3. **定义路由签名** → `@router` + `response_model`（占位实现，response_model必填）
4. **实现业务逻辑** → 填充路由函数
5. **编写测试** → 验证契约

### 异步架构规范

- ✅ 所有服务类只接受 `AsyncSession`
- ✅ 所有路由函数使用 `get_async_db()` 而不是 `get_db()`
- ✅ 数据库操作必须异步：`await db.execute(select(...))`
- ❌ 禁止在 `async def` 函数中使用 `db.query()`、`db.commit()` 等同步方法

### API响应格式规范

所有API必须遵循统一响应格式：

```python
# 成功响应
{
  "success": true,
  "data": {...},
  "timestamp": "2026-01-06T10:30:00Z"
}

# 错误响应
{
  "success": false,
  "error": {
    "code": 2001,
    "type": "BusinessError",
    "detail": "操作失败",
    "recovery_suggestion": "请检查参数"
  },
  "message": "业务错误：操作失败",
  "timestamp": "2026-01-06T10:30:00Z"
}

# 分页响应
{
  "success": true,
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  },
  "timestamp": "2026-01-06T10:30:00Z"
}
```

使用工具函数：
- `backend/utils/api_response.py` - `success_response()`, `error_response()`, `pagination_response()`

---

## 数据模型设计

### SystemLog（系统日志表）

```python
class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True)
    level = Column(String(10), nullable=False)  # ERROR, WARN, INFO, DEBUG
    module = Column(String(64), nullable=False)  # 模块名称
    message = Column(Text, nullable=False)  # 日志消息
    user_id = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(512), nullable=True)
    details = Column(JSONB, nullable=True)  # 详细信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_system_logs_level", "level"),
        Index("ix_system_logs_module", "module"),
        Index("ix_system_logs_created_at", "created_at"),
        ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], name='fk_system_logs_user_id'),
    )
```

**注意**：系统日志表用于存储应用运行时产生的结构化日志。与现有日志系统的关系：
- **文件日志**：`modules/core/logger.py` 中的日志记录器会同时写入文件日志和数据库日志（如果配置了数据库日志处理器）
- **审计日志**：`FactAuditLog` 表用于记录用户操作审计，与系统日志（应用运行日志）不同
- **任务日志**：`CollectionTaskLog` 表用于记录采集任务日志，与系统日志不同
- **系统日志API**：主要用于查询数据库中的系统日志，文件日志通过服务器日志文件查看

### SecurityConfig（安全配置表）

```python
class SecurityConfig(Base):
    __tablename__ = "security_config"
    
    id = Column(Integer, primary_key=True)
    config_key = Column(String(64), unique=True, nullable=False)  # password_policy, login_restrictions, session_config, 2fa_config
    config_value = Column(JSONB, nullable=False)  # 配置值（JSON格式）
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('config_key', name='uq_security_config_key'),  # 唯一约束
        Index('ix_security_config_key', 'config_key'),  # 索引
        ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], name='fk_security_config_updated_by'),
    )
```

### BackupRecord（备份记录表）

```python
class BackupRecord(Base):
    __tablename__ = "backup_records"
    
    id = Column(Integer, primary_key=True)
    backup_type = Column(String(32), nullable=False)  # full, incremental
    backup_path = Column(String(512), nullable=False)  # 备份文件路径
    backup_size = Column(BIGINT, nullable=False)  # 备份大小（字节）
    checksum = Column(String(64), nullable=True)  # 文件校验和（SHA-256）
    status = Column(String(32), nullable=False)  # pending, completed, failed
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_backup_records_status", "status"),
        Index("ix_backup_records_created_at", "created_at"),
        ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], name='fk_backup_records_created_by'),
    )
```

### SystemConfig（系统配置表）

```python
class SystemConfig(Base):
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True)
    config_key = Column(String(64), unique=True, nullable=False)  # system_name, version, timezone, language, currency
    config_value = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('config_key', name='uq_system_config_key'),  # 唯一约束
        Index('ix_system_config_key', 'config_key'),  # 索引
    )
```

### SMTPConfig（SMTP配置表）

```python
class SMTPConfig(Base):
    __tablename__ = "smtp_config"
    
    id = Column(Integer, primary_key=True)
    smtp_server = Column(String(256), nullable=False)
    smtp_port = Column(Integer, nullable=False)
    use_tls = Column(Boolean, default=True, nullable=False)
    username = Column(String(256), nullable=False)
    password_encrypted = Column(Text, nullable=False)  # 加密存储
    from_email = Column(String(256), nullable=False)
    from_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], name='fk_smtp_config_updated_by'),
    )
```

### NotificationTemplate（通知模板表）

```python
class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    
    id = Column(Integer, primary_key=True)
    template_type = Column(String(64), nullable=False)  # system_notification, alert_notification, approval_notification
    template_name = Column(String(128), nullable=False)
    subject = Column(String(256), nullable=False)  # 邮件主题
    body = Column(Text, nullable=False)  # 模板内容（支持变量替换）
    variables = Column(JSONB, nullable=True)  # 可用变量列表
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        Index("ix_notification_templates_type", "template_type"),
        ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], name='fk_notification_templates_created_by'),
        ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], name='fk_notification_templates_updated_by'),
    )
```

### AlertRule（告警规则表）

```python
class AlertRule(Base):
    __tablename__ = "alert_rules"
    
    id = Column(Integer, primary_key=True)
    rule_name = Column(String(128), nullable=False)
    alert_level = Column(String(32), nullable=False)  # critical, warning, info
    condition = Column(JSONB, nullable=False)  # 告警条件（JSON格式）
    notification_methods = Column(JSONB, nullable=False)  # ["email", "sms", "in_app"]
    notification_targets = Column(JSONB, nullable=False)  # 通知对象（用户ID或角色）
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("dim_users.user_id"), nullable=True)
    
    __table_args__ = (
        Index("ix_alert_rules_level", "alert_level"),
        Index("ix_alert_rules_active", "is_active"),
        ForeignKeyConstraint(['created_by'], ['dim_users.user_id'], name='fk_alert_rules_created_by'),
        ForeignKeyConstraint(['updated_by'], ['dim_users.user_id'], name='fk_alert_rules_updated_by'),
    )
```

---

## API设计规范

### 路由命名规范

- 使用名词复数：`/api/system/logs`（而非 `/api/system/log`）
- **统一使用连字符（kebab-case）**：`/api/system/backup-records`、`/api/system/ip-whitelist`
- ❌ **禁止使用下划线**：不要使用 `/api/system/backup_records`
- 避免动词：URL中不使用动词（动词由HTTP方法表达）

**示例**：
```python
# ✅ 正确：使用连字符
@router.get("/api/system/backup-records")
@router.post("/api/system/ip-whitelist")
@router.delete("/api/system/ip-whitelist/{ip}")

# ❌ 错误：使用下划线
@router.get("/api/system/backup_records")
@router.post("/api/system/ip_whitelist")
```

### HTTP方法规范

- `GET` - 查询资源（幂等，不修改数据）
- `POST` - 创建资源（非幂等）
- `PUT` - 更新资源（幂等，完整更新）
- `PATCH` - 部分更新资源（幂等，部分更新）
- `DELETE` - 删除资源（幂等）

### 权限控制

所有系统管理API需要管理员权限：

**重要**：必须使用现有的 `require_admin` 依赖，不要重新定义。

```python
# ✅ 正确：从现有模块导入
from backend.routers.users import require_admin

@router.get("/api/system/logs")
async def get_system_logs(
    current_user: DimUser = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db)
):
    # ...

# ❌ 错误：重新定义（会导致不一致）
async def require_admin(current_user: DimUser = Depends(get_current_user)):
    # ...
```

**现有实现位置**：`backend/routers/users.py` 第42-60行

### 分页规范

所有列表查询API必须支持分页：

```python
@router.get("/api/system/logs")
async def get_system_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    # ... 其他筛选参数
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)
):
    offset = (page - 1) * page_size
    # ... 查询逻辑
    return pagination_response(
        data=logs,
        page=page,
        page_size=page_size,
        total=total
    )
```

### 限流配置

所有系统管理API必须添加限流配置，防止滥用：

```python
from backend.middleware.rate_limiter import role_based_rate_limit

# 数据备份API：每小时最多5次
@router.post("/api/system/backup")
@role_based_rate_limit("admin", "backup", limit=5, period=3600)
async def create_backup(...):
    pass

# 日志导出API：每小时最多10次
@router.post("/api/system/logs/export")
@role_based_rate_limit("admin", "export", limit=10, period=3600)
async def export_logs(...):
    pass

# 缓存清理API：每小时最多20次
@router.post("/api/system/maintenance/cache/clear")
@role_based_rate_limit("admin", "maintenance", limit=20, period=3600)
async def clear_cache(...):
    pass
```

**限流策略**：
- 数据备份/恢复：每小时最多5次
- 日志导出：每小时最多10次
- 缓存清理：每小时最多20次
- 配置更新：每小时最多30次
- 查询操作：每分钟最多60次

---

## 安全设计

### 数据备份恢复安全

数据恢复API必须多重安全防护（**所有检查必须全部通过**，适用于生产环境）：

1. **维护窗口检查**：仅在维护窗口内执行（可配置，默认：凌晨2-4点）
   - 检查当前时间是否在维护窗口内
   - 如果不在维护窗口，需要管理员明确确认（`RestoreRequest.force_outside_window == True`）
2. **管理员权限**：仅管理员可执行（使用 `require_admin` 依赖）
3. **多重确认**：需要至少2名管理员确认（`RestoreRequest.confirmed_by` 数组包含2个不同的管理员ID）
4. **交互确认**：需要二次确认（`RestoreRequest.confirmed == True`）
5. **备份文件完整性验证**：验证备份文件存在性和校验和（SHA-256）
6. **恢复前自动备份**：执行恢复前自动创建紧急备份
7. **超时控制**：恢复操作最多1小时超时
8. **操作通知**：恢复前后发送通知给所有管理员
9. **审计日志**：所有恢复操作记录到审计日志（包含恢复前后状态对比）

```python
@router.post("/api/system/backup/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    restore_request: RestoreRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: DimUser = Depends(require_admin)
):
    import asyncio
    from pathlib import Path
    import hashlib
    
    # 1. 维护窗口检查（允许生产环境，但需要维护窗口或强制确认）
    from datetime import datetime, time
    current_time = datetime.now().time()
    maintenance_window_start = time(2, 0)  # 凌晨2点
    maintenance_window_end = time(4, 0)    # 凌晨4点
    
    in_maintenance_window = maintenance_window_start <= current_time <= maintenance_window_end
    
    if not in_maintenance_window and not restore_request.force_outside_window:
        raise HTTPException(
            status_code=403,
            detail="恢复操作应在维护窗口内执行（凌晨2-4点），或需要强制确认"
        )
    
    # 2. 多重管理员确认（至少2名管理员）
    if len(restore_request.confirmed_by) < 2:
        raise HTTPException(
            status_code=400,
            detail="需要至少2名管理员确认才能执行恢复操作"
        )
    
    # 验证两个管理员ID不同且都有管理员权限
    admin_ids = set(restore_request.confirmed_by)
    if len(admin_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="需要2个不同的管理员确认"
        )
    
    # 验证管理员权限（查询数据库验证）
    from sqlalchemy import select
    from modules.core.db import DimUser
    
    for admin_id in admin_ids:
        result = await db.execute(
            select(DimUser).where(DimUser.user_id == admin_id)
        )
        admin_user = result.scalar_one_or_none()
        if not admin_user:
            raise HTTPException(
                status_code=404,
                detail=f"管理员 {admin_id} 不存在"
            )
        
        # 检查是否为管理员（使用现有的require_admin逻辑）
        is_admin = admin_user.is_superuser or any(
            (hasattr(role, "role_code") and role.role_code == "admin") or
            (hasattr(role, "role_name") and role.role_name == "admin")
            for role in admin_user.roles
        )
        if not is_admin:
        raise HTTPException(
            status_code=403,
                detail=f"用户 {admin_id} 不是管理员"
        )
    
    # 3. 二次确认
    if not restore_request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="需要确认才能执行恢复操作"
        )
    
    # 3. 获取备份记录
    result = await db.execute(
        select(BackupRecord).where(BackupRecord.id == backup_id)
    )
    backup_record = result.scalar_one_or_none()
    if not backup_record:
        raise HTTPException(status_code=404, detail="备份记录不存在")
    
    # 4. 备份文件完整性验证
    backup_file = Path(backup_record.backup_path)
    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    
    # 验证校验和（如果存在）
    if backup_record.checksum:
        actual_checksum = calculate_file_checksum(backup_file)
        if actual_checksum != backup_record.checksum:
            raise HTTPException(
                status_code=400,
                detail="备份文件已损坏（校验和不匹配）"
            )
    
    # 5. 恢复前自动备份
    emergency_backup = await create_emergency_backup(db, current_user)
    logger.warning(f"恢复前已创建紧急备份: {emergency_backup.id}")
    
    # 6. 执行恢复（带超时控制）
    try:
        await asyncio.wait_for(
            execute_restore(backup_id, backup_file),
            timeout=3600  # 1小时超时
        )
    except asyncio.TimeoutError:
        # 恢复超时，尝试回滚到紧急备份
        await rollback_to_backup(emergency_backup.id, db)
        raise HTTPException(
            status_code=500,
            detail="恢复操作超时，已回滚到恢复前状态"
        )
    
    # 7. 记录审计日志
    await audit_service.log_action(
        user_id=current_user.user_id,
        action="restore_backup",
        resource="backup",
        resource_id=str(backup_id),
        details={
            "backup_path": str(backup_file),
            "emergency_backup_id": emergency_backup.id,
            "restore_status": "completed"
        }
    )
    
    return success_response(
        data={"backup_id": backup_id, "status": "completed"},
        message="恢复操作已完成"
    )
```

### 敏感数据加密

所有敏感数据必须加密存储：

1. **SMTP密码**：使用 `EncryptionService` 加密存储
2. **数据库配置密码**：使用 `EncryptionService` 加密存储
3. **加密字段**：所有密码、密钥、令牌等敏感字段必须加密
4. **加密算法**：使用 AES-256-GCM（对称加密）
5. **密钥管理**：使用 `EncryptionService` 统一管理加密密钥

```python
from backend.services.encryption_service import get_encryption_service

# 加密存储
encryption_service = get_encryption_service()
encrypted_password = encryption_service.encrypt_password(plain_password)

# 解密使用
decrypted_password = encryption_service.decrypt_password(encrypted_password)
```

**数据模型示例**：
```python
class SMTPConfig(Base):
    # ...
    password_encrypted = Column(Text, nullable=False)  # 加密存储，不要存储明文

class DatabaseConfig(Base):
    # ...
    password_encrypted = Column(Text, nullable=False)  # 加密存储
```

---

## 性能设计

### 日志查询优化

- 使用索引：`level`、`module`、`created_at`
- 分页查询：避免一次性加载所有日志
- 时间范围限制：默认查询最近30天

### 缓存策略

- 系统配置：缓存到Redis（5分钟TTL）
- 安全配置：缓存到Redis（10分钟TTL）
- 配置更新时自动失效缓存

---

## 输入验证

### Pydantic模型验证

所有API请求模型必须包含输入验证：

```python
from pydantic import BaseModel, Field, validator
import ipaddress

class IPWhitelistUpdate(BaseModel):
    ip: str = Field(..., description="IP地址或CIDR")
    
    @validator('ip')
    def validate_ip(cls, v):
        """验证IP地址格式"""
        try:
            # 尝试解析为IP地址
            ipaddress.ip_address(v)
        except ValueError:
            try:
                # 尝试解析为CIDR
                ipaddress.ip_network(v, strict=False)
            except ValueError:
                raise ValueError("Invalid IP address or CIDR format")
        return v

class PasswordPolicyUpdate(BaseModel):
    min_length: int = Field(8, ge=8, le=128, description="最小长度")
    require_uppercase: bool = Field(True, description="需要大写字母")
    require_lowercase: bool = Field(True, description="需要小写字母")
    require_digits: bool = Field(True, description="需要数字")
    require_special_chars: bool = Field(True, description="需要特殊字符")
    max_age_days: int = Field(90, ge=30, le=365, description="密码最大有效期（天）")
    
    @validator('min_length')
    def validate_min_length(cls, v):
        if v < 8:
            raise ValueError("密码最小长度不能少于8个字符")
        return v
```

### 验证规则

- **IP地址**：使用 `ipaddress` 模块验证
- **邮箱地址**：使用 `email-validator` 或正则表达式验证
- **URL**：使用 `validators` 库验证
- **数值范围**：使用 Pydantic 的 `ge`、`le` 约束
- **字符串长度**：使用 `min_length`、`max_length` 约束

## 错误处理

### 统一错误码

使用 `backend/utils/error_codes.py` 中定义的错误码：

- `1xxx` - 系统错误
- `2xxx` - 业务错误
- `3xxx` - 数据错误
- `4xxx` - 用户错误

### 错误响应格式

```python
return error_response(
    code=ErrorCode.DATA_VALIDATION_FAILED,
    message="数据验证失败",
    error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
    detail="具体错误信息",
    recovery_suggestion="建议操作",
    status_code=400
)
```

---

## 测试要求

### 单元测试

每个API端点必须有单元测试：

```python
@pytest.mark.asyncio
async def test_get_system_logs():
    # Arrange
    # Act
    # Assert
    pass
```

### 集成测试

关键功能（如数据备份恢复）必须有集成测试。

---

**最后更新**: 2026-01-06  
**维护**: AI Agent Team  
**状态**: 📝 设计阶段

