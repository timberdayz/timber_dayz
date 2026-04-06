采集运行态迁移包说明

默认目标：
- 让采集环境电脑在短期内承担“采集 + 排障 + 修复 + 验证”工作
- 不默认覆盖采集环境现有 `.env`

默认包含：
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

可选包含：
- `.env`

`.env` 处理原则：
- 如果采集环境机器已有可工作的 `.env`，默认保留采集环境自己的版本
- 不要直接用开发环境 `.env` 覆盖采集环境 `.env`
- 只有在明确确认缺少某些键时，才做逐项补充或人工合并
- 更安全的做法是迁移：
  - `.env.example`
  - `env.example`
  - `env.development.example`
  - `env.production.example`
  让目标机器 agent 对照检查，而不是直接覆盖

目标机器落地建议：
- 仓库根目录：`D:\AI_code\xihong_erp`，若无 D 盘则用 `C:\AI_code\xihong_erp`
- 所有 profile / state / work 目录都落回仓库内原相对路径

额外注意：
- PowerShell profile 中当前 `pwcli` 函数写死了旧路径，需要目标机器 agent 改成新仓库路径
- 浏览器持久化 profile 体积可能较大，复制前确保目标机器有足够空间
