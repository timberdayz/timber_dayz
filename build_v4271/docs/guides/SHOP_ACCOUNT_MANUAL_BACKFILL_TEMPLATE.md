# 店铺账号人工回填模板

适用场景：

- 已通过 `pwcli + agent + snapshot` 看到了平台页面中的标准店铺名
- 已确认主账号可以登录
- 需要把店铺信息人工回填到账号管理

## 字段填写标准

| 字段 | 填写规则 |
|---|---|
| `main_account_id` | 人工确认的主账号登录主体 |
| `shop_account_id` | 系统内部稳定机器 ID，推荐规则：`<platform>_<region>_<store_slug>[_<shop_type>]` |
| `store_name` | 平台页面真实可见的标准店铺名 |
| `platform_shop_id` | 平台真实运行时店铺标识；属于可选增强字段，没有也不阻塞回填 |
| `shop_region` | 平台页面或切店器可见区域，例如 `SG` / `MY` / `PH` |
| `shop_type` | 人工盘点确认，例如 `local` / `global` / `special` |
| `status` | `待确认` / `可回填` / `可回填（平台店铺ID可选待补）` |
| `evidence` | 对应 snapshot 文件路径 |

## 回填流程

1. 先确认 `main_account_id`
2. 从切店器 snapshot 读取页面标准店铺名
3. 逐个切换店铺，能补到 `platform_shop_id` 就补，补不到也先不阻塞
4. 生成 `shop_account_id`
5. 先形成草单
6. 人工确认无误后，再回填系统

---

## Shopee 草单

### 主账号候选

- `main_account_id`: `chenewei666:main`

### 已识别店铺

| platform | main_account_id | shop_account_id | store_name | platform_shop_id | shop_region | shop_type | status | evidence |
|---|---|---|---|---|---|---|---|---|
| `shopee` | `chenewei666:main` | `shopee_sg_chenewei666_local` | `chenewei666.sg` | `1227491331` | `SG` | `local` | `可回填` | `output/playwright/work/shopee/products-export/01-homepage-ready.md` |
| `shopee` | `chenewei666:main` | `shopee_sg_zewei_toys_local` | `zewei_toys.sg` | `1407964586` | `SG` | `local` | `可回填` | `output/playwright/work/shopee/analytics-export/4-shop-swicth-detail-open.md` |

### 说明

- `chenewei666.sg` 已从 URL 明确取得 `cnsc_shop_id=1227491331`
- `zewei_toys.sg` 已人工确认 `cnsc_shop_id=1407964586`，系统中已补录为 `manual_confirmed`

---

## TikTok 草单

### 主账号

- 当前 snapshot 未直接给出稳定 `main_account_id` 文本，需按现有主账号配置人工确认

### 已识别店铺

| platform | main_account_id | shop_account_id | store_name | platform_shop_id | shop_region | shop_type | status | evidence |
|---|---|---|---|---|---|---|---|---|
| `tiktok` | `待确认` | `tiktok_sg_hx_home_local` | `Singapore(HX Home)` |  | `SG` | `local` | `待确认` | `output/playwright/work/tiktok/login-2store/20-shop-switch-before.md` |
| `tiktok` | `待确认` | `tiktok_my_flora_mall_local` | `Malaysia(Flora Mall)` |  | `MY` | `local` | `待确认` | `output/playwright/work/tiktok/login-2store/22-shop-switch-2-open.md` |
| `tiktok` | `待确认` | `tiktok_ph_daju_mall_local` | `Philippines(DAJU Mall)` |  | `PH` | `local` | `待确认` | `output/playwright/work/tiktok/login-2store/23-shop-switch-3-open.md` |

### 说明

- 当前 TikTok 录制证据已能看到区域 + 页面标准店铺名
- 抽查 snapshot 尚未看到类似 Shopee `cnsc_shop_id` 这样的明确平台店铺 ID；因此应优先以 `shop_account_id + store_name` 回填
- TikTok 的 `main_account_id` 需要从你们当前账号配置中人工确认

---

## 当前数据库现状

以下是当前系统里已经存在、后续很可能需要“改名/归并/补充”的记录：

### Shopee

| 当前 shop_account_id | 当前 main_account_id | 当前 store_name | enabled | 备注 |
|---|---|---|---|---|
| `shopee新加坡3C店` | `chenewei666:main` | `shopee新加坡3C店` | `true` | 很可能对应本轮草单中的 `chenewei666.sg`，但仍需人工确认 |
| `虾皮巴西（东朗照明主体）` | `huangjiaju:main` | `虾皮巴西（东朗照明主体）` | `true` | 与本轮 Shopee 新加坡切店草单无直接冲突 |

### TikTok

| 当前 shop_account_id | 当前 main_account_id | 当前 store_name | enabled | 备注 |
|---|---|---|---|---|
| `Tiktok 2店` | `chenzeweinbnb@163.com` | `Tiktok 2店` | `true` | 很可能属于本轮 `login-2store` 录制链路，但需人工确认是否应承接 `Singapore(HX Home)` / `Malaysia(Flora Mall)` / `Philippines(DAJU Mall)` |
| `Tiktok 1店` | `chenzewei666666@163.com` | `Tiktok 1店` | `false` | 历史记录，是否保留待业务确认 |
| `Tiktok 3店` | `15014006608@163.com` | `Tiktok 3店` | `false` | 历史记录，是否保留待业务确认 |
| `Tiktok 4店` | `Zhongwangnbx@163.com` | `Tiktok 4店` | `false` | 历史记录，是否保留待业务确认 |

---

## 待确认项

### Shopee

- 无

### TikTok

- 当前主账号的正式 `main_account_id`
- 每个店铺是否都归类为 `local`
- 是否存在平台真实店铺 ID 可从 URL、接口响应或页面 DOM 补取
