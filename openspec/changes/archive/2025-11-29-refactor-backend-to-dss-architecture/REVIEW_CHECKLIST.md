# 提案审查清单 - 漏洞检查

## ✅ 已完成的检查项

### 1. OpenSpec合规性
- ✅ 通过`openspec validate --strict`验证
- ✅ 所有spec文件包含必需的delta操作（ADDED/MODIFIED/REMOVED）
- ✅ 所有requirement都有至少一个scenario
- ✅ 文件结构符合OpenSpec标准

### 2. 与对话历史的一致性
- ✅ 覆盖了用户提出的核心问题（字段映射复杂、数据流混乱）
- ✅ 采纳了用户的选择（Vue嵌入Superset、CRUD界面、物化视图策略B）
- ✅ 回答了用户关于现有表是否修改的问题（零删除策略）
- ✅ 整合了A+B+C类数据的处理逻辑

### 3. 技术栈一致性
- ✅ PostgreSQL 15+ - 主数据库
- ✅ Apache Superset 3.0+ - 新增BI层
- ✅ FastAPI - 后端API（简化）
- ✅ Vue.js 3 + Element Plus - 前端（保留）
- ✅ Docker + Docker Compose - 容器化部署

### 4. 架构完整性
- ✅ 三层视图架构（Atomic/Aggregate/Wide）
- ✅ ETL-focused后端架构
- ✅ BI层集成（Superset）
- ✅ 前端嵌入策略
- ✅ A类数据管理CRUD界面

---

## ⚠️ 发现的漏洞和遗漏

### 漏洞1：缺少frontend-api-contracts规格变更 ⚠️
**问题**: proposal.md提到"frontend-api-contracts (修改规格)"，但没有创建对应的spec文件

**影响**: 前端API契约变更不明确

**建议修复**:
```bash
创建文件：openspec/changes/refactor-backend-to-dss-architecture/specs/frontend-api-contracts/spec.md
包含内容：
- MODIFIED: 简化的字段映射API契约
- ADDED: A类数据管理API契约（目标/战役/成本）
- ADDED: Superset代理API契约
- ADDED: 物化视图刷新API契约
```

### 漏洞2：缺少dashboard规格变更 ⚠️
**问题**: proposal.md提到"dashboard (修改规格)"，但没有创建对应的spec文件

**影响**: 前端Dashboard集成Superset的规格不明确

**建议修复**:
```bash
创建文件：openspec/changes/refactor-backend-to-dss-architecture/specs/dashboard/spec.md
包含内容：
- MODIFIED: 业务概览页面（集成Superset图表）
- ADDED: SupersetChart.vue组件规格
- ADDED: 图表降级策略
```

### 漏洞3：字段映射系统简化细节不足 ⚠️
**问题**: 提案提到"简化字段映射系统"，但具体简化哪些部分不够明确

**影响**: 开发人员不清楚哪些代码可以删除

**建议修复**:
在backend-architecture/spec.md的REMOVED部分添加：
- 删除多余的验证函数（enhanced_data_validator.py中的派生字段验证）
- 删除冗余的文件读取逻辑
- 简化preview API（移除KPI计算）

### 漏洞4：Superset用户认证集成细节缺失 🔴
**问题**: 只提到JWT认证集成，但没有详细的实现方案

**影响**: 安全性设计不完整，实施时可能遇到认证问题

**建议修复**:
在bi-layer/spec.md添加新的requirement：
```markdown
### Requirement: User Authentication Integration
Superset SHALL integrate with existing ERP user authentication system.

#### Scenario: SSO login via JWT
- WHEN user logs into ERP frontend
- THEN frontend SHALL obtain JWT token from ERP backend
- AND SHALL use token to generate Superset guest token
- AND Superset SHALL validate JWT signature

#### Scenario: User role mapping
- WHEN Superset guest token is generated
- THEN system SHALL map ERP roles to Superset roles:
  - Admin → Superset Admin
  - Manager → Superset Analyst
  - Operator → Superset Viewer
```

### 漏洞5：数据权限控制实现不够具体 🔴
**问题**: 提到Row Level Security（RLS），但没有详细的配置和实施方案

**影响**: 不同用户可能看到不应该访问的数据

**建议修复**:
在bi-layer/spec.md的RLS部分补充：
```markdown
#### Scenario: RLS configuration per dataset
- WHEN dataset is created in Superset
- THEN admin SHALL configure RLS filter:
  - view_shop_performance_wide: `shop_id IN (SELECT shop_id FROM user_shop_access WHERE user_id = {{ current_user_id() }})`
  - view_orders_atomic: `shop_id IN (...)`
  
#### Scenario: RLS filter caching
- WHEN user accesses dashboard
- THEN Superset SHALL cache RLS filter for session
- AND SHALL refresh when user permissions change
```

### 漏洞6：物化视图刷新失败处理不完整 ⚠️
**问题**: 提到刷新失败会发送告警，但没有具体的失败恢复机制

**影响**: 刷新失败后可能导致数据不一致

**建议修复**:
在database-design/spec.md添加：
```markdown
#### Scenario: Refresh failure recovery
- WHEN materialized view refresh fails
- THEN system SHALL:
  - Log error to mv_refresh_log with error details
  - Send alert to admin (email/Slack)
  - Retry after 1 hour (max 3 retries)
  - If all retries fail, mark view as stale
  - Display "Data may be outdated" warning in frontend
```

### 漏洞7：性能降级策略不够详细 ⚠️
**问题**: 提到"降级策略"，但没有具体的实现方案

**影响**: Superset服务异常时用户体验下降

**建议修复**:
在dashboard规格中添加：
```markdown
#### Scenario: Superset service unavailable
- WHEN Superset health check fails (3 consecutive failures)
- THEN frontend SHALL:
  - Switch to fallback mode (static charts using ECharts)
  - Display warning banner: "图表服务暂时不可用，显示缓存数据"
  - Use last cached data from localStorage
  - Retry Superset connection every 30 seconds
  - Auto-restore when Superset is available
```

### 漏洞8：数据一致性验证机制缺失 ⚠️
**问题**: 提到"零数据丢失"，但没有验证机制

**影响**: 无法确保迁移后数据100%一致

**建议修复**:
在tasks.md的Phase 1验收部分添加：
```markdown
- [ ] 1.9.5 数据一致性验证脚本：
  - 对比视图查询结果与直接表查询结果（抽样10000行）
  - 验证聚合指标一致性（sum, count, avg）
  - 验证时间维度计算正确性
  - 生成一致性验证报告（期望：100%匹配）
```

### 漏洞9：A类数据历史版本管理缺失 ⚠️
**问题**: 用户可以编辑目标和成本，但没有版本控制

**影响**: 无法追溯历史修改，审计困难

**建议修复**:
在backend-architecture/spec.md添加：
```markdown
### Requirement: A-Class Data Versioning
A-class data modifications SHALL be versioned for audit trail.

#### Scenario: Target modification with history
- WHEN user updates sales target
- THEN system SHALL:
  - Create new version record in sales_targets_history table
  - Copy old values with version number (auto-increment)
  - Set modified_by, modified_at timestamps
  - Keep current version in sales_targets table

#### Scenario: View historical versions
- WHEN admin views target history
- THEN system SHALL display:
  - All versions sorted by version number descending
  - What changed (diff between versions)
  - Who changed and when
```

### 漏洞10：成本分摊逻辑未考虑 ⚠️
**问题**: 提到"经营成本配置"，但没有说明成本如何分摊到每日/每SKU

**影响**: view_shop_performance_wide的成本计算可能不准确

**建议修复**:
在database-design/spec.md的view_shop_performance_wide部分明确：
```sql
-- 成本按30天均摊（简化版）
rent_cost / 30 AS daily_rent_cost

-- 或者按实际天数均摊（精确版）
rent_cost / DATE_PART('day', DATE_TRUNC('month', sale_date) + INTERVAL '1 month' - INTERVAL '1 day') AS daily_rent_cost
```

---

## 🔧 建议的补充工作

### 补充1：创建缺失的spec文件
- [ ] 创建`specs/frontend-api-contracts/spec.md`
- [ ] 创建`specs/dashboard/spec.md`

### 补充2：增强安全性设计
- [ ] 补充Superset SSO/JWT认证详细方案
- [ ] 补充RLS配置和测试方案
- [ ] 补充数据脱敏规则（如果需要）

### 补充3：增强可靠性设计
- [ ] 补充物化视图刷新失败恢复机制
- [ ] 补充Superset服务降级详细方案
- [ ] 补充数据一致性验证脚本

### 补充4：增强可审计性
- [ ] 补充A类数据版本管理机制
- [ ] 补充操作日志记录规范
- [ ] 补充审计报表生成机制

### 补充5：明确成本计算逻辑
- [ ] 明确成本分摊算法（按天/按实际天数）
- [ ] 明确变动成本计算逻辑（成本率 × 销售额）
- [ ] 明确利润计算公式（销售额 - 固定成本 - 变动成本）

---

## 📊 漏洞严重性评估

| 漏洞 | 严重性 | 影响范围 | 是否阻塞实施 |
|------|--------|----------|-------------|
| 漏洞1: 缺少frontend-api-contracts规格 | 中 | 前端开发 | ❌ 不阻塞（可在Phase 3补充） |
| 漏洞2: 缺少dashboard规格 | 中 | 前端开发 | ❌ 不阻塞（可在Phase 3补充） |
| 漏洞3: 字段映射简化细节不足 | 低 | 后端开发 | ❌ 不阻塞（开发时明确） |
| 漏洞4: 用户认证集成细节缺失 | 🔴 高 | 安全性 | ⚠️ 建议Phase 2前补充 |
| 漏洞5: 数据权限控制不具体 | 🔴 高 | 安全性 | ⚠️ 建议Phase 2前补充 |
| 漏洞6: 刷新失败处理不完整 | 中 | 可靠性 | ❌ 不阻塞（可在Phase 4补充） |
| 漏洞7: 性能降级策略不详细 | 中 | 用户体验 | ❌ 不阻塞（可在Phase 3补充） |
| 漏洞8: 数据一致性验证缺失 | 中 | 数据质量 | ❌ 不阻塞（Phase 1验收时补充） |
| 漏洞9: A类数据版本管理缺失 | 低 | 审计追溯 | ❌ 不阻塞（可在Phase 3补充） |
| 漏洞10: 成本分摊逻辑未明确 | 中 | 财务计算 | ❌ 不阻塞（Phase 1时明确） |

---

## ✅ 总体评估

### 优点
1. ✅ 架构设计合理，符合DSS系统标准
2. ✅ 渐进式迁移策略，风险可控
3. ✅ 零破坏性变更，向后兼容
4. ✅ 任务清单详细（90+任务项）
5. ✅ OpenSpec合规性100%

### 需要改进的地方
1. ⚠️ **安全性设计需要加强**（漏洞4、5）- 建议在Phase 2前补充
2. ⚠️ **缺少2个spec文件**（frontend-api-contracts、dashboard）- 建议补充
3. ⚠️ **可靠性设计可以更详细**（漏洞6、7）- 不阻塞，可在实施中补充
4. ℹ️ 其他漏洞影响较小，可在实施过程中迭代补充

### 建议的优先级
1. **P0（必须）**: 补充Superset用户认证和RLS安全设计（漏洞4、5）
2. **P1（重要）**: 创建缺失的spec文件（漏洞1、2）
3. **P2（建议）**: 补充可靠性和审计设计（漏洞6、7、9）
4. **P3（优化）**: 其他细节补充（漏洞3、8、10）

---

## 🎯 下一步行动建议

### 立即行动（今天）
1. 补充安全性设计（漏洞4、5）到bi-layer/spec.md
2. 创建frontend-api-contracts/spec.md（漏洞1）
3. 创建dashboard/spec.md（漏洞2）

### 短期行动（Phase 1开始前）
4. 明确成本分摊算法（漏洞10）
5. 创建数据一致性验证脚本（漏洞8）

### 中期行动（Phase 2-3实施中）
6. 实现降级策略详细方案（漏洞7）
7. 实现A类数据版本管理（漏洞9）

### 长期优化（Phase 4）
8. 完善刷新失败恢复机制（漏洞6）
9. 优化字段映射简化实施（漏洞3）

---

**审查人**: AI Agent  
**审查日期**: 2025-11-22  
**审查结果**: ⚠️ 发现10个漏洞，其中2个高严重性（安全相关）  
**总体评分**: 7.5/10 - 架构合理，需要加强安全设计  
**建议**: 补充安全性设计后可以开始实施

