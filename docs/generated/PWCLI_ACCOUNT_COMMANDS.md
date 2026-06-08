# PWCLI 账号命令清单

> 自动生成文件，请勿手工修改。
> 刷新命令: `python scripts/generate_pwcli_account_commands.py`
> 生成时间: `2026-05-30 05:16:23 UTC`
> 数据来源: `postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp` 中的 `core.main_accounts where enabled = true`

本文档提供给业务同事直接复制使用。

规则:

1. 先执行“打开命令”
2. 在打开的浏览器里人工巡店、人工操作
3. 操作结束后执行“保存命令”
4. 如需确认路径是否正确，可执行“检查命令”

注意:

1. 同一平台下，不同账号不能使用同一个 `WorkTag`
2. 本清单已为每个账号分配固定 `WorkTag`，直接复制即可
3. 必须使用这里的正式 `AccountId`，不要改成旧店铺名、旧别名或历史用户名

## 通用模板

Shopee:

```powershell
Open-PwcliShopee -WorkTag <fixed-worktag> -AccountId '<main-account-id>'
Save-PwcliShopeeState -AccountId '<main-account-id>'
Show-PwcliPaths -Platform shopee -AccountId '<main-account-id>' -WorkTag <fixed-worktag>
```

TikTok:

```powershell
Open-PwcliTiktok -WorkTag <fixed-worktag> -AccountId '<main-account-id>'
Save-PwcliTiktokState -AccountId '<main-account-id>'
Show-PwcliPaths -Platform tiktok -AccountId '<main-account-id>' -WorkTag <fixed-worktag>
```

妙手:

```powershell
Open-PwcliMiaoshou -WorkTag <fixed-worktag> -AccountId '<main-account-id>'
Save-PwcliMiaoshouState -AccountId '<main-account-id>'
Show-PwcliPaths -Platform miaoshou -AccountId '<main-account-id>' -WorkTag <fixed-worktag>
```

## 账号总表

| 平台   | 显示名                               | AccountId                   | WorkTag                                    |
| ------ | ------------------------------------ | --------------------------- | ------------------------------------------ |
| 妙手   | xihong                               | `miaoshou_real_001`         | `miaoshou-miaoshou-real-001-inspect`       |
| Shopee | playwright_smoke_admin               | `accept_main_1775126941575` | `shopee-accept-main-1775126941575-inspect` |
| Shopee | shopee新加坡3C店                     | `chenewei666:main`          | `shopee-chenewei666-main-inspect`          |
| Shopee | hongxikeji:main                      | `hongxikeji:main`           | `shopee-hongxikeji-main-inspect`           |
| Shopee | Leslieshop:main                      | `shopee KR`                 | `shopee-shopee-kr-inspect`                 |
| TikTok | Tiktok 1店 (chenzewei666666@163.com) | `Tiktok 1店`                | `tiktok-tiktok-1-inspect`                  |
| TikTok | Tiktok 2店                           | `chenzeweinbnb@163.com`     | `tiktok-chenzeweinbnb-163-com-inspect`     |

## 妙手

### xihong

打开:

```powershell
Open-PwcliMiaoshou -WorkTag miaoshou-miaoshou-real-001-inspect -AccountId 'miaoshou_real_001'
```

保存:

```powershell
Save-PwcliMiaoshouState -AccountId 'miaoshou_real_001'
```

检查:

```powershell
Show-PwcliPaths -Platform miaoshou -AccountId 'miaoshou_real_001' -WorkTag miaoshou-miaoshou-real-001-inspect
```

## Shopee

### playwright_smoke_admin

打开:

```powershell
Open-PwcliShopee -WorkTag shopee-accept-main-1775126941575-inspect -AccountId 'accept_main_1775126941575'
```

保存:

```powershell
Save-PwcliShopeeState -AccountId 'accept_main_1775126941575'
```

检查:

```powershell
Show-PwcliPaths -Platform shopee -AccountId 'accept_main_1775126941575' -WorkTag shopee-accept-main-1775126941575-inspect
```

### shopee新加坡3C店

打开:

```powershell
Open-PwcliShopee -WorkTag shopee-chenewei666-main-inspect -AccountId 'chenewei666:main'
```

保存:

```powershell
Save-PwcliShopeeState -AccountId 'chenewei666:main'
```

检查:

```powershell
Show-PwcliPaths -Platform shopee -AccountId 'chenewei666:main' -WorkTag shopee-chenewei666-main-inspect
```

### hongxikeji:main

打开:

```powershell
Open-PwcliShopee -WorkTag shopee-hongxikeji-main-inspect -AccountId 'hongxikeji:main'
```

保存:

```powershell
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
```

检查:

```powershell
Show-PwcliPaths -Platform shopee -AccountId 'hongxikeji:main' -WorkTag shopee-hongxikeji-main-inspect
```

### Leslieshop:main

打开:

```powershell
Open-PwcliShopee -WorkTag shopee-shopee-kr-inspect -AccountId 'shopee KR'
```

保存:

```powershell
Save-PwcliShopeeState -AccountId 'shopee KR'
```

检查:

```powershell
Show-PwcliPaths -Platform shopee -AccountId 'shopee KR' -WorkTag shopee-shopee-kr-inspect
```

## TikTok

### Tiktok 1店 (chenzewei666666@163.com)

打开:

```powershell同意

```

保存:

```powershell
Save-PwcliTiktokState -AccountId 'Tiktok 1店'
```

检查:

```powershell
Show-PwcliPaths -Platform tiktok -AccountId 'Tiktok 1店' -WorkTag tiktok-tiktok-1-inspect
```

### Tiktok 2店

打开:

```powershell
Open-PwcliTiktok -WorkTag tiktok-chenzeweinbnb-163-com-inspect -AccountId 'chenzeweinbnb@163.com'
```

保存:

```powershell
Save-PwcliTiktokState -AccountId 'chenzeweinbnb@163.com'
```

检查:

```powershell
Show-PwcliPaths -Platform tiktok -AccountId 'chenzeweinbnb@163.com' -WorkTag tiktok-chenzeweinbnb-163-com-inspect
```

## 保存时机

只有在以下场景才建议保存:

1. 已经稳定进入后台首页
2. 已经完成验证码或二次验证
3. 当前页面不是登录页、报错页、验证页

不要在以下场景保存:

1. 刚打开还在跳转
2. 停留在登录页
3. 停留在验证码页
4. 页面明显异常

## 更新方式

本清单基于账号管理中的当前启用主账号自动生成。

当 `core.main_accounts` 中启用账号有新增、停用或重命名时，请执行:

```powershell
python scripts/generate_pwcli_account_commands.py
```
