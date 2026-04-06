新电脑迁移建议包内容

必带：
- `C:\Users\18689\.codex\skills\`
- `C:\Users\18689\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`

建议一起带：
- `C:\Users\18689\.codex\superpowers\`
- `C:\Users\18689\.codex\rules\`

不要默认直接迁移：
- `C:\Users\18689\.codex\auth.json`
- `C:\Users\18689\.codex\sessions\`
- `C:\Users\18689\.codex\sqlite\`
- `C:\Users\18689\.codex\logs_1.sqlite*`
- 仓库里的 `.env`
- 各平台账号密码、cookies、storage state、浏览器 profile

原因：
- 上述内容要么是账号敏感信息，要么强依赖机器路径和本地状态，不适合直接整包迁移。

新电脑验收重点：
- `python --version`
- `node --version`
- `npm --version`
- `npx playwright --version`
- `Get-Command pwcli,pwsnap,pwnote,pwshot,pwpack`
- `Get-ChildItem $HOME\\.codex\\skills -Directory`
