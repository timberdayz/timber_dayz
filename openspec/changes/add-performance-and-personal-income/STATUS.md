# 绩效公示优化、我的收入与 Public 表 Schema 迁移 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-01-31（增加 Phase 0 Schema 迁移）  
**状态**: 提案已更新，待审批

---

## 变更概要

1. **Phase 0（新增）**：Public 表迁移至 A/C 类 schema
   - `performance_scores` → `c_class`
   - `shop_health_scores` → `c_class`
   - `shop_alerts` → `c_class`
   - `sales_targets` → `a_class`

2. **Phase 1**：绩效公示修复（db.execute 添加 await、完善 calculate 逻辑）

3. **Phase 2**：我的收入 API 与 C 类表数据写入

4. **Phase 3-6**：前端我的收入页面、菜单、验证

---

## 依赖

- **add-link-user-employee-management**：需先完成（Employee.user_id、我的档案）

---

## 验证

```bash
npx openspec validate add-performance-and-personal-income --strict
```

---

## 相关文档

- [proposal.md](./proposal.md) - 变更说明
- [tasks.md](./tasks.md) - 实施任务清单
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量
