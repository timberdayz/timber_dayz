## Why

`refactor-rules-and-code-patterns` 提案聚焦 Agent-first 开发治理，覆盖了规则分层、代码模式标准化、异常体系、测试底座和高风险重构风控。该提案落地后，Agent 开发效率和代码一致性将显著提升。

但对于一个面向 50~100 人同时使用的现代化跨境电商 ERP 系统，仅有开发治理仍不足以支撑长期稳定运行。经审视，当前体系存在六个生产级缺口：

1. **性能与容量**：没有关键 API 的延迟目标、连接池容量基线和压测通过标准
2. **发布与回滚**：没有迁移预演流程、灰度发布规则和回滚模板
3. **灾备与恢复**：没有 RPO/RTO 目标、恢复演练频率和恢复验证脚本
4. **数据治理与敏感访问**：HR/薪资/绩效等敏感数据缺少分级、脱敏、导出审批和审计保留规则
5. **前端 Agent 规则**：后端已有 `CODE_PATTERNS.md`，前端 API/Store/View 层仍缺少等效模板
6. **ERP 业务验收**：金额精度、时间口径、对账规则等业务正确性标准尚未建立

本次变更聚焦生产级治理补强，使项目从"可规范开发"升级为"可稳定运行、可安全发布、可恢复、可审计"。

## What Changes

### 生产运行治理
- 定义关键 API 的 p95/p99 延迟 SLO、页面加载目标、后台任务时限
- 定义数据库连接池、Redis、Celery worker、任务队列积压阈值
- 引入压测门禁：高风险变更上线前必须执行压测并产出报告

### 发布与回滚治理
- 定义数据库迁移预演流程（staging 预跑、幂等验证、回滚演练）
- 定义灰度/分批发布规则和 feature flag 使用标准
- 定义回滚策略：代码回滚、迁移回滚、数据补救分层处理

### 灾备与数据治理
- 定义 RPO/RTO 目标和备份频率
- 定义恢复演练频率和通过标准
- 定义数据四级分级：public / internal / sensitive / restricted
- 定义敏感数据访问规则：查看/导出/审计要求

### 前端 Agent 规则
- 创建前端 `FRONTEND_CODE_PATTERNS.md`：API 层、Pinia store、列表页、表单页模板
- 统一错误处理、局部 loading、后台刷新、权限控制模式
- 禁止页面直接拼接请求和重复状态逻辑

### ERP 业务验收标准
- 定义金额精度与舍入规则（CNY 2 位小数、百分比统一除以 100）
- 定义时间口径：时区、自然月、财务月、数据归属周期
- 为收入/绩效/目标模块建立 acceptance checklist

## Capabilities

### New Capabilities
- `performance-and-capacity`: 性能 SLO、容量基线、压测门禁
- `release-and-rollback`: 发布流程、迁移预演、回滚策略、feature flag
- `backup-and-disaster-recovery`: RPO/RTO、备份策略、恢复演练
- `data-governance-and-sensitive-access`: 数据分级、敏感访问控制、审计保留
- `frontend-agent-patterns`: 前端 Agent 开发模板和约束
- `erp-business-acceptance`: ERP 业务正确性验收标准

### Modified Capabilities
_(无现有 spec 的行为需求发生变更。本次变更补充生产治理，不改变任何面向用户的功能行为。)_

## Impact
- **受影响的规则文件**: `.cursorrules`（增加生产治理入口指针和前端强制规则，预计新增 ~10 行，需确保 V1 精简后仍有余量保持总行数 <= 310 行）、`docs/DEVELOPMENT_RULES/`（新增3个文件、更新 README 索引）
- **受影响的流程**: 发布流程、迁移流程、验收流程、压测流程、备份恢复流程
- **新增文档**: `PRODUCTION_READINESS.md`、`DATA_GOVERNANCE.md`、`FRONTEND_CODE_PATTERNS.md`
- **新增脚本**: 压测脚本（k6/Locust）、恢复验证脚本
- **依赖变更**: 新增 `k6` 或 `locust`（仅 dev/ops 依赖）
- **与 V1 提案的关系**: 本提案是 `refactor-rules-and-code-patterns`（Agent 开发治理 V1）的后续补强。V2 的 spec 可先行评审，但文档结构和规则入口的实际落地应排在 V1 完成 L3 文档结构重构之后。V1 解决"怎么写代码"，V2 解决"怎么上线和运行"

