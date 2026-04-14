---
name: sea-business-review
description: Use when reviewing weekly or monthly Southeast Asia cross-border e-commerce performance for a platform, shop, category, or SKU, especially when the team needs a consistent order to diagnose changes in GMV, traffic, conversion, average order value, profitability, inventory risk, or target achievement.
---

# Sea Business Review

## Status

This is the mandatory workflow for SEA business review.  
It is used for human meetings and agent analysis.

## Core Rule

所有经营复盘都按同一顺序判断：

1. 先拆 GMV 变化来自哪里
2. 再看利润是否同向变化
3. 再判断问题在流量、转化还是客单
4. 再看目标达成和时间进度
5. 最后看库存风险是否拖累经营

不要直接从动作跳到结论。  
先给事实，再给根因，再给动作。

## Mandatory Gates

在输出经营结论前，必须完成：

1. 明确复盘对象和时间范围
2. 明确比较基准
3. 拆解 GMV 变化
4. 检查利润是否同向
5. 判断主瓶颈
6. 给出动作和复查时间

缺少关键数据时，输出 `missing evidence`，不得直接给最终判断。

## How To Invoke

当用户要求“复盘经营”“看店铺表现”“分析 GMV 变化”“分析利润下滑”“周会/月会总结”时，agent 必须按以下调用链执行：

1. 使用本 skill
2. 使用 `../sea-metrics-language/SKILL.md` 确认指标定义和状态
3. 使用 `references/review-order.md` 确认复盘顺序
4. 使用 `references/diagnostic-tree.md` 判断根因
5. 使用 `references/report-template.md` 输出

不得只输出行动建议。

## Standard User Request

人类或 agent 可使用以下标准请求启动经营复盘：

```text
请按 docs/team-skills/sea-business-review/SKILL.md 复盘本次经营表现，
并引用 docs/team-skills/sea-metrics-language/SKILL.md 的统一指标规则。

要求：
1. 按 GMV、利润、流量、转化、客单、目标、库存顺序诊断
2. 指标定义必须符合 sea-metrics-language
3. 缺失数据必须标记 missing evidence
4. 按 report-template.md 输出
```

## Required References

先读：

- `../sea-metrics-language/references/metrics-dictionary.md`
- `../sea-metrics-language/references/metric-status.md`

再读：

- `references/review-order.md`
- `references/diagnostic-tree.md`
- `references/report-template.md`

## Rules

- 先拆症状，后判断根因。
- 不要用 `blocked` 指标下结论。
- 不要把“GMV 增长”直接等于“经营改善”。
- 不要把“利润下降”直接归因于投放，除非成本口径足够清楚。
- 不要在没有拆开 `traffic / conversion / avg_order_value` 之前直接给动作建议。
- 不要把增长、利润、目标和库存混成一个模糊结论。
- 不要只输出建议动作而不说明指标证据。

## Output Format

- 复盘对象
- 时间范围
- 核心事实
- 关键指标
- 根因判断
- 建议动作
- 复查时间

## Allowed Conclusions

复盘结论必须落到以下主瓶颈之一：

- 流量问题
- 转化问题
- 客单问题
- 利润问题
- 目标节奏问题
- 库存风险问题
- 数据不足，需补证据
