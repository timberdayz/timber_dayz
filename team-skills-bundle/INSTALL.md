# Installation Guide

本 bundle 设计为跨平台使用。

## Option A: Install each skill folder directly

将以下目录复制到你的 agent skills 目录：

- `sea-metrics-language`
- `sea-business-review`
- `sea-product-selection`
- `sea-funnel-action-playbook`

## Option A2: Install with script

### PowerShell

```powershell
pwsh ./scripts/install-team-skills.ps1
```

覆盖已存在 skill：

```powershell
pwsh ./scripts/install-team-skills.ps1 -Force
```

指定目标目录：

```powershell
pwsh ./scripts/install-team-skills.ps1 -TargetDir "D:\\my-agent\\skills"
```

### Python

```bash
python ./scripts/install-team-skills.py
```

覆盖已存在 skill：

```bash
python ./scripts/install-team-skills.py --force
```

指定目标目录：

```bash
python ./scripts/install-team-skills.py --target-dir /path/to/skills
```

## Option B: Use as a repository-hosted bundle

如果你的 agent 不支持原生 skills：

1. 打开目标 skill 的 `SKILL.md`
2. 按 `Required References` 读取 references
3. 使用 `How To Invoke` 或 `Standard User Request`

## Codex Example

复制到：

```text
$CODEX_HOME/skills/
```

或直接运行：

```powershell
pwsh ./scripts/install-team-skills.ps1
```

## Validation Note

在 Windows 上验证 skill 时，建议启用 UTF-8：

```powershell
$env:PYTHONUTF8='1'
python quick_validate.py <skill-path>
```

否则某些默认 GBK 环境可能导致验证脚本报编码错误。
