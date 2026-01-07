# 提案和待办遗漏检查报告 - 2025-11-27

## 🔍 发现的遗漏和问题

### 1. 重复任务 ⚠️ **严重**

**问题**：`tasks.md`中0.7.16任务重复了两次（207-212行和213-218行）

**位置**：
- 第207-212行：第一次出现
- 第213-218行：第二次出现（完全重复）

**修复**：删除第二次出现的重复任务

---

### 2. Phase 2缺失 ⚠️ **严重**

**问题**：
- `proposal.md`中提到了Phase 2："Metabase Dashboard创建和配置（2周）"
- `tasks.md`中**没有Phase 2**，直接从Phase 1跳到Phase 3
- Phase 1中的任务编号混用了1.x和2.x（如2.5.1, 2.6.1等）

**分析**：
- Phase 1中的任务编号2.x实际上应该是Phase 2的内容
- 需要将Phase 1中的Dashboard创建任务（2.5.x, 2.6.x等）移到Phase 2

**修复**：
1. 在tasks.md中创建Phase 2章节
2. 将Phase 1中的Dashboard创建任务移到Phase 2
3. 统一任务编号（Phase 1使用1.x，Phase 2使用2.x）

---

### 3. 需要标记废弃的API缺少任务 ⚠️ **中等**

**问题**：
- `proposal.md`中列出了需要废弃的文件：
  - `backend/services/materialized_view_service.py` - 标记废弃（Phase 6删除）
  - `backend/routers/materialized_views.py` - 标记废弃（Phase 6删除）
  - `backend/routers/main_views.py` - 需要重构（改为查询原始B类数据表，Phase 4完成）
  - `backend/routers/metrics.py` - 需要重构（改为Metabase代理，Phase 4完成）
  - `backend/routers/store_analytics.py` - 需要重构（改为Metabase代理，Phase 4完成）
  - `backend/routers/dashboard_api.py` - 需要重构（改为Metabase代理，Phase 4完成）
- `tasks.md`中**没有对应的任务**来标记这些API为废弃

**修复**：
1. 在Phase 4中添加任务：标记废弃的API（添加@deprecated装饰器或返回410 Gone）
2. 在Phase 6中添加任务：删除废弃的API代码

---

### 4. 前端API契约检查缺失 ⚠️ **中等**

**问题**：
- `proposal.md`中列出了需要删除的API端点：
  - `POST /api/dashboard/calculate-metrics` - REMOVED
  - `GET /api/dashboard/shop-performance` - REMOVED
  - `GET /api/dashboard/product-ranking` - REMOVED
  - `GET /api/dashboard/overview` - REMOVED
- `tasks.md`中没有明确的任务来：
  1. 检查这些API是否仍在使用
  2. 标记为废弃
  3. 删除代码

**修复**：
1. 在Phase 4中添加任务：检查并标记废弃的Dashboard API
2. 在Phase 6中添加任务：删除废弃的Dashboard API代码

---

### 5. 数据迁移验证任务不完整 ⚠️ **中等**

**问题**：
- `tasks.md`中0.1.8.4提到了数据验证，但不够详细
- 缺少具体的验证脚本和自动化测试

**修复**：
1. 细化0.1.8.4任务，添加具体的验证步骤
2. 创建验证脚本：`scripts/validate_migration.py`

---

### 6. Metabase定时计算任务实现方式不明确 ⚠️ **中等**

**问题**：
- Phase 3中提到了Metabase定时计算任务（3.2.1-3.2.5）
- 但没有明确说明是使用Metabase Scheduled Questions还是后端API定时任务
- 缺少实现细节和选择标准

**修复**：
1. 在design.md或tasks.md中明确实现方式
2. 如果使用后端API，需要添加Celery或APScheduler配置任务

---

### 7. 前端组件迁移清单文档缺失 ⚠️ **中等**

**问题**：
- `tasks.md`中0.7.16提到了创建`docs/FRONTEND_MIGRATION_CHECKLIST.md`
- 但proposal.md中的前端组件依赖清单可能不完整
- 需要检查实际代码中的前端组件

**修复**：
1. 检查`frontend/src/views/`目录，列出所有需要迁移的组件
2. 更新proposal.md中的前端组件依赖清单

---

### 8. 性能测试脚本缺失 ⚠️ **低**

**问题**：
- `tasks.md`中提到了性能测试，但缺少具体的测试脚本
- 4.2.4提到了`scripts/test_metabase_performance.py`，但可能不存在

**修复**：
1. 在Phase 5中添加任务：创建性能测试脚本
2. 创建`scripts/test_metabase_performance.py`

---

### 9. 文档更新任务不完整 ⚠️ **低**

**问题**：
- Phase 5中有文档编写任务（4.5.x）
- 但可能遗漏了一些重要的文档更新，如：
  - API文档中需要标记废弃的端点
  - 架构文档中需要说明新架构与旧架构的区别

**修复**：
1. 检查所有文档是否需要更新
2. 添加文档更新检查清单

---

### 10. 回滚方案验证缺失 ⚠️ **低**

**问题**：
- `proposal.md`中提到了回滚方案（3个月内可以恢复旧表结构）
- 但`tasks.md`中没有验证回滚方案的任务

**修复**：
1. 在Phase 0中添加任务：测试回滚脚本
2. 在Phase 5中添加任务：验证回滚方案

---

## 📋 修复优先级

### 高优先级（必须修复）
1. ✅ **重复任务**（0.7.16）- 立即修复
2. ✅ **Phase 2缺失** - 立即修复
3. ⚠️ **需要标记废弃的API缺少任务** - Phase 4前完成

### 中优先级（建议修复）
4. ⚠️ **前端API契约检查缺失** - Phase 4前完成
5. ⚠️ **数据迁移验证任务不完整** - Phase 0完成前补充
6. ⚠️ **Metabase定时计算任务实现方式不明确** - Phase 3前明确

### 低优先级（可选）
7. ⚠️ **前端组件迁移清单文档缺失** - Phase 4前完成
8. ⚠️ **性能测试脚本缺失** - Phase 5前完成
9. ⚠️ **文档更新任务不完整** - Phase 5前完成
10. ⚠️ **回滚方案验证缺失** - Phase 0完成前补充

---

## ✅ 修复计划

### 立即修复（本次更新）
1. 删除重复的0.7.16任务
2. 创建Phase 2章节，移动Dashboard创建任务
3. 统一任务编号

### Phase 4前修复
4. 添加标记废弃API的任务
5. 添加前端API契约检查任务
6. 完善前端组件迁移清单

### Phase 5前修复
7. 创建性能测试脚本
8. 完善文档更新任务
9. 添加回滚方案验证任务

---

**检查完成时间**：2025-11-27  
**检查人**：AI Agent  
**下次检查**：Phase 4开始前

