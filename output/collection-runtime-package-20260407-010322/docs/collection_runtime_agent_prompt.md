你现在需要在采集环境电脑上接收一个“采集运行态迁移包”，目标是让这台机器短期内承担采集、排障、修复和验证工作。

重要原则：
1. 默认不要覆盖这台机器现有的 `.env`
2. 当前机器用户名可能不同
3. 当前机器可能没有 `F:\`，优先使用 `D:\AI_code\xihong_erp`，没有 `D:\` 再使用 `C:\AI_code\xihong_erp`
4. PowerShell profile 中如果存在旧仓库路径，必须自动改为新路径

请按下面步骤执行。

第一步：探测目标路径和仓库位置

```powershell
$repoRoot = if (Test-Path "D:\") { "D:\AI_code\xihong_erp" } else { "C:\AI_code\xihong_erp" }
$profilePath = $PROFILE
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }

Write-Host "REPO_ROOT=$repoRoot"
Write-Host "PROFILE=$profilePath"
Write-Host "CODEX_HOME=$codexHome"
```

第二步：接收迁移包并落地

假设我给你的 zip 里包含这些内容：
- `profiles\`
- `output\playwright\profiles\`
- `output\playwright\state\`
- `output\playwright\work\`
- `temp\component_tests\`
- `temp\test_results\`
- `.playwright-cli\`
- `accounts.enc`
- `account_key.key`
- `secure_accounts.enc`
- `secure_account_key.key`
- `local_accounts.py`
- `docs\collection_runtime_transfer_manifest.md`

把这些内容复制到 `$repoRoot` 下对应的原相对路径。

如果目标文件已存在：
- 先备份为 `*.bak-时间戳`
- 再覆盖

第三步：处理 `.env`

规则如下：
- 如果 `$repoRoot\.env` 已存在，不要直接覆盖
- 只有我明确再提供 `.env` 或要求你合并时，才处理 `.env`
- 如果发现代码运行缺少环境变量，请告诉我缺少哪些键，不要擅自猜测

第四步：修复 PowerShell profile 中的旧路径

请检查 `$PROFILE` 中是否有类似旧路径：
- `F:\Vscode\python_programme\AI_code\xihong_erp`

如果有，请替换为新的 `$repoRoot`。

重点检查这些函数或别名中的路径：
- `pwcli`
- `pwcli-script`
- `Get-PwcliProjectRoot`
- `pwcap`
- `pwpack`

第五步：验证

重新打开一个新的 PowerShell 会话，再执行：

```powershell
$repoRoot = if (Test-Path "D:\AI_code\xihong_erp") { "D:\AI_code\xihong_erp" } else { "C:\AI_code\xihong_erp" }

Get-Command pwcli,Open-PwcliMiaoshou,Open-PwcliShopee,Open-PwcliTiktok,Save-PwcliMiaoshouState,Save-PwcliShopeeState,Save-PwcliTiktokState,Show-PwcliPaths,pwsnap,pwnote,pwshot,pwpack -ErrorAction SilentlyContinue | Select-Object Name,CommandType,Source

Test-Path (Join-Path $repoRoot "profiles")
Test-Path (Join-Path $repoRoot "output\playwright\profiles")
Test-Path (Join-Path $repoRoot "output\playwright\state")
Test-Path (Join-Path $repoRoot "output\playwright\work")
Test-Path (Join-Path $repoRoot "accounts.enc")
Test-Path (Join-Path $repoRoot "local_accounts.py")
```

最后给我一份简短报告：
1. 实际仓库路径
2. 已迁移的目录和文件
3. 是否保留了本机原 `.env`
4. PowerShell profile 是否已改成新路径
5. 还缺什么
