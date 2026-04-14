---
name: sea-funnel-action-playbook
description: Use when diagnosing Southeast Asia Shopee or TikTok product, shop, content, or campaign performance from funnel signals, especially when the team needs to convert data patterns such as high exposure low click, high click low cart, high content engagement low sales, good conversion poor margin, or high sales high return into standard actions.
---

# Sea Funnel Action Playbook

## Status

This is the mandatory action playbook for funnel signal diagnosis.  
It converts data patterns into bottleneck judgments and standard actions.

## Core Rule

不要只问“卖不卖”。  
先判断瓶颈在哪里，再决定动作。

每个诊断必须输出：

- 数据表现
- 瓶颈判断
- 标准动作
- 不建议动作
- 复查指标
- 复查时间

## Required References

先读：

- `../sea-metrics-language/SKILL.md`
- `../sea-business-review/SKILL.md`

再读：

- `references/signal-action-matrix.md`
- `references/shopee-shelf-funnel.md`
- `references/tiktok-content-funnel.md`
- `references/pdp-conversion-actions.md`
- `references/profit-brand-actions.md`
- `references/inventory-supply-actions.md`
- `references/action-output-template.md`

## Mandatory Gates

在输出动作前，必须完成：

1. 明确诊断对象：平台 / 店铺 / SKU / 内容 / 广告 / 直播
2. 明确漏斗阶段：曝光、点击、浏览、加购、下单、支付、复购、退货
3. 对照信号矩阵判断瓶颈
4. 输出标准动作
5. 指定复查指标和复查时间

数据不足时输出 `missing evidence`，不得直接给优化动作。

## How To Invoke

当用户要求“看到这些数据该怎么处理”“为什么有流量没成交”“为什么内容互动高但不出单”“为什么转化好但利润差”时，agent 必须使用本 skill。

如果涉及指标定义，必须引用 `sea-metrics-language`。  
如果涉及整体经营复盘，必须引用 `sea-business-review`。

## Standard User Request

```text
请按 docs/team-skills/sea-funnel-action-playbook/SKILL.md 诊断以下数据表现，
并引用 docs/team-skills/sea-metrics-language/SKILL.md 的统一指标规则。

要求：
1. 判断瓶颈属于哪个漏斗阶段
2. 输出数据表现、瓶颈判断、标准动作、不建议动作、复查指标、复查时间
3. 不允许只说“优化转化”这类泛泛建议
4. 数据不足时标记 missing evidence
```

## Output Rule

动作必须是可执行动作，不能是泛泛建议。

错误示例：

- 优化页面
- 提升转化
- 加强投放

正确示例：

- 重拍首图，突出价格锚点和核心使用场景
- 补充 FAQ、评价截图、保障承诺，降低购买疑虑
- 将脚本从娱乐型改为问题解决型，复查商品点击率和下单率
