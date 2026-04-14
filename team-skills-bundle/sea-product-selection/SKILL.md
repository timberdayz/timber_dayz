---
name: sea-product-selection
description: Use when evaluating a product, category, or SKU for Southeast Asia cross-border e-commerce selection, especially when the team needs a consistent method to compare demand, competition, profitability, content potential, differentiation, and supply-chain risk before deciding go, hold, or reject.
---

# Sea Product Selection

## Status

This is the mandatory workflow for SEA product selection.  
It is used for employee product proposals and agent evaluation.

## Core Rule

所有选品结论都必须按统一评分卡输出。  
不要用“感觉能做”“最近很火”“竞品卖得不错”直接下结论。

先给证据，再给评分，再给结论。

## Mandatory Gates

在输出 `go / hold / reject` 前，必须完成：

1. 读取指标状态，确认没有使用 `blocked` 指标支撑结论
2. 完成类目预筛
3. 完成六维评分
4. 应用 V0 阈值或已校准阈值
5. 检查一票否决项
6. 输出员工提报格式或老板复核格式

缺少关键证据时，只能输出 `hold` 或 `reject`，不得输出 `go`。

## How To Invoke

当用户要求“开始选品”“评估候选品”“判断这个产品能不能做”“比较不同员工选品结果”时，agent 必须按以下调用链执行：

1. 使用本 skill
2. 使用 `../sea-metrics-language/SKILL.md` 确认指标定义和状态
3. 使用 `references/selection-scorecard.md` 评分
4. 使用 `references/threshold-standards.md` 判断阈值
5. 使用 `references/submission-template.md` 输出候选品
6. 如果是复核他人提案，使用 `references/review-template.md`

不得只给产品列表或泛泛建议。

## Standard User Request

人类或 agent 可使用以下标准请求启动选品：

```text
请按 docs/team-skills/sea-product-selection/SKILL.md 执行本次选品任务，
并引用 docs/team-skills/sea-metrics-language/SKILL.md 的统一指标规则。

要求：
1. 所有判断按六维评分卡执行
2. 所有指标定义必须符合 sea-metrics-language
3. 应用 threshold-standards.md 的当前阈值
4. 存在证据不足时，必须标记 missing evidence 或 needs-calibration
5. 最终只能输出 go / hold / reject
6. 按 submission-template.md 的格式输出
```

如果用户只给出产品名称但没有数据，agent 必须列出缺失数据清单，并默认输出 `hold` 或请求补充证据。

## Required References

先读：

- `../sea-metrics-language/references/metrics-dictionary.md`
- `../sea-metrics-language/references/metric-status.md`
- `../sea-metrics-language/references/metric-usage-matrix.md`

再读：

- `references/selection-scorecard.md`
- `references/threshold-standards.md`
- `references/calibration-framework.md`
- `references/category-checklist.md`
- `references/validation-thresholds.md`
- `references/submission-template.md`
- `references/review-template.md`

## Evaluation Order

1. 先判断需求是否成立
2. 再判断竞争是否可切入
3. 再判断利润是否成立
4. 再判断内容表现力是否够强
5. 再判断是否有差异化 / 品牌化空间
6. 最后判断供应链和风险是否可控

## Output Rule

每个候选品最终只能给三种结论：

- `go`
- `hold`
- `reject`

没有证据的项不能给高分。  
任何一票否决项成立时，不得给 `go`。

评分时必须使用 `references/threshold-standards.md` 的 V0 阈值。  
如果平台、国家或品类缺少历史校准数据，先使用 V0 阈值并标记为 `needs-calibration`。

## One-Vote Veto

以下情况任一成立，禁止直接进入 `go`：

- 利润明显不足
- 合规风险高
- 高退货 / 高售后风险
- 供应链极不稳定
- 完全没有差异化空间

## Output Format

- 产品
- 平台 / 国家
- 目标人群
- 关键证据
- 六维评分
- 总分
- 结论
- 建议动作
- 复查时间

## Failure Behavior

如果缺少搜索、销量、利润、竞争或供应链证据，必须写明：

- 缺失哪项证据
- 缺失证据影响哪个评分维度
- 当前结论为什么不能是 `go`
