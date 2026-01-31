# 人员店铺归属和提成比页面 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-01-31（漏洞修复已纳入）  
**状态**: 实施完成

---

## 实施完成（2026-01-31）

- ORM 模型、迁移、后端 API、前端页面、路由、菜单已完成
- 表 `a_class.employee_shop_assignments` 已存在（迁移已 stamp）

### Phase 2 优化（2026-01-31）

- 主页面改为 Tab 结构：配置 / 统计
- 配置子页：以店铺为行，表格化平铺（可分配利润率、主管/操作员多选、+ 添加、移除）
- 统计子页：月份选择器 + 表格（当月销售额、利润、达成率、人员利润收入，占位）
- 权限改为仅 admin 可见

---

## 漏洞修复（2026-01-31）

- 店铺数据来源：明确使用 api.getTargetShops()，后端校验 dim_shops
- 多人同店提成：明确各自按全店销售额×比例独立计算（不拆分）
- SalaryStructure 选取：status='active' 且 effective_date<=当前日期的最新记录
- employee_code：删除员工时需先解除归属（应用层校验）
- effective_to >= effective_from：Pydantic 校验
- commission_ratio：0-1 闭区间校验
- 索引命名：遵循 A 类表规范（ix_employee_shop_assignments_a_*）
- dim_shops 外键：ON DELETE RESTRICT
- routeTitles → route.meta.title 与 routeDisplayNames
- 员工下拉：仅展示在职（status='active'）
- 唯一约束命名：uq_employee_shop_assignments_a
- 提成计算：仅 status=active，effective NULL 语义
- 店铺不在 dim_shops：400 提示「该店铺尚未同步至系统，请先在账号管理中同步」
- PUT/DELETE id 不存在：404

---

## 验证

```bash
npx openspec validate add-employee-shop-assignment-page --strict
```

---

## 相关文档

- [proposal.md](./proposal.md) - 变更说明
- [design.md](./design.md) - 技术设计
- [tasks.md](./tasks.md) - 实施任务清单
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量
