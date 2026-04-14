# Team Skills Bundle

这是团队经营分析与选品工作的**跨平台 skill bundle**。  
目标不是只给 Codex 使用，而是让不同成员使用的 agent 都能接入同一套工作标准。

## Bundle Goals

- 即插即用
- 平台无关
- 先统一指标语言，再统一判断顺序，再统一动作
- 既适合人类员工，也适合 agent

## Included Skills

| Skill | Purpose |
|---|---|
| `sea-metrics-language` | 统一指标定义、口径、状态、适用边界 |
| `sea-business-review` | 统一经营复盘顺序与结论输出 |
| `sea-product-selection` | 统一选品评分、阈值、`go / hold / reject` |
| `sea-funnel-action-playbook` | 把漏斗数据表现转成标准动作 |
| `sea-operations-daily-sop` | 把经营标准转成每日时间分配、优先级和执行节奏 |
| `sea-business-models` | 统一比较精品、精铺、铺货模式与转型路径 |
| `sea-marketing-diagnosis` | 统一诊断广告、达人、内容、直播、ROAS / MER 问题 |

## Portable Structure

每个 skill 都使用通用结构：

```text
skill-name/
  SKILL.md
  references/
  agents/openai.yaml   # Codex / OpenAI 兼容元数据，可选
```

`SKILL.md + references/` 是平台无关的核心。  
即使某个 agent 不识别 `agents/openai.yaml`，仍可通过读取 `SKILL.md` 和 `references/` 工作。

## Cross-Skill Routing

### Product Selection

使用：

1. `sea-product-selection`
2. `sea-metrics-language`

### Business Review

使用：

1. `sea-business-review`
2. `sea-metrics-language`

### Funnel Action Diagnosis

使用：

1. `sea-funnel-action-playbook`
2. `sea-metrics-language`
3. 如涉及全局经营判断，再补 `sea-business-review`

### Daily Operations Planning

使用：

1. `sea-operations-daily-sop`
2. 指标定义争议时补 `sea-metrics-language`
3. 经营异常优先级判断时补 `sea-business-review`
4. 漏斗动作设计时补 `sea-funnel-action-playbook`
5. 有选品任务时补 `sea-product-selection`

### Marketing Diagnosis

使用：

1. `sea-marketing-diagnosis`
2. 指标定义争议时补 `sea-metrics-language`
3. 漏斗动作判断时补 `sea-funnel-action-playbook`
4. 涉及整体经营质量时补 `sea-business-review`

### Metric Dispute

只使用：

1. `sea-metrics-language`

### Business Model Decision

使用：

1. `sea-business-models`
2. 涉及选品时补 `sea-product-selection`
3. 涉及经营能力和利润结构时补 `sea-business-review` 与 `sea-metrics-language`

## Agent-Agnostic Usage

如果你的 agent 支持“skills / slash commands / prompt libraries / reusable markdown guides”，请将每个 skill 文件夹作为一个独立 skill 安装或导入。

如果你的 agent 不支持原生 skill 机制，也可以这样使用：

1. 先打开目标 `SKILL.md`
2. 按 `Required References` 读取相应 references
3. 严格按 `How To Invoke` 和 `Standard User Request` 执行

## Platform Notes

### Codex / OpenAI-compatible

- 直接将 skill 文件夹复制到 `$CODEX_HOME/skills/`
- `agents/openai.yaml` 用于 UI 元数据

### Claude-compatible

- 将 skill 文件夹复制到 Claude 使用的 skills 目录
- 若无自动安装机制，可把 `SKILL.md` 作为团队 prompt guide 引入

### Gemini / Other agents

- 保留目录结构不变
- 只要 agent 能读取 markdown 和相对 references，即可使用

## Standard Rule

这些 skill 不是参考资料，而是工作标准。

- 不允许用感觉替代数据
- 不允许绕过模板
- 不允许忽略 `blocked` 指标
- 缺少证据时必须标记 `missing evidence` 或 `needs-calibration`

## Current Status

当前为 V1 标准执行版。  
可直接用于 agent 工作要求。  
阈值中的 `v0` 表示当前执行标准，待历史数据校准，不表示可以忽略。
