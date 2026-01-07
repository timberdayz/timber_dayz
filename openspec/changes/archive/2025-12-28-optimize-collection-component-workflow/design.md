# Design: 优化数据采集组件工作流

## Context

数据采集模块是西虹ERP系统的核心功能之一，负责从多个电商平台（Shopee、TikTok、妙手ERP等）自动采集数据。当前架构采用组件驱动设计（YAML配置），已完成Phase 1-8的代码实现，但缺乏系统性的验证机制。

**相关利益方**：
- 运营人员：需要稳定可靠的数据采集
- 开发人员：需要清晰的验证指标和调试工具
- 系统管理员：需要监控和告警能力

**技术约束**：
- 必须使用Playwright进行浏览器自动化
- 必须支持Windows和Linux平台
- 必须遵循Contract-First开发规范

## Goals / Non-Goals

### Goals
- ✅ 建立组件录制的质量验证标准
- ✅ 实现手动采集的端到端验证
- ✅ 增强定时采集的可靠性和监控
- ✅ 提供组件质量评估工具

### Non-Goals
- ❌ 添加新的数据采集平台
- ❌ 重构现有的组件驱动架构
- ❌ 实现AI驱动的选择器自动修复
- ❌ 修改数据库表结构

## Decisions

### 决策1: 组件验证采用三层验证架构

**选择**：静态验证 + 干运行验证 + 实际运行验证

**原因**：
- 静态验证（YAML解析）速度快，可在保存时立即执行
- 干运行验证（无浏览器）检查逻辑完整性
- 实际运行验证（有浏览器）确保真实可用性

**替代方案**：
- 仅静态验证：无法检测运行时问题
- 仅实际验证：验证成本高，反馈周期长

### 决策2: 采集状态监控采用轮询+日志模式

**选择**：HTTP轮询获取进度 + 结构化日志记录

**原因**：
- WebSocket在生产环境（特别是负载均衡后）可能不稳定
- HTTP轮询更简单可靠，与现有架构一致
- 结构化日志便于问题排查和审计

**替代方案**：
- WebSocket实时推送：实现复杂，生产环境易出问题
- Server-Sent Events：浏览器兼容性问题

### 决策3: 定时任务使用APScheduler + 数据库持久化

**选择**：继续使用APScheduler，增加数据库任务记录

**原因**：
- APScheduler已集成，运行稳定
- 数据库记录支持任务审计和恢复
- 与现有架构一致

**替代方案**：
- Celery Beat：额外依赖，部署复杂度增加
- 系统cron：无法与应用状态联动

## Technical Design

### 组件验证服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                   ComponentValidator                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐│
│  │ Static Validator│  │DryRun Validator │  │Live Validator││
│  │                 │  │                 │  │              ││
│  │ - YAML语法      │  │ - 步骤逻辑      │  │ - 选择器有效 ││
│  │ - 必需字段      │  │ - 条件分支      │  │ - 操作可执行 ││
│  │ - 选择器格式    │  │ - 超时配置      │  │ - 成功标准   ││
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘│
│           │                    │                   │        │
│           └────────────────────┼───────────────────┘        │
│                                ▼                            │
│                    ┌─────────────────────┐                  │
│                    │ ValidationReport    │                  │
│                    │ - passed: bool      │                  │
│                    │ - errors: List      │                  │
│                    │ - warnings: List    │                  │
│                    │ - metrics: Dict     │                  │
│                    └─────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 采集流程监控架构

```
┌──────────────────────────────────────────────────────────────┐
│                  Collection Monitoring                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  前端触发                                                     │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────┐                                         │
│  │ 创建采集任务    │──▶ collection_tasks表 (status=pending)  │
│  └────────┬────────┘                                         │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │ 执行器V2       │──▶ 更新状态 (status=running)            │
│  │ (executor_v2)  │                                          │
│  └────────┬────────┘                                         │
│           │                                                  │
│           ├──▶ 组件执行日志 (component_logs)                 │
│           ├──▶ 步骤进度更新 (WebSocket/轮询)                 │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │ 文件下载完成   │──▶ catalog_files表 (status=pending)      │
│  └────────┬────────┘                                         │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │ 任务完成       │──▶ 更新状态 (status=completed/failed)    │
│  └─────────────────┘                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 定时任务监控架构

```
┌──────────────────────────────────────────────────────────────┐
│               Scheduled Collection Monitoring                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  APScheduler                                                 │
│      │                                                       │
│      ├──▶ 触发时记录 (scheduled_task_logs表)                 │
│      │    - trigger_time                                     │
│      │    - job_id                                           │
│      │    - config_id                                        │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────┐                                         │
│  │ 检查任务冲突   │                                          │
│  │ - 相同配置运行中?│                                         │
│  │ - 资源是否足够? │                                          │
│  └────────┬────────┘                                         │
│           │                                                  │
│           ├── 有冲突 ──▶ 延迟执行/跳过 + 记录日志            │
│           │                                                  │
│           └── 无冲突 ──▶ 创建采集任务                        │
│                          │                                   │
│                          ▼                                   │
│                    ┌─────────────────┐                       │
│                    │ 任务执行       │                        │
│                    └────────┬────────┘                       │
│                             │                                │
│                             ├── 成功 ──▶ 更新下次执行时间    │
│                             │                                │
│                             └── 失败 ──▶ 重试机制(最多3次)   │
│                                          │                   │
│                                          └──▶ 告警通知       │
└──────────────────────────────────────────────────────────────┘
```

### API设计

#### 组件验证API

```python
# POST /api/component-recorder/validate
# 请求体
class ComponentValidateRequest(BaseModel):
    platform: str
    component_name: str
    validation_level: Literal["static", "dryrun", "live"] = "static"
    account_id: Optional[str] = None  # live验证需要

# 响应体
class ComponentValidateResponse(BaseModel):
    passed: bool
    validation_level: str
    errors: List[ValidationError]
    warnings: List[ValidationWarning]
    metrics: ValidationMetrics

class ValidationError(BaseModel):
    code: str
    message: str
    location: Optional[str] = None  # 如 "steps[2].selector"

class ValidationMetrics(BaseModel):
    total_steps: int
    valid_selectors: int
    has_success_criteria: bool
    estimated_duration_ms: Optional[int] = None
```

#### 采集统计API

```python
# GET /api/collection/statistics
# 响应体
class CollectionStatisticsResponse(BaseModel):
    period: str  # "today", "week", "month"
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    success_rate: float
    average_duration_ms: int
    files_collected: int
    by_platform: Dict[str, PlatformStatistics]

class PlatformStatistics(BaseModel):
    platform: str
    total_tasks: int
    success_rate: float
    average_duration_ms: int
```

## Risks / Trade-offs

### 风险1: 组件验证可能产生误报

**风险描述**：静态验证可能标记正确的选择器为无效

**缓解措施**：
- 验证规则可配置，允许跳过特定检查
- 区分错误和警告，仅错误阻止保存

### 风险2: 定时任务在系统重启后可能丢失

**风险描述**：APScheduler内存存储在重启后丢失任务状态

**缓解措施**：
- 使用数据库持久化任务配置
- 启动时从数据库恢复未完成任务
- 定期检查任务健康状态

### 风险3: 采集监控增加系统负载

**风险描述**：频繁的状态更新和日志记录可能影响性能

**缓解措施**：
- 状态更新批量提交
- 日志异步写入
- 监控数据定期清理

## Migration Plan

本变更不涉及数据迁移，属于功能增强。

**部署步骤**：
1. 部署新的验证服务（backend/services/component_validator.py）
2. 部署更新的API端点
3. 运行验证脚本确认功能正常
4. 更新前端集成验证功能

**回滚计划**：
- 验证API独立于核心采集功能，可单独回滚
- 保留旧的组件测试工具作为备份

## Open Questions

1. **组件版本管理粒度**：是按commit管理还是手动标记版本？
   - 当前倾向：手动标记版本，与组件内容hash结合
   
2. **验证指标阈值是否需要可配置**：不同平台是否需要不同的成功率阈值？
   - 当前倾向：全局阈值 + 平台级覆盖

3. **定时任务失败告警方式**：邮件/Webhook/应用内通知？
   - 当前倾向：应用内通知 + 可选Webhook

