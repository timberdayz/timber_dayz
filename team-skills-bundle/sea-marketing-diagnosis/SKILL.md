---
name: sea-marketing-diagnosis
description: Use when diagnosing Southeast Asia cross-border e-commerce marketing performance across Shopee ads, TikTok content, live, affiliate, or paid media, especially when the team needs a standard method to judge traffic quality, content efficiency, cost efficiency, conversion quality, and whether ROAS, MER, or GMV growth is actually healthy.
---

# Sea Marketing Diagnosis

## Status

This is the standard marketing diagnosis skill for SEA e-commerce growth work.  
It is used for ad, content, affiliate, and traffic-efficiency diagnosis.

## Core Rule

不要只看花钱后有没有销售。  
先判断：

1. 流量质量
2. 内容质量
3. 转化质量
4. 成本效率
5. 利润质量

GMV 增长不等于营销有效。  
ROAS 好看也不等于生意健康。

## Required References

先读：

- `../sea-metrics-language/SKILL.md`
- `../sea-funnel-action-playbook/SKILL.md`
- `../sea-business-review/SKILL.md`

再读：

- `references/channel-diagnostics.md`
- `references/shopee-ads-diagnostics.md`
- `references/tiktok-content-diagnostics.md`
- `references/affiliate-live-diagnostics.md`
- `references/roas-mer-guidelines.md`
- `references/action-template.md`

## Mandatory Gates

在输出营销判断前，必须完成：

1. 明确渠道：Shopee Ads / TikTok content / live / affiliate / paid media
2. 明确目标：拉新、成交、放量、清库存、打爆款
3. 明确指标来源和归因口径
4. 明确流量、点击、转化、成本、利润五层表现
5. 输出判断和动作

缺少成本、归因或转化证据时，不得直接下“投放有效”结论。

## How To Invoke

当用户要求“广告为什么没效果”“ROAS 是好还是坏”“TikTok 内容为什么有播放没成交”“达人为什么有曝光没出单”“Shopee 广告要不要加预算”时，必须使用本 skill。

如果涉及指标定义，引用 `sea-metrics-language`。  
如果涉及漏斗动作，引用 `sea-funnel-action-playbook`。  
如果涉及经营质量，引用 `sea-business-review`。

## Standard User Request

```text
请按 team-skills-bundle/sea-marketing-diagnosis/SKILL.md 诊断当前营销表现。

要求：
1. 明确渠道和目标
2. 拆流量、点击、转化、成本、利润五层表现
3. 说明 ROAS / MER / GMV 分别能证明什么、不能证明什么
4. 输出标准动作和复查指标
5. 缺数据时标记 missing evidence
```

## Output Rule

输出必须包含：

- 渠道
- 目标
- 关键指标
- 主要问题
- 营销判断
- 标准动作
- 不建议动作
- 复查指标
