# Team Skills

本目录是团队经营工作 skill 包，供人类员工和 agent 共同使用。

这些 skill 不是参考资料。  
当任务匹配触发场景时，agent 必须按对应 `SKILL.md` 执行。

## Active Skills

| Skill | Use When | Primary Output |
|---|---|---|
| `sea-metrics-language` | 定义、解释、比较经营指标；处理 Shopee、TikTok、ERP、会议口径不一致 | 指标定义、公式、来源、状态、适用边界 |
| `sea-business-review` | 周会、月会、店铺 / 平台 / 品类 / SKU 经营复盘 | 经营问题诊断、根因、动作、复查时间 |
| `sea-product-selection` | 新品、品类、SKU、Hero SKU 候选评估 | 六维评分、总分、`go / hold / reject` |
| `sea-funnel-action-playbook` | 根据漏斗数据表现判断瓶颈并给出标准动作 | 数据表现、瓶颈、动作、复查指标 |

## Routing

选品任务：

1. 使用 `sea-product-selection`
2. 指标定义或口径有争议时使用 `sea-metrics-language`

经营复盘任务：

1. 使用 `sea-business-review`
2. 指标定义或口径有争议时使用 `sea-metrics-language`

指标争议任务：

1. 只使用 `sea-metrics-language`
2. 先看 `metric-status.md`
3. `blocked` 指标禁止进入最终结论

漏斗动作任务：

1. 使用 `sea-funnel-action-playbook`
2. 指标定义或口径有争议时使用 `sea-metrics-language`
3. 涉及整体经营问题时使用 `sea-business-review`

## Global Rules

- 不允许用感觉替代数据。
- 不允许用页面标签替代指标定义。
- 不允许跳过 `go / hold / reject` 或复盘输出格式。
- 不允许用 `blocked` 指标下最终结论。
- 缺失数据必须标记为 `missing` 或 `needs-calibration`，不能假设。
- 结论必须包含证据、判断和下一步动作。

## Required Agent Behavior

agent 收到相关任务后必须：

1. 明确使用哪个 skill。
2. 读取该 skill 的 `SKILL.md`。
3. 按 `Required References` 读取必要 references。
4. 按 skill 指定的输出模板回答。
5. 如果数据不足，输出 `hold`、`missing evidence` 或 `needs-calibration`，不得硬判 `go`。

## Standard Prompts

### Product Selection

当用户要选品、评估产品、比较候选 SKU、判断是否值得做精品时，agent 必须按下面的工作方式执行：

```text
Use `docs/team-skills/sea-product-selection/SKILL.md`.
Use `docs/team-skills/sea-metrics-language/SKILL.md` for metric definitions and metric status.
Evaluate all candidates with the six-dimension scorecard.
Apply `threshold-standards.md`.
Use `submission-template.md` for candidate output.
Use `review-template.md` when reviewing another person's proposal.
Final decision must be one of: go, hold, reject.
If evidence is missing, mark missing evidence or needs-calibration and do not output go.
```

人类员工也按同样规则提报。不得提交自由格式选品建议。

### Business Review

当用户要复盘店铺、平台、品类、SKU、周会、月会或经营异常时，agent 必须按下面的工作方式执行：

```text
Use `docs/team-skills/sea-business-review/SKILL.md`.
Use `docs/team-skills/sea-metrics-language/SKILL.md` for metric definitions and metric status.
Diagnose in the required order: GMV, profit, traffic, conversion, average order value, target progress, inventory risk.
Use `report-template.md` for output.
If evidence is missing, mark missing evidence and do not infer root cause.
```

### Metric Dispute

当用户问“这个指标怎么算”“这个指标能不能用”“为什么系统和平台不一致”时，agent 必须按下面的工作方式执行：

```text
Use `docs/team-skills/sea-metrics-language/SKILL.md`.
Check `metrics-dictionary.md`, `metric-status.md`, `platform-mapping.md`, and `metric-usage-matrix.md`.
Explain the platform-native metric, system-unified metric, and meeting decision metric separately.
Do not use blocked metrics in final recommendations.
```

### Funnel Action Diagnosis

当用户问“看到这个数据表现该怎么办”“为什么有流量没成交”“为什么互动高成交弱”“为什么转化好但利润差”时，agent 必须按下面的工作方式执行：

```text
Use `docs/team-skills/sea-funnel-action-playbook/SKILL.md`.
Use `docs/team-skills/sea-metrics-language/SKILL.md` for metric definitions and metric status.
Match the data pattern to the signal action matrix.
Output data pattern, bottleneck, standard action, not recommended action, review metrics, and review date.
If evidence is missing, mark missing evidence and do not infer action.
```

## Human Workflow

选品员工：

1. 读取 `sea-product-selection/SKILL.md`
2. 使用 `submission-template.md` 提报候选品
3. 给出六维评分和 `go / hold / reject`
4. 指标定义不清楚时查 `sea-metrics-language`

负责人 / 老板：

1. 使用 `review-template.md` 复核候选品
2. 检查是否存在一票否决
3. 检查评分是否符合 `threshold-standards.md`
4. 确认结论是否维持、降级或驳回

经营复盘主持人：

1. 使用 `sea-business-review`
2. 按 `report-template.md` 输出结论
3. 不允许绕过指标直接给动作

运营执行人：

1. 使用 `sea-funnel-action-playbook`
2. 先判断漏斗瓶颈
3. 按矩阵执行标准动作
4. 记录复查指标和复查时间

## Cross-Skill Dependencies

- `sea-metrics-language` 是底层依赖。
- `sea-business-review` 必须引用 `sea-metrics-language`。
- `sea-product-selection` 必须引用 `sea-metrics-language`。
- `sea-funnel-action-playbook` 必须引用 `sea-metrics-language`；涉及经营全局时引用 `sea-business-review`。
- 后续 `sea-marketing-diagnosis` 必须引用 `sea-metrics-language`、`sea-funnel-action-playbook` 和必要的产品 / 经营结论。

## Version Policy

当前版本为 V1 标准执行版。  
V1 可以直接用于 agent 工作要求。  
阈值文件中标记为 `v0` 的标准表示“当前执行标准，待历史数据校准”，不是“可忽略标准”。
