# API 契约验证失败说明（部署门禁）

**更新 (2026-03-13)**：已从根源修复 v4.24.10 部署失败涉及的三个 router 文件（`dashboard_api.py`、`target_management.py`、`component_versions.py`），全部改为使用 `backend.utils.api_response` 的 `error_response`/`success_response`，并已移除 workflow 中 Validate API Contracts 步骤的 `continue-on-error: true`。仅验证改动文件时，上述三文件 0 错误，发布门禁可通过。

---

## 1. GitHub CLI 状态

**当前本机未安装 GitHub CLI**（`gh` 命令不可用）。

- 部署是在 **GitHub Actions** 里跑的，不依赖本机是否安装 `gh`，所以 **部署失败与是否安装 gh 无关**。
- 若需要在本地用 `gh`（查 workflow、触发部署、看日志等），可安装：
  - **Windows**: `winget install GitHub.cli` 或从 [GitHub CLI 发布页](https://github.com/cli/cli/releases) 下载安装包。

---

## 2. 部署失败原因

失败发生在 **Deploy to Production** 工作流中的 **Validate API Contracts (Release Gate)** 步骤。

- **脚本**: `scripts/validate_api_contracts.py`
- **逻辑**: 检查 `backend/routers/` 下的路由是否遵守项目契约：
  - 使用 `error_response()` 而不是 `raise HTTPException(...)`（410 Gone 除外）
  - 使用 `success_response()` 时正确导入 `backend.utils.api_response`
  - 部分错误处理与日志规范

**当前本地全量验证结果**（与 CI 跑“全部文件”时一致）：

- 验证文件数: **49** 个 router 文件  
- **错误: 155**（导致退出码 1，门禁失败）  
- **警告: 331**

主要错误类型：

1. **应使用 error_response 而非 raise HTTPException**  
   涉及文件包括但不限于：  
   `account_management.py`, `auth.py`, `collection.py`, `component_versions.py`, `data_sync.py`, `field_mapping.py`, `finance.py`, `system_management/*.py`, `target_management.py`, `users.py` 等。
2. **except 中使用了 raise HTTPException 而非 error_response**
3. **error_response 调用缺少 recovery_suggestion 参数**（部分为警告）
4. **except 块缺少错误日志记录**（部分为错误）

因此：**只要“验证全部 router 文件”，当前代码就会报 155 个错误，Release Gate 会失败。**

---

## 3. 工作流中的“只验证改动文件”

在 `deploy-production.yml` 里，设计是“只验证本次发布改动的文件”：

- 步骤 **Get changed files since last tag** 会生成 `temp/changed_files.txt`（相对上一个 tag 的改动文件列表）。
- 若存在上一 tag 且 `temp/changed_files.txt` 存在，则执行：  
  `python scripts/validate_api_contracts.py --changed-files temp/changed_files.txt`
- 若没有上一 tag 或没有该文件，则执行：  
  `python scripts/validate_api_contracts.py`（**验证全部 49 个 router 文件**）。

因此出现大量问题的常见情况：

- **首次按 tag 发布**（没有上一 tag）→ 会验证全部文件 → 155 个错误。
- **本次 tag 与上一 tag 之间改动了大量 router 文件** → 这些文件里本身就有很多 HTTPException/未用 error_response → 同样会报大量错误。

---

## 4. 可选方案

### 方案 A：临时放宽门禁（先让部署通过）

在 **不修改业务代码** 的前提下，让“Validate API Contracts”不阻断部署：

- 在 `deploy-production.yml` 的 **Validate API Contracts (Release Gate)** 步骤中为该步骤加上 `continue-on-error: true`，或  
- 把该步骤改为“只报告失败，不令 job 失败”（具体依你希望是“本 job 仍算成功”还是“本 job 失败但后续 deploy 仍执行”而定；通常用 `continue-on-error: true` 即可先恢复部署）。

**优点**: 立刻恢复部署。  
**缺点**: 不再强制阻止“不符合契约”的代码合入/发布，需靠后续排期还技术债。

### 方案 B：从根上满足契约（推荐中长期）

按脚本要求逐步改造 router：

- 将 `raise HTTPException(...)` 改为使用 `backend.utils.api_response` 的 `error_response(...)`（并视情况补全 `recovery_suggestion`、日志等）。
- 先改本次发布涉及或最常改动的 router，再逐步覆盖全部 49 个文件。

这样无需放宽门禁，部署时 API 契约验证会自然通过。

### 方案 C：保持门禁，但仅在“有上一 tag 且只验证改动”时严格失败

保持当前逻辑不变：

- 有上一 tag 且存在 `temp/changed_files.txt` 时，仅对改动文件运行 `validate_api_contracts.py --changed-files temp/changed_files.txt`。
- 无上一 tag 或没有改动文件列表时，仍会验证全部文件；若你希望“首次 tag 发布不因历史债失败”，可再单独为“无上一 tag”分支改为 `continue-on-error: true` 或跳过全量验证（需改 workflow）。

---

## 5. 本地复现与自检

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
python scripts/validate_api_contracts.py
```

- 退出码 0：当前（全量）验证通过。  
- 退出码 1：存在错误，与 CI 中“验证全部文件”时的失败一致。

仅验证指定文件示例：

```powershell
python scripts/validate_api_contracts.py --files backend/routers/account_management.py
```

---

## 6. 小结

| 项目           | 说明 |
|----------------|------|
| GitHub CLI     | 本机未安装；不影响 GitHub Actions 部署，仅影响本地使用 `gh`。 |
| 部署失败原因   | API 契约验证步骤发现 155 个错误（主要为未使用 error_response）。 |
| 快速恢复部署   | 给“Validate API Contracts”步骤加 `continue-on-error: true`。 |
| 长期建议       | 按契约将 router 中 HTTPException 改为 error_response，并补全日志与 recovery_suggestion。 |

如需，我可以根据你选的方案（A/B/C）直接给出对 `deploy-production.yml` 或某个 router 的具体修改片段。
