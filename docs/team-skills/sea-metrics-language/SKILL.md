---
name: sea-metrics-language
description: Use when defining, comparing, or discussing Southeast Asia cross-border e-commerce metrics for product selection, business review, operations, or marketing decisions, especially when Shopee, TikTok, ERP, and meeting language may use inconsistent metric definitions or calculation logic.
---

# Sea Metrics Language

## Status

This is the source of truth for team metric language.  
When another team skill uses a metric, it must follow this skill.

## Core Rule

先区分三层口径，再讨论结论：

- 平台原生口径
- 系统统一口径
- 会议决策口径

页面标签不是定义。指标字典才是定义。

## Mandatory Use

使用任何经营指标前，必须确认：

1. 指标是否存在于 `references/metrics-dictionary.md`
2. 指标状态是否允许进入会议结论
3. 当前使用的是平台原生口径、系统统一口径还是会议决策口径
4. 该指标是否适用于当前任务场景

如果指标不存在或状态不清楚，不能直接用于最终结论。

## How To Invoke

当用户要求“解释指标”“统一口径”“判断某个指标能不能用”“为什么平台和系统数据不同”时，agent 必须按以下调用链执行：

1. 使用本 skill
2. 读取 `references/metrics-dictionary.md`
3. 读取 `references/metric-status.md`
4. 如涉及 Shopee / TikTok / ERP 差异，读取 `references/platform-mapping.md`
5. 如涉及具体业务场景，读取 `references/metric-usage-matrix.md`

不得跳过指标状态检查。

## Standard User Request

人类或 agent 可使用以下标准请求启动指标口径判断：

```text
请按 docs/team-skills/sea-metrics-language/SKILL.md 解释并判断以下指标口径。

要求：
1. 区分平台原生口径、系统统一口径、会议决策口径
2. 检查 metric-status.md
3. 标记该指标是否能进入最终结论
4. 说明该指标能证明什么、不能证明什么
```

## Read Order

1. 先读 `references/metrics-dictionary.md`
2. 再读 `references/metric-status.md`
3. 涉及 Shopee / TikTok 差异时读 `references/platform-mapping.md`
4. 讨论某个场景该看什么指标时读 `references/metric-usage-matrix.md`
5. 需要形成会议结论时读 `references/meeting-output-template.md`

## Rules

- 不要把平台原生指标和系统统一指标混成一个结论。
- 不要把 `blocked` 指标用于会议最终结论。
- 不要用 GMV 单独判断经营质量。
- 不要用搜索热度单独判断产品机会。
- 不要用销售额单独判断营销效率。
- 不要用库存价值单独判断库存健康。
- 不要把 `observe` 指标作为唯一证据。
- 不要用未定义指标生成新结论；先标记 `undefined metric`。

## Status Rule

每个指标必须标记为：

- `stable`
- `observe`
- `blocked`
- `deprecated`

只有 `stable` 指标可以直接进入团队最终结论。  
`observe` 只能辅助讨论，不能单独支撑决策。  
`blocked` 禁止用于会议结论。  

## Output Format

使用任一指标时，统一按这个顺序表达：

- 指标
- 定义
- 公式
- 来源
- 适用范围
- 可用于什么判断
- 不能证明什么
- 当前状态

## Failure Behavior

如果数据或定义不足，必须输出：

- `missing definition`
- `missing data`
- `needs-calibration`
- `blocked metric`

不得用猜测补齐。
