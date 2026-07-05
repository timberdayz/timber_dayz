# PWCLI 人工巡店与会话复用指南

本文档定义在现有正式采集会话复用规则基础上，如何使用 `pwcli` 进行人工巡店、人工维护账号会话，以及让正式采集复用人工维护后的高质量会话。

## 适用范围

- 平台: `shopee`、`tiktok`、`miaoshou`
- 规则: 所有平台统一适用
- 目标人群: 需要手动打开店铺后台、巡店检查、少量人工操作的业务或运营同事

## 核心原则

1. 不新建第二套会话规则。人工巡店与正式采集共用同一套账号级会话路径。
2. 对于主账号 + 多店铺模型，正式采集复用的会话 owner 以 `main_account_id` 为准。
3. 人工巡店必须显式带 `AccountId` 打开和保存会话，不允许再依赖旧的临时路径或历史别名。
4. 人工巡店是“人工维护会话”的入口，不是批量自动化巡店器。
5. 同一主账号不要同时被人工巡店和正式采集并发使用。

## 正式采集当前规则

当前正式采集已经按以下规则复用会话:

- 任务侧传入的是店铺账号，如 `shop_account_id`
- 运行时将会话归属解析到 `main_account_id`
- 会话文件走:
  - `data/sessions/<platform>/<main_account_id>/storage_state.json`
- 持久 profile 走:
  - `profiles/<platform>/<main_account_id清洗后目录>`

以 Shopee 为例:

- 主账号: `hongxikeji:main`
- 会话文件: `data/sessions/shopee/hongxikeji:main/storage_state.json`
- 持久 profile: `profiles/shopee/hongxikejimain`

这意味着，人工巡店只要按 `main_account_id` 打开并保存会话，后续该主账号下的正式采集就可以直接复用。

## 推荐操作方式

### 0. 本地网页巡店面板（推荐）

日常人工巡店优先使用本地网页巡店面板，减少复制命令、手写 `AccountId` 和 `WorkTag` 的重复操作。

```powershell
python scripts\pwcli_inspection_panel.py
```

面板会自动打开 `http://127.0.0.1:<port>/?token=<一次性token>`，只允许本机访问。点击账号卡片里的“打开巡店”后，在浏览器里人工巡店、关闭弹窗、处理验证；确认页面稳定后，回到面板勾选保存前检查项并点击“保存会话”。

巡店面板只负责打开账号会话、等待人工确认后保存。它不会自动点击页面、关闭弹窗或处理验证码。在页面停留于登录页、验证页、报错页或明显异常页时，请选择“跳过/清除状态”。

如果网页面板不可用，可使用 CLI 菜单兜底:

```powershell
. .\scripts\pwcli_helpers.ps1
Start-PwcliDailyInspection
```

手动复制命令仍保留为兜底方式，见 `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`。

### 1. 打开主账号会话

Shopee:

```powershell
Open-PwcliShopee -WorkTag hongxi-main-manual -AccountId 'hongxikeji:main'
```

TikTok:

```powershell
Open-PwcliTiktok -WorkTag <work-tag> -AccountId '<main-account-id>'
```

妙手:

```powershell
Open-PwcliMiaoshou -WorkTag <work-tag> -AccountId '<main-account-id>'
```

要求:

- `WorkTag` 用于区分本次人工巡店窗口，建议使用固定可读名称
- 同一平台下，不同账号必须使用不同的 `WorkTag`，否则会话 session 会串
- `AccountId` 必须使用正式账号管理里的主账号标识，不要使用旧别名、旧店铺名、旧临时用户名
- 业务同事日常复制命令时，应优先使用自动生成清单:
  - `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`

### 2. 人工巡店和人工操作

允许行为:

- 人工查看首页、店铺后台、运营看板、商品页、订单页
- 人工切店铺
- 人工执行少量正常后台操作
- 人工处理登录、二次验证、验证码

不建议行为:

- 以固定节奏快速切多个账号
- 打开后立即连续大量点击
- 一次性轮询大量主账号
- 用人工巡店窗口做批量自动脚本操作

### 3. 在稳定页面保存会话

操作完成后，确认当前页面已经稳定进入后台首页或正常业务页面，再保存:

Shopee:

```powershell
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
```

也可以显式按 session 保存:

```powershell
pwcli --session shopee-hongxi-main-manual state-save
```

保存前不要停留在以下页面:

- 登录页
- 验证码页
- 二次校验页
- 报错页
- 强制重新认证页

### 4. 让正式采集复用

人工保存成功后，不需要再做额外同步。正式采集会按现有 runtime 规则读取该主账号会话并复用。

## Shopee 推荐命令模板

### 首次按新标准手动登录并保存

```powershell
Open-PwcliShopee -WorkTag hongxi-main-refresh -AccountId 'hongxikeji:main'
```

人工登录成功后:

```powershell
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
```

### 日常人工巡店

```powershell
Open-PwcliShopee -WorkTag hongxi-main-inspect -AccountId 'hongxikeji:main'
```

巡店完成后:

```powershell
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
```

### 检查路径是否正确

```powershell
Show-PwcliPaths -Platform shopee -AccountId 'hongxikeji:main' -WorkTag hongxi-main-inspect
```

## 风控与封禁风险

`pwcli` 底层仍然是 Playwright 控制浏览器，因此不能把它视为“绝对等同于普通人工 Chrome/Edge”。

风险主要来自以下几类问题:

1. 同一账号的浏览器环境漂移太大。
2. 同一账号短时间内频繁切换网络、机器、profile。
3. 同一账号被人工巡店和正式采集并发使用。
4. 虽然是 `pwcli` 打开的窗口，但实际执行的是批量自动化操作。
5. 在异常页面保存低质量会话，导致后续频繁重登和重复验证。

降低风险的建议:

1. 一个主账号固定绑定一套会话目录和持久 profile。
2. 尽量固定机器、固定网络、固定地区环境。
3. 人工巡店与正式采集尽量错峰。
4. 打开后以人工节奏操作，不做脚本式高速点击。
5. 出现验证码、二验、登录保护时，优先人工完成后再重新保存。
6. 不混用旧会话路径与新标准路径。

## 禁止事项

1. 不要再把旧店铺名、旧历史用户名、旧平台别名当成新的正式 `AccountId`。
2. 不要将 `pwcli` 无 `AccountId` 的临时探索会话当成正式采集会话来源。
3. 不要同时打开同一主账号的多个人工巡店窗口并分别保存。
4. 不要在同一主账号正式采集中途手动覆盖会话。
5. 不要把历史遗留目录 `temp/sessions/...` 当成正式会话来源。

## 历史遗留说明

仓库里仍可能存在旧式会话资产，例如:

- `temp/sessions/...`
- 旧店铺名目录
- 旧账号别名目录

这些历史资产只作为排障线索，不作为新的正式会话标准。若需要继续使用某个历史账号，应该按新的 `main_account_id` 规则重新手动登录一次并覆盖保存。

## 什么时候需要重新手动登录

出现以下任一情况时，建议重新手动登录并保存:

- 打开后回到登录页
- 打开后跳到安全验证页
- 正式采集连续提示会话失效
- 主账号刚改过密码
- 平台强制要求重新认证
- 更换了固定巡店机器或网络环境

## 与正式采集的边界

人工巡店复用正式采集的会话体系，但不改变正式采集本身的 runtime 规则。

本指南只定义:

- 人怎么打开
- 人怎么保存
- 什么时候允许保存
- 什么时候不该覆盖
- 如何降低风控风险

正式采集是否读取、如何解析 `main_account_id`、如何构建 runtime context，仍以当前后端实现为准。

## 相关文档

- `docs/guides/PWCLI_COMMAND_REFERENCE.md`
- `docs/generated/PWCLI_ACCOUNT_COMMANDS.md`
- `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`
- `docs/guides/MAIN_SHOP_ACCOUNT_CUTOVER_RUNBOOK.md`
