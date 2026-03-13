# 绩效计算 Metabase 方案 - 实施状态

**创建日期**: 2026-01-31  
**更新日期**: 2026-03-13（补充前置依赖：须先完成 add-performance-and-personal-income Phase 0）  
**状态**: 待审批 - 提案已创建，等待批准后实施

---

## 实现顺序

- **前置**：须先完成 **add-performance-and-personal-income** 的 **Phase 0**（public 表迁移至 a_class/c_class），确保 `a_class.sales_targets`、`c_class.performance_scores`、`c_class.shop_health_scores` 等表已存在，再实施本提案。

---

## 变更概要

- **新增 Metabase Question**：`performance_scores_calculation`（店铺月度绩效得分计算）
- **修改后端**：`POST /api/performance/scores/calculate` 调用 Metabase 并写入 `c_class.performance_scores`
- **数据流**：Metabase SQL 读取 b_class 订单、a_class 目标与配置 → 后端写入 c_class.performance_scores → 绩效公示读取展示

---

## 验证命令

```bash
npx openspec validate add-performance-calculation-via-metabase --strict
```

---

## 相关文档

- [proposal.md](./proposal.md) - 变更说明
- [design.md](./design.md) - 技术设计
- [tasks.md](./tasks.md) - 实施任务清单
- [specs/hr-management/spec.md](./specs/hr-management/spec.md) - 规格增量
