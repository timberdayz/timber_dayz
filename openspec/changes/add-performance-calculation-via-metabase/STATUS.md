# 绩效计算 Metabase 方案 - 实施状态

**创建日期**: 2026-01-31  
**状态**: 待审批 - 提案已创建，等待批准后实施

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
