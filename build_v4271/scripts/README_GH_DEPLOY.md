# 使用 GitHub CLI (gh) 查看部署结果

## 1. 安装 GitHub CLI（本机未安装时）

### 方式一：winget（推荐，Windows 10/11）

在 **PowerShell 或 CMD（管理员可选）** 中执行：

```powershell
winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
```

安装完成后 **关闭并重新打开终端**，再执行 `gh --version` 确认。

### 方式二：手动安装

1. 打开 https://github.com/cli/cli/releases/latest
2. 下载 `gh_*_windows_amd64.msi`
3. 双击安装，安装完成后 **新开终端**

### 登录（首次使用必须）

```powershell
gh auth login
```

按提示选择 GitHub.com，浏览器或 token 方式登录即可。

---

## 2. 部署后如何“自动/半自动”查看问题点

- **push 仍由你执行**：`git push origin v4.24.9`（或先 `git tag v4.24.9` 再 push）。
- **用 gh 查看本次 run 的状态和失败日志**，无需打开浏览器。

### 2.1 查看最近一次 Deploy to Production 的 run

```powershell
gh run list --workflow="Deploy to Production" -L 1
```

会看到类似：`123456789  Deploy to Production  push   failure   v4.24.9  2m`，第一列是 run id。

### 2.2 查看该 run 的失败步骤日志（便于贴给 AI 排查）

```powershell
gh run view <run-id> --log-failed
```

例如 run id 为 123456789：

```powershell
gh run view 123456789 --log-failed
```

把终端输出的失败步骤日志复制给 Cursor/AI，即可快速定位部署问题点。

### 2.3 一条命令：push 后等待并查看结果（半自动）

在项目根目录执行（将 `v4.24.9` 换成你要发布的 tag）：

```powershell
# 1. 打 tag 并推送（若尚未打 tag）
git tag v4.24.9
git push origin v4.24.9

# 2. 等待约 10 秒让 GitHub 创建 run，再取最新 run id
Start-Sleep -Seconds 10
$runId = (gh run list --workflow="Deploy to Production" -L 1 --json databaseId -q ".[0].databaseId")
Write-Host "Run ID: $runId"

# 3. 等待该 run 结束（会持续输出状态）
gh run watch $runId

# 4. 若失败，拉取失败日志到终端
gh run view $runId --log-failed
```

这样你一次操作即可：push → 等待跑完 → 若失败直接在终端看到失败日志，复制贴给 AI 即可。

---

## 3. 小结

| 目的                     | 命令 |
|--------------------------|------|
| 检查 gh 是否安装         | `gh --version` |
| 查看最近一次部署 run     | `gh run list --workflow="Deploy to Production" -L 1` |
| 查看某次 run 的失败日志  | `gh run view <run-id> --log-failed` |
| push 后等待并看结果      | 见上面 2.3 的 PowerShell 片段 |

“自动 push”仍由你执行 `git push origin v4.24.9`；“自动查看部署问题点”可通过上述 `gh run watch` + `gh run view --log-failed` 在终端完成，无需切到网页。
