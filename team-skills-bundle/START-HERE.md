# START HERE

如果你刚拿到这个 bundle，先看这一页。  
目标：让你在 30 秒内知道**该把 skill 放哪里、怎么安装、怎么开始用**。

## 这是什么

这是团队经营工作的标准 skill bundle。  
它不是普通文档，而是一套可被人类员工和 agent 共同使用的工作标准。

包含：

- 指标语言
- 经营复盘
- 选品评分
- 漏斗动作
- 每日运营 SOP
- 模式选择
- 营销诊断

## 第一步：你用什么 agent

### 如果你用 Codex / OpenAI 兼容环境

把 skill 安装到：

```text
$CODEX_HOME/skills/
```

如果没设置 `CODEX_HOME`，通常是：

```text
~/.codex/skills/
```

最简单做法：

```powershell
pwsh ./scripts/install-team-skills.ps1
```

或：

```bash
python ./scripts/install-team-skills.py
```

## 如果你用 Claude 或其他支持 skills / prompt library 的 agent

做法：

1. 把每个 skill 文件夹复制到该 agent 的 skills 目录
2. 如果该 agent 不支持原生安装，就直接保留 `SKILL.md + references/`
3. 工作时按 `How To Invoke` 和 `Standard User Request` 使用

## 如果你用其他不支持原生 skills 的 agent

也可以工作。

做法：

1. 打开目标 skill 的 `SKILL.md`
2. 按 `Required References` 打开相应 reference 文件
3. 把 `Standard User Request` 当作工作提示词使用

## 第二步：你现在要做什么

### 你要统一指标口径

用：

- `sea-metrics-language`

路径：

- `sea-metrics-language/SKILL.md`

### 你要做选品

用：

- `sea-product-selection`
- 如指标有争议，补 `sea-metrics-language`

### 你要做经营复盘

用：

- `sea-business-review`
- 如指标有争议，补 `sea-metrics-language`

### 你要根据数据表现决定动作

用：

- `sea-funnel-action-playbook`

### 你要安排今天的运营工作

用：

- `sea-operations-daily-sop`

如果需要明确到“几点做什么”，读取：

- `sea-operations-daily-sop/references/time-slots.md`

### 你要判断精品 / 精铺 / 铺货模式

用：

- `sea-business-models`

### 你要看广告、达人、内容、直播、ROAS / MER

用：

- `sea-marketing-diagnosis`

## 第三步：最短使用方式

如果你不知道怎么开始，就直接复制对应 skill 里的 `Standard User Request`。

例如选品时：

```text
请按 team-skills-bundle/sea-product-selection/SKILL.md 执行本次选品任务，
并引用 team-skills-bundle/sea-metrics-language/SKILL.md 的统一指标规则。
```

例如经营复盘时：

```text
请按 team-skills-bundle/sea-business-review/SKILL.md 复盘本次经营表现，
并引用 team-skills-bundle/sea-metrics-language/SKILL.md 的统一指标规则。
```

## 第四步：必须遵守的规则

- 不允许用感觉替代数据
- 不允许绕过模板
- 不允许忽略 `blocked` 指标
- 数据不够时必须标记 `missing evidence` 或 `needs-calibration`
- 结论必须有证据、判断和动作

## 你下一步该看什么

推荐顺序：

1. `README.md`
2. `INSTALL.md`
3. 你当前任务对应的 `SKILL.md`
4. 该 skill 的 `Required References`

## 文件导航

- 总说明：`README.md`
- 安装说明：`INSTALL.md`
- 安装脚本：
  - `scripts/install-team-skills.ps1`
  - `scripts/install-team-skills.py`
