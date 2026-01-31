# 绩效公示优化、我的收入与 Public 表 Schema 迁移 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-01-31（采用方案 B：完全迁移，迁移后删除原表）  
**状态**: 提案已更新，待审批

---

## 变更概要

### Phase 0（核心）：Public 表完全迁移

| 原表 | 目标表 | 操作 |
|------|--------|------|
| `public.sales_targets` | `a_class.sales_targets`（新建） | 迁移数据 → 更新 target_breakdown 外键 → 删除原表 |
| `public.performance_scores` | `c_class.performance_scores` | 迁移数据 → 删除原表 |
| `public.shop_health_scores` | `c_class.shop_health_scores` | 迁移数据 → 删除原表 |
| `public.shop_alerts` | `c_class.shop_alerts` | 迁移数据 → 删除原表 |

**重要说明**：
- `a_class.sales_targets`（新建）与 `a_class.sales_targets_a`（现有聚合表）是两张不同的表
- 迁移不影响 TargetSyncService 同步到 `sales_targets_a`

### Phase 1：绩效公示修复

- 修复 `db.execute` 缺少 `await` 问题
- 完善计算逻辑，写入 `c_class.performance_scores`

### Phase 2-3：我的收入

- 新增后端 API：`GET /api/hr/me/income`
- 新增前端页面：`MyIncome.vue`

### Phase 4-5：菜单、路由、API 客户端

### Phase 6：验证

---

## 依赖

- **add-link-user-employee-management**：需先完成（Employee.user_id、我的档案）

---

## 迁移后删除的表

迁移完成后，以下 public 表将被**删除**：

- `public.sales_targets`
- `public.performance_scores`
- `public.shop_health_scores`
- `public.shop_alerts`

---

## 验证命令

```bash
npx openspec validate add-performance-and-personal-income --strict
```

---

## 相关文档

- [proposal.md](./proposal.md) - 变更说明
- [tasks.md](./tasks.md) - 实施任务清单
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量
