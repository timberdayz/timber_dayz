# 采集会话复用与店铺身份统一 —— 设计规格

- 日期：2026-11-01
- 状态：**业务已确认方向**（v3，含 4 项业务拍板结论，见 §11.1）；待进入实施计划
- 范围：`modules/utils/pwcli_native.py`、`scripts/pwcli*.{py,ps1}`、`scripts/pwcli_inspection_panel_static/index.html`、`modules/utils/sessions/session_manager.py`、`modules/apps/collection_center/*`、`backend/services/data_ingestion_service.py`、`sql/semantic/*`、`backend/domains/collection/routers/shop_account*.py`、`backend/utils/text_normalization.py`、`frontend/src/domains/platform/views/AccountManagement.vue`
- 关联文档：`docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md`、`docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md`
- 迁移落点：`current_migrations/versions/`（活动迁移集；`migrations/versions/` 为历史集，本轮不动）

---

## 1. 要解决的业务问题

两件事互相咬合：

**A. 人工巡店保存下来的会话，采集根本用不上。**
运营在本地巡店面板里逐个账号登录、确认店铺、点「保存会话」，本意是让后续采集直接复用这份"人已经用过的登录态"，少弹验证码、少重复登录。实测结果是：**保存动作实际失败，但面板始终显示「保存成功」**；而且即使保存成功，下次打开也读不到（读写路径不一致）。

**B. 店铺身份靠"名字"认，多地同名必然张冠李戴。**
未来会在 TikTok 开多个地区的同名品牌店（例如三个地区都叫 `FIORO`）。当前系统把"店铺名"同时当成展示名和匹配键，一旦同名，多店数据会全部归到其中一个店，订单重复入账、月度结算出错。

两件事必须一起设计：**会话复用决定"采集拿到的是哪个账号的登录态"，店铺身份决定"采回来的数据算哪个店的"。**

---

## 2. 已实测确认的事实（设计依据）

### 2.1 巡店会话链路：五个断点

#### 断点 A —— 面板「保存会话」根本定位不到浏览器会话（主因）

链路的 session 名是**按账号**拼出来的：

```
scripts/pwcli_account_inventory.py:54-55   work_tag(platform, account_id) = f"{slugify(platform)}-{slugify(account_id)}-inspect"
scripts/pwcli_helpers.ps1:164              $session = "$platformName-$WorkTag"      # 例：shopee-shopee-hongxikeji-main-inspect
scripts/pwcli_helpers.ps1:167              $env:PLAYWRIGHT_CLI_SESSION = $session
scripts/pwcli_helpers.ps1:178              pwcli --session $session open $Url --headed --account-id $AccountId
```

但保存时：

```
scripts/pwcli_helpers.ps1:204-212
    if ($AccountId) {
        $session = Get-PwcliActiveSession      # 只读 $env:PLAYWRIGHT_CLI_SESSION
        if ($session) { pwcli --session $session state-save }
        else          { pwcli state-save }     # ← 走这里
        return
    }
```

**`$AccountId` 传进来了，却完全没被用于定位会话。**
面板每次动作都起一个全新的 PowerShell 进程（`scripts/pwcli_inspection_panel.py:54-68` `run_subprocess_command`），`$env:PLAYWRIGHT_CLI_SESSION` 不在进程环境里 → `Get-PwcliActiveSession` 返回空 → 落到 `pwcli state-save` → session 被解析为 `"default"` → `require_session("default")` 抛 `SystemExit("No browser session found for 'default'")`（`modules/utils/pwcli_native.py:653-656`）。

实测复现：

```
Save-PwcliShopeeState -AccountId 'hongxikeji:main'
→ No browser session found for 'default'
→ exit code = 0
```

#### 断点 B —— 退出码不传播，失败被当成成功

```
scripts/pwcli.ps1:6-7
    $ScriptPath = Join-Path $PSScriptRoot "pwcli_native.py"
    & python $ScriptPath @CliArgs          # ← 结尾没有 exit $LASTEXITCODE
```

`Open-PwcliPlatform` / `Save-PwcliPlatformState` 都不检查 `$LASTEXITCODE`；面板 `scripts/pwcli_inspection_panel.py:183` 只看 `result.exit_code != 0` → **永远为假 → 面板永远显示 opened/saved 成功**。

实测：

```
pwcli --session no-such-session-xyz state-save
→ No browser session found for 'no-such-session-xyz'
→ exit code = 0
```

配套：`scripts/pwcli_inspection_panel_static/index.html:320` 的日志只渲染 `result.status`，**不渲染含真实 stdout/stderr 的 `result.message`** → 失败原因对用户完全不可见。

#### 断点 C —— 读写路径不一致：写用净化名，读用原始名

| 方向 | 代码 | 实际路径 |
|---|---|---|
| **写** | `SessionManager.save_session` → `_safe_filename(account_id)`（`modules/utils/sessions/session_manager.py:211`） | `data/sessions/shopee/hongxikeji_main/storage_state.json` |
| **读** | `runtime_account_state_path`（`modules/utils/pwcli_native.py:167-175`，用**原始 account_id**） | `data/sessions/shopee/hongxikeji:main/storage_state.json` |

磁盘上只存在前者 → **即使面板保存成功，下次打开仍读不到，每次都要重新登录**。
读取发生在 `launch_browser` 的 `maybe_load_default_storage_state(context, metadata)`（`pwcli_native.py:643`）。

> 注：session 与 profile 目录名不同（`hongxikeji_main` vs `hongxikejimain`）是**既定设计**，`backend/tests/test_session_storage_roots.py:30-31` 已断言，不要动。要统一的是**读写两侧用同一个净化函数**。

#### 断点 D —— 直接调用入口缺 `sys.path` 兜底（影响面比原先估计小）

`modules/utils/pwcli_native.py:320` 的延迟导入 `from modules.utils.sessions.session_manager import SessionManager`，只有在 `default_state_mode == "session_manager"`（即传入 `--account-id`，见 `pwcli_native.py:191-196`）时才会执行。

生产链是 `scripts/pwcli.ps1:6-7` → **`scripts/pwcli_native.py`**（一个 10 行的 shim，第 4 行 `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`）→ 以库方式 import `modules.utils.pwcli_native`。
**这条链路 `sys.path` 含仓库根，import 正常。**

所以只有**直接以 `python modules/utils/pwcli_native.py …` 启动**（或 `python -m modules.utils.pwcli_native`）才会抛 `ModuleNotFoundError: No module named 'modules'`：

```
python modules/utils/pwcli_native.py --session shopee-shopee-leslieshop-main-inspect \
  open "https://seller.shopee.cn/" --headed --account-id "Leslieshop:main"
  File "pwcli_native.py", line 646, in launch_browser
    save_default_storage_state_from_context(metadata, context)
  File "pwcli_native.py", line 320
    from modules.utils.sessions.session_manager import SessionManager
ModuleNotFoundError: No module named 'modules'
```

该导入确由 2026-04-01 提交 `662d3c13` 引入（`git log -S` 可证），但**"面板保存链路已坏 7 个月"这个归因不成立**——面板的保存失败是断点 A + B 造成的，与它无关。断点 D 仍要修（直接调用是公开入口），但优先级低于 A/B/C。

#### 断点 E —— `slugify` 丢弃全部非字母数字，中文账号名互相塌陷

```
scripts/pwcli_account_inventory.py:48-51
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower())
```

`虾皮巴西（东朗照明主体）` 与 `验证码测试账号` 都被 slug 成 `account` → work_tag 相同 → session 名相同 → `command_open`（`pwcli_native.py:705-708`）在打开时杀掉同名 session → **账号之间互相踢掉浏览器窗口、互相覆盖 storage_state**。这是 ③④ 两项的共同根因。

### 2.2 巡店与采集确实共用同一套目录（这部分是对的，不要动）

- `modules/utils/pwcli_native.py:163-164` `runtime_account_profile_dir`（`session_manager_safe_token` 净化）与 `SessionManager.get_persistent_profile_path` 净化规则一致 → 巡店与采集共用同一 profile 目录（实测 `profiles/shopee/hongxikejimain` 存在且与 live session 一致）。
- `pwcli_native.py:310-333` `save_default_storage_state_from_context` → `SessionManager.save_session` → 写入路径与采集读路径一致。
- `SessionManager.save_session` 的保护逻辑（`session_manager.py:417-436`、`:450-464`）：**已 protected 的人工会话不会被打开时的自动回写覆盖**（`old_protected and not incoming_manual` → 保留旧 state）。这条是对的，要保留。

**结论：不需要重做会话存储设计，只需要把断掉的五处接上。**

### 2.3 一处"名字"被塞进三个概念

`core.shop_accounts.store_name` 现在存的是**平台侧真实店名**：

| 平台 | store_name 样例 | platform_shop_id | shop_region |
|---|---|---|---|
| tiktok（6 个） | `DAWIE Mall`、`Malaysia(Flora Mall)`、`Singapore(HX Home)` … | **全部 NULL**（0/6，status=missing） | 6/6 有值 |
| shopee（13 个 enabled） | `xhkj1.my`、`xhkj11.sg`、`hx_home.ph` … | 13/13 有值 | 13/13 有值 |
| miaoshou（1 个） | `xihong` | NULL | `''`（空串） |

而 `core.shop_account_aliases` 存的是**内部中文标签**，不是平台店名：

```
('tiktok', 'TK菲律宾1店', '菲律宾1店', 'Explorers Mall',    'PH', primary=True,  active=True)   -- id=20
('tiktok', 'TK马来1店',   '马来1店',   'DAWIE Mall',        'MY', primary=True,  active=True)   -- id=18
('shopee', 'Shopee马来3店','马来3店',   'xhkj13.my',         'MY', primary=True,  active=True)
```

> 元组第 4、5 列是 `join core.shop_accounts` 派生的（别名表本身**没有** `store_name` / `shop_region` 列）。

**关键实测：妙手 ERP 导出文件的「店铺」列，填的就是我们自己的中文别名。**
`b_class.fact_tiktok_orders_monthly`（4662 行）按 **`raw_data->>'店铺'` / `raw_data->>'站点'`** 取值：

```
('TK菲律宾1店', '菲律宾', 2171)   ('TK新加坡1店', '新加坡', 1427)
('TK马来1店',   '马来',   503)    ('TK菲律宾2店', '菲律宾',  279)
('TK新加坡2店', '新加坡',  120)   ('TK新加坡3C店','新加坡',   88)
('TK马来2店',   '马来',    74)
```

> 物化列 `"店铺"/"站点"` 与 `raw_data` 取值**不一致**（物化列含 191 行 NULL，且分布为 2029/1394/501/277/191/115/82/73）→ **该断言只能用 `raw_data` 取值**。

`raw_data` 里真正的身份相关字段只有 4 个键：

```
main_account_id  2751 行（59%），取值全部 = 'miaoshou_real_001'（妙手主账号，对 TikTok 无区分度）
shop_account_id  2751 行，取值全部 = 同一个
store_name       2751 行，取值全部 = 'xihong'
shop_id          4662 行，取值全部 = 'xihong'
```

**所以 TikTok 订单在 raw 层唯一可用、且真正起作用的店铺身份，就是妙手导出的「店铺」列（= 别名值）+「站点」列（= 区域）。** live 语义层的解析结果反向印证：

```
semantic.fact_orders_atomic (tiktok):
  tiktok_ph_explorers_mall_local  2473   <- 'TK菲律宾1店'
  tiktok_sg_daone_mall_local       1448   <- 'TK新加坡1店'
  tiktok_my_dawie_mall_local        505   <- 'TK马来1店'
  tiktok_ph_daju_mall_local          289   <- 'TK菲律宾2店'
  tiktok_sg_hx_home_local            124   <- 'TK新加坡2店'
  tiktok_my_flora_mall_local          75   <- 'TK马来2店'
  unknown                              90   <- 'TK新加坡3C店'（别名表里没有这个标签）
```

### 2.4 别名机制的两个真 bug

**Bug A —— 写侧与查侧规范化规则不一致。**

| 侧 | 规则 | `TK-新加坡-1店` 的结果 | `Malaysia(Flora Mall)` 的结果 |
|---|---|---|---|
| 写侧（Python，`backend/utils/text_normalization.py:68-76` `normalize_alias_key`） | 小写 + 折叠空白 + 剥平台前缀 + strip，**不删分隔符** | `-新加坡-1店`（前导连字符保留） | `malaysia(flora mall)` |
| 查侧（SQL，`sql/semantic/orders_atomic.sql:467`、`shop_identity_resolution_candidates.sql:70-80`） | 剥前缀 + 删 `[[:space:]_()/-]+` | `新加坡1店` | `malaysiafloramall` |

→ **认领了也可能永远匹配不上。**
现在 21 条别名恰好都是无分隔符的中文标签（`TK菲律宾1店` → `菲律宾1店`），两侧结果碰巧相同，才没暴露。

**Bug B —— 平台代码大小写分裂，唯一约束形同虚设。**
别名表里 `platform` 同时存在 `'Shopee'` / `'shopee'` / `'Tiktok'` / `'tiktok'` 四种写法：

```
('Shopee', '3C店',       '3c店', 'chenewei666.sg',         SG, primary=False, active=False)   -- id=1
('shopee', 'Shopee3C店', '3c店', 'zewei_toys.sg',          SG, primary=True,  active=True)    -- id=14
('Tiktok', '菲律宾1店',  '菲律宾1店', 'Philippines(DAJU Mall)', PH, primary=False, active=False) -- id=21
('tiktok', 'TK菲律宾1店','菲律宾1店', 'Explorers Mall',     PH, primary=True,  active=True)    -- id=20
```

唯一约束是 `UniqueConstraint("platform","alias_normalized","is_active")`（`modules/core/db/schema_parts/platform.py:227`）—— **大小写敏感，所以 `'Shopee'` 和 `'shopee'` 可以同时 active 一个 `3c店`**。一旦统一大小写，现有数据立刻冲突。

> 范围修正：**只有别名表**存在大小写分裂。`core.shop_accounts.platform` = {miaoshou, shopee, tiktok, 验证码测试账号}、`core.main_accounts.platform` 已全小写。

**附带**：`UniqueConstraint` 使得**同平台同一别名只能 active 一条** → 三个 `FIORO` 不可能同时归给三个店。**别名必须引入区域维度**。

### 2.5 live 语义层有四套并存的解析逻辑，且都带 `LIMIT 1`

| 语义对象 | 类型 | 来源文件 | 解析方式 | raw 里有站点吗 |
|---|---|---|---|---|
| `semantic.fact_orders_atomic` | VIEW | `sql/semantic/orders_atomic.sql`（2026-06-09） | `LATERAL` 扫 `core.shop_accounts`，条件 **`store_name` 等值 OR `platform_shop_id` 等值 OR 别名匹配**（`:463-467`），`ORDER BY 别名命中 → is_primary → sa.id LIMIT 1`（`:469-473`） | ✅ `source_site`（`:62`，tiktok orders raw 4662/4662） |
| `semantic.fact_analytics_atomic` | VIEW | `sql/semantic/analytics_atomic.sql`（2026-06-09） | `LATERAL` 扫候选视图 `ORDER BY resolution_priority, resolved_shop_id LIMIT 1`（`:221-229`） | ❌（tiktok analytics raw 1263 行，`站点` / `店铺` 都是 0 行） |
| `semantic.fact_orders_monthly_atomic_mv` | MATVIEW | `sql/semantic/orders_monthly_atomic_mv.sql`（2026-06-18） | `LATERAL` 扫候选视图 `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`（`:267-279`） | ✅（同一个 raw 表，站点 100%） |
| `semantic.fact_analytics_monthly_atomic_mv` | MATVIEW | `sql/semantic/analytics_monthly_atomic_mv.sql` | `LATERAL` 扫候选视图 `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`（`:389-401`）；**带与 orders monthly 同一套既有告警码词表**（`:365-377`） | ❌ |
| `semantic.fact_orders_monthly_atomic` | VIEW | — | `fact_orders_monthly_atomic_mv` 的薄封装 | — |
| `semantic.fact_analytics_monthly_atomic` | VIEW | — | `fact_analytics_monthly_atomic_mv` 的薄封装 | — |

候选视图 `semantic.shop_identity_resolution_candidates` 的优先级：`platform_shop_id`(1) → `shop_account_id`(2) → `alias_match`(3) → `store_name_match`(4)，**没有区域维度**。

**两个必须记住的坑：**

1. **候选池不按 `enabled` 过滤**（视图 CTE 名叫 `active_shop_accounts`，但 `FROM shop_accounts sa` **无 `WHERE enabled`**），且 `alias_match` 只要求 `saa.is_active = true`、**不看 `is_primary`**。
   实测：32 个 **disabled** 店铺账号贡献 **65** 条候选行，20 个 enabled 账号贡献 71 条（合计 136 行）—— **近半候选来自 disabled 账号**（含 `chenewei666.sg`、28 个 disabled shopee 店、以及 `platform='验证码测试账号'` 的脏行）。
2. **同名塌缩的胜者在两条路径上不同**（只读模拟，未改库）：
   - `semantic.fact_orders_atomic` 路径（`orders_atomic.sql:469-473`）→ 胜者 `tiktok_sg_daone_mall_local`（SG）
   - 候选视图路径（`fact_orders_atomic_mv` / `fact_analytics_atomic`）→ 胜者 `tiktok_my_dawie_mall_local`（MY）

   结论（三店数据全归一店）成立，但**"归 MY 店"只对后两条路径成立**。D12 必须在**四条**路径上统一判定逻辑。

   > **区域感知匹配（D10b）只对有站点信息的 orders 两条路径生效** —— analytics 两条路径的 raw 里既没有站点也没有店铺标签，
   > 它们靠 `shop_account_id`（稳定锚点）匹配，不会出现同名品牌歧义。

**这就是改名的红线：** 一旦多个店的 `store_name` 相同且该名字出现在导出数据里，`LIMIT 1` 会把它们的行全部归给一个店。

### 2.6 改名当前"不会"立刻塌缩——因为妙手导出用的是中文标签

2.3 已证明妙手「店铺」列 = 中文别名标签，所以**只要不把平台侧真实店名写进导出文件的店铺列，改 `store_name` 本身不影响现有 4662 行 TikTok 数据的归属**。

但这层安全是"碰巧"的，不是"设计"的。两个明确的引爆点：

1. `semantic.fact_orders_atomic` 的 `store_name` 等值匹配（`orders_atomic.sql:464`）—— 只要导出里出现 `FIORO`，立刻塌缩。
2. 仓库里 `sql/semantic/orders_atomic.sql` / `analytics_atomic.sql` 已改成"名字反查"为主，**一旦部署到 live 并叠加同名改名**，就是活的生产事故。

### 2.7 采集侧的会话短路点（会话线现有设计缺陷，一并纳入）

- `modules/apps/collection_center/executor_v2.py:924`：`if (not has_persistent_profile and effective_storage_state is None and session_owner_id:)` —— **profile 目录非空时，`data/sessions` 下的 JSON 根本不读**。人工在面板保存的会话，对已有 profile 的账号无效。
- `modules/apps/collection_center/runtime_session.py:458-462` `_profile_contains_state` 仅判断 `any(profile_path.iterdir())` —— 目录非空即视为"有会话"。
- `modules/utils/sessions/session_manager.py:523-525` `load_session` **每次读取都回写文件**并刷新 `last_used_at`；`_session_freshness_timestamp`(:108-121) 取 `saved_at/last_used_at/created_at` **最大值** → **30 天过期机制实际永不触发**；文件 mtime 失去参考价值（实测 `Tiktok 1店` mtime 是今日，但 `saved_at` 停在 2026-06-22）。
- `modules/apps/collection_center/executor_v2.py:2822` `_should_skip_post_login_session_persist`：TikTok 走持久 profile 时**不落 storage_state**。
- `modules/apps/collection_center/executor_v2.py:245-309` 的 executor 版 bootstrap（`def` 在 `:245`）**缺** `runtime_session.py:74-136` 的 TikTok 质量门禁；调用点 `executor_v2.py:330` 调的是**本地这份**，不是 `runtime_session` 的实现。

### 2.8 数据健康缺口（需要业务确认，不在代码范围内）

- `TK新加坡3C店`（新加坡）→ 别名表里**没有这个标签**，`core.shop_accounts` 里也**没有对应的 TikTok 店铺账号**（只有 shopee 的 `chenewei666.sg`，且 `enabled=false`）。
  > **业务已决定：暂不认领**，保持 `unknown` 并登记为待处理（见 §11.1 第 3 条、A14）。
  - 在 `b_class.fact_tiktok_orders_monthly`（按 `raw_data->>'店铺'`）中 = **88 行**；
  - 在 `semantic.fact_orders_atomic`（全粒度汇总）中落 `unknown` = **90 行**。
  - 两者都是真值，但属不同表，**不要混用口径**。
- `core.shop_accounts` 有一行 `platform='验证码测试账号'`（平台字段填了主账号名），属脏数据；该行还进入了候选池。
- 2 个主账号 `enabled=false`（`虾皮巴西（东朗照明主体）` 6 店、`验证码测试账号` 1 店）→ 面板与采集同时看不见，一致但属业务死区；同时**它们的店铺账号仍在语义层候选池里**（见 §2.5 坑 1）。
- `data/sessions` 下 27 个 owner 目录，其中 **18 个**是历史别名孤儿（对 9 个 `main_accounts` 含 2 个 disabled 计；若只对 7 个 enabled 计则为 20 个）。
- `public.catalog_files` 身份字段覆盖严重不足（见 §5.2 D13）。

---

## 3. 概念定义（本设计的核心）

必须把三个被混为一谈的"名字"分开：

| 概念 | 载体 | 是否唯一 | 是否参与数据匹配 | 例子 |
|---|---|---|---|---|
| **平台侧真实店名** | `core.shop_accounts.store_name`（现有列） | 可重名，**且会随平台改名而变化** | 现状：直接参与（**要改成只经别名表间接参与**） | `FIORO`（原 `DAONE Mall`）、`xhkj1.my` |
| **内部标准名** | `core.shop_accounts.internal_code`（**新增列**） | 同平台内唯一 | **否**（仅供人读与内部引用） | `FIORO_SG`、`FIORO_MY`、`FIORO_PH` |
| **原始导出标签** | `core.shop_account_aliases.alias_value` | 平台 + 主账号 + 区域内唯一 | **是（唯一的真实匹配锚点）** | `TK菲律宾1店`、`Shopee3C店` |

**内部标准名不参与匹配。** 数据归属只走 `(平台, 主账号, 原始导出标签, 区域)`。

**平台侧真实店名会变（业务已确认）**：例如 `DAONE Mall` → `FIORO`。因此：

1. 它**不能**当稳定标识 —— 稳定标识只能是 `shop_account_id`。
2. **改名那一刻，历史数据仍要归到同一个店** —— 靠"旧名进别名表"实现（见 D15）。
3. **改名那一刻不能塌缩** —— 靠"新旧名同时在别名表 + 语义层不再用 `store_name` 等值直接匹配"实现（见 D10/D13）。

---

## 4. 对用户两个问题的直接回答

### 4.1 标准名怎么改？——**用户手动改，系统给建议值 + 自动做配套**

**分工**：

| 谁 | 做什么 | 为什么 |
|---|---|---|
| **系统自动** | 按 `store_name` + `shop_region` + `main_account_id` 生成建议值 | 区域是现成的辅助锚点（**但不是唯一锚点**，见下） |
| **用户手动** | 在账号管理页现有编辑弹窗里确认或修改建议值 | 平台侧真实店名我们不知道，**不能自动生成**；标准名是业务命名决策（要不要带平台、要不要带序号），**必须人定** |
| **系统自动** | 同平台内唯一性校验；冲突时给出具体冲突项 | 建议值可能撞车，必须能自动消歧 |
| **系统自动** | 改名时自动记曾用名；同步 `core.dim_shops.shop_name`（展示用的维度表，否则页面/绩效/提成显示旧名）；同主账号下唯一性校验 | 这些是"改名动作的必然副作用"，手工做必然漏 |

**建议值生成规则（必须逐形态枚举，否则不可预测）**：

| `store_name` 形态 | 样例 | 处理 | `shop_region` | 建议值 |
|---|---|---|---|---|
| 带域名后缀 | `xhkj1.my` | 剥掉 `.my` | MY | `XHKJ1_MY` |
| 带括号 | `Malaysia(Flora Mall)` | 括号转 `_` | MY | `MALAYSIA_FLORA_MALL_MY` |
| 纯英文带空格 | `DAWIE Mall` | 空格转 `_` | MY | `DAWIE_MALL_MY` |
| 纯中文 | `xh_home.ph`（实为域名） | 同域名式 | PH | `XH_HOME_PH` |

统一算法：`大写化(store_name 去掉已知地区后缀) → 非字母数字转 _ → 去首尾 _ → 拼 "_" + shop_region`。

**⚠ 区域不是唯一锚点。** 实测 `shop_region` 在主账号内**高度重复**：

```
hongxikeji:main  MY×3  PH×3  SG×3
shopee KR        SG×3
```

且 20 个 enabled 店铺账号中有 1 个 `shop_region` 为空串（miaoshou / `xihong`）。
→ **唯一锚点必须是 `shop_account_id`（20/20 覆盖、永不变化）；`shop_region` 只是消歧维度之一。**
→ 同平台两个主账号各开一个 `FIORO_MY` 时，建议值必须能区分主账号，例如 `FIORO_MY_T1` / `FIORO_MY_T2`（T1/T2 取主账号短标识）。

**唯一约束**：`UniqueConstraint("platform", "internal_code")`（同平台内唯一，跨平台允许同名 —— 匹配本来就带 platform 维度，不会歧义）。

**"FIORO" 这个平台侧真实店名要不要进别名表？** 要。但因为 `UniqueConstraint("platform","alias_normalized","is_active")` 的存在，裸 `FIORO` 只能给一个店 → **别名表必须引入区域维度**（见 §5.2 D9）。

### 4.2 改名时间点？——**改名确定会发生，但顺序不能颠倒**

业务已确认：平台侧真实店名最终都要改（`DAONE Mall` → `FIORO`），不改未来会有分歧（同一个店在库里出现两个名字，老数据认旧名、新数据认新名，数据分裂）。

所以问题不是"要不要改"，而是"**改的时候系统扛不扛得住**"。

理由：妙手导出用的是中文别名标签而非平台店名，**改 `store_name` 当下不会让现有数据塌缩**；真正的红线是语义层的 `store_name` 等值 + `LIMIT 1`（§2.5）。

结论：

1. **⑤⑥⑧⑩（语义层止血 + 别名区域维度）先做** —— 它们不是"可选优化"，而是**改名的前置条件**。做完之后，改名才是安全操作。
2. **改名时必须一次性完成三件事**（缺一件就分歧）：
   - 旧平台侧真实名写进别名表（`is_active=true`, `is_primary=false`）→ 老数据继续命中；
   - 新平台侧真实名写进别名表并绑定区域 → 新数据命中正确店铺；
   - 内部标准名同步更新（`FIORO_SG` 形式）→ 内部引用统一。
3. **改名不得由运营在账号管理页直接改 `store_name`** —— 必须走一个带联动的改名流程（D17），否则第 2 条的三个"必须"无法保证。
4. 业务侧要改 TikTok 三店为 `FIORO` 时，请在第一批完成后提出，届时 D10/D13 已就位。

---

## 5. 设计决策

### 5.1 会话线

**D1 —— 会话保存走"按账号重算 session 名"，不依赖环境变量。**
`Save-PwcliPlatformState -AccountId X` 必须用 `X` **重算出与 open 完全相同的 session 名**（`"$platformName-$WorkTag"`，`WorkTag = work_tag(platform, account_id)`），或由面板显式传 `-Session`。`PLAYWRIGHT_CLI_SESSION` 只作显式覆盖时的次选。

**D2 —— 退出码必须传播到面板。**
`scripts/pwcli.ps1` 结尾补 `exit $LASTEXITCODE`；`Open-PwcliPlatform` / `Save-PwcliPlatformState` 捕获 `$LASTEXITCODE` 并在非 0 时 `throw`；面板 `run_action` 同时看退出码与 stderr。

**D3 —— 面板日志必须渲染 `result.message`（含 stdout/stderr 原文），不只是 `result.status`。**

**D4 —— `modules/utils/pwcli_native.py` 补 `sys.path` 兜底。**
按 `__file__` 推出仓库根并 `sys.path.insert(0, root)`，使 `python modules/utils/pwcli_native.py` 与 `python -m modules.utils.pwcli_native` 两种直接调用方式都成立。
（**理由是"直接调用是公开入口"，不是"面板链路已坏 7 个月"** —— 后者已被 §2.1 断点 D 推翻。）

**D5 —— 读写两侧共用同一个路径净化函数。**
`runtime_account_state_path`（读）与 `SessionManager`（写）必须产出同一路径。实现上应复用 `SessionManager` 内部的净化逻辑，而不是再写一份。
（`backend/tests/test_session_storage_roots.py:30-31` 断言的"session 目录名 ≠ profile 目录名"是既定设计，**不受影响**。）

**D6 —— 采集侧会话读取顺序修正。**
`executor_v2.py:924` 的短路条件改为：当存在 `session_owner_id` 且 `data/sessions/<platform>/<owner>/storage_state.json` 存在时，**优先使用该 storage_state**（人工巡店保存的），而不是"profile 目录非空就跳过一切"。会话质量门禁沿用 `runtime_session.py:74-136` 的 TikTok 质量评分（该门禁在 `executor_v2.py:255-309` 的 executor 版 bootstrap 里缺失，需补齐）。

**D7 —— 会话新鲜度以 `saved_at` 为准。**
`_session_freshness_timestamp` 改为：**`saved_at` 唯一优先，完全不参与 `last_used_at`**（仅当 `saved_at` 缺失时回退 `created_at`）。
（注意：`save_session` 在保留 protected 旧 state 时仍会刷新 `merged_metadata["saved_at"]`（`session_manager.py:447`）→ **必须同时改**：保留旧 state 时**不得**刷新 `saved_at`。）
`load_session` 的"读时回写"改为"仅在内容真正变化时回写"，不再每次都刷新 `last_used_at`。

**D8 —— TikTok 持久 profile 模式下也要落 storage_state。**
`executor_v2.py:2822` 的 `_should_skip_post_login_session_persist` 需排除"人工保存的会话"这一来源，否则 D6 拿到的会话会被后续采集覆盖。

**D9（会话侧）—— 一账号一巡店窗口的 session 名必须可区分。**
`slugify`（`pwcli_account_inventory.py:48-51`）丢弃全部非字母数字 → 中文账号名塌成 `account` → session 名冲突 → `command_open` 杀掉同名浏览器。
修法：slug 保留中文（URL/PowerShell 安全字符集）或对非 ASCII 部分追加短哈希；并让 `command_open` 只杀**同账号**的 session，不杀同平台其他账号。

### 5.2 身份线

**D10a —— 别名表加区域维度（第一批：落库与约束）。**
`core.shop_account_aliases` 新增 `shop_region` 列（可空；NULL 表示"不限区域"，兼容存量），唯一约束改为 `(platform, alias_normalized, shop_region, is_active)` 且**必须使用 `NULLS NOT DISTINCT`**（PostgreSQL 15.14 支持；否则 NULL 行互不冲突，约束对存量行形同虚设，且"FIORO 可挂三店"会变成"FIORO 可挂无限多店"）。

**D10b —— 匹配用区域消歧（第二批 ⑨：让 `FIORO` + 站点正确分流）。**
只加列不改匹配的话，同一个 `FIORO` 会产生多个候选 → 落 `unknown` + `ambiguous_shop_label`（**安全，但认不出店**）。
要让它真正分流，需要把「站点 → 区域」引入匹配：
- raw 数据里已有站点：`b_class.fact_tiktok_orders_monthly.raw_data->>'站点'`（100% 覆盖，改名后不变），`sql/semantic/orders_atomic.sql:62` 已经把它抽成 `source_site`；
- 现成映射：`backend/domains/collection/routers/account_alignment.py:796-805` 的 `site_map`（菲律宾→ph、新加坡→sg、马来/马来西亚→my、泰国→th、越南→vn、印尼→id、巴西→br）；
- 店铺侧区域：`core.shop_accounts.shop_region` 存**大写**（MY/PH/SG），与 `site_map` 的小写码差一个 `upper()`；
- 匹配规则：候选别名的 `shop_region` 与该行站点映射出的区域一致（`shop_region IS NULL` 的别名作"不限区域"兜底，优先级最低）。

**D11 —— 写侧与查侧共用同一套规范化，且必须幂等、可解释。**
`backend/utils/text_normalization.py` 的 `normalize_alias_key` 改为与 SQL 侧完全一致：剥平台前缀 → 小写 → 折叠空白 → 删 `[[:space:]_()/-]+`（**含前导连字符**）。
SQL 侧统一改为**直接使用存储的 `alias_normalized`**，不再在查询里做第二次规范化（消除双份规则）。
`normalize_alias_key` 成为唯一真源，并加单元测试锁定（至少覆盖 `TK-新加坡-1店` → `新加坡1店`、`Malaysia(Flora Mall)` → `malaysiafloramall`、`TK新加坡1店` → `新加坡1店`）。

**D12 —— 平台代码大小写统一为小写（仅别名表）。**
`core.shop_account_aliases.platform` 的 `'Shopee'` / `'Tiktok'` 两行合并到小写侧。合并规则：**保留 `is_active=true` 且 `is_primary=true` 的那条；另一条降为 `is_active=false` 且 `is_primary=false`**。
`3c店` 冲突的既有决策需业务确认（见 §11 第 2 条）。`core.shop_accounts.platform` 与 `core.main_accounts.platform` 已无大小写分裂，本轮不动。

**D13 —— 多候选不静默归一，落 `unknown` + 告警码。**
语义层解析从 `ORDER BY priority, shop_id LIMIT 1` 改为：
- 候选唯一 → 归属该店；
- 候选 0 → `unknown` + `identity_warning_code='unmatched_shop_label'`；
- 候选 > 1 → `unknown` + `identity_warning_code='ambiguous_shop_label'`，并暴露 `identity_candidate_count` 与 `identity_candidates`（供"未匹配店铺别名"面板消费）。

**候选集口径必须同时明确（否则会凭空制造 unknown）：**

- **是否排除 `enabled=false` 的店铺账号？→ 不排除**（业务确认：停用只是暂时的，可能回来还会启用）。
  当前候选池有 65/136 行来自 disabled 账号（含脏行 `platform='验证码测试账号'`）。
  **排除会有害**：一旦某账号被停用，它名下数据会掉进 `unknown`；重新启用后归属又变回 —— 归属随启停状态漂移，历史数据反复进出 unknown。
  **不排除则安全**：唯一性判定用**完整候选集**，只要候选仍是唯一的，归属就不随启停变化。
  → 唯一的例外是**同名冲突**：enabled 店与 disabled 店同名时 → 2 个候选 → `unknown` + `ambiguous_shop_label` → 交人工裁决。这正是应有的行为（将来 disabled 店若启用，归属会变，必须人工确认）。
  → 脏行 `platform='验证码测试账号'` 单独清理（§11 第 7 条），不进 D13 口径讨论。
- `alias_match` 是否要求 `is_primary=true`？→ **不要求**（"曾用名"机制依赖 `is_active` 即可匹配）。

**告警码词表（已定稿，不再是"建议"）**：live `semantic.fact_orders_monthly_atomic.identity_warning_code` 实测分布为
`NULL` = 31201 行、`unresolved_shop_account` = **88 行**（全部来自 `TK新加坡3C店`）、
`missing_identity` = 0、`missing_required_platform_shop_id` = 0。
`semantic.fact_analytics_monthly_atomic_mv`（3541 行）用的是**同一套**既有词表。

`identity_warning_code` 是**单值列**，所以新旧码按**固定优先级**并存（先命中先返回）：

| 顺序 | 码 | 触发条件 |
|---|---|---|
| ① | `missing_identity` | 四个身份线索全为空（连线索都没有） |
| ② | `unmatched_shop_label`（新） | 候选数 = 0（有线索但没人认领） |
| ③ | `ambiguous_shop_label`（新） | 候选数 ≥ 2（多个店抢） |
| ④ | `unresolved_shop_account` | 候选唯一但 `resolved_shop_account_id` 为空 / `canonical` 查不到 |
| ⑤ | `missing_required_platform_shop_id` | 已归属、shopee、但该店没有 `platform_shop_id` |
| — | `NULL` | 正常归属 |

既有码**只在新码没命中时才生效** → live 的 88 行不会凭空消失，会按新口径落进 `unmatched_shop_label`。
**两个 monthly 资产都要改**（`orders_monthly_atomic_mv.sql:247-259` 与 `analytics_monthly_atomic_mv.sql:365-377`），
否则两个视图的告警码词表会不一致。

**列覆盖**：`fact_orders_atomic`（实测 **40 列**）当前**无** identity/warning/candidate 列，
`fact_analytics_atomic`（实测 **31 列**）同样没有，`fact_orders_monthly_atomic` 有 `identity_source_value` + `identity_warning_code`。
D12 需为前两者补列。

> **实现口径（必须照抄计划里的模板）**：候选计数**不能用窗口函数** ——
> `count(DISTINCT x) OVER ()` 在 PostgreSQL 直接报错（`DISTINCT is not implemented for window functions`），
> 而「显然的修法」`count(*) OVER ()` 因为窗口函数在聚合之后求值会**恒为 1**，
> 导致所有多候选都被判成 1 个 → **永远不落 `ambiguous_shop_label`** → 正是本设计要防的静默错配。
> 正确写法是纯聚合 `count(DISTINCT ...)` + `array_agg(DISTINCT ...)` 放在独立子查询里，
> 再用 `LEFT JOIN LATERAL` 拼回（已在 live PG 15.14 实测：0 / 1 / 2 候选计数全部正确，输出行数恒为 1）。

**D14 —— 数据落库用稳定身份编号，不用名字。**
`backend/services/data_ingestion_service.py:494-495` 的 `file_shop_id = file_record.shop_id or "none"` 改为优先 `file_record.shop_account_id`（`:497` 已有该字段读取），`platform_shop_id` 次之。
`:627-637` 的 `data_hash` 作用域（`hash_scope_values["shop_id"] = file_shop_id`）中把 `shop_id` 换成稳定身份编号，避免改名/重命名造成同一份数据重复入库、`semantic.fact_orders_atomic.shop_id` 分裂、`mart.shop_*_kpi` 聚合断裂。

**⚠ D14 的前置任务（必须先做，否则 D14 会立即造成全量历史行重复）：**
`public.catalog_files` 的身份字段覆盖严重不足（live 实测）：

| platform_code | 总行 | `platform_shop_id` 有值 | `shop_account_id` 有值 | `shop_id` 有值 |
|---|---|---|---|---|
| shopee | 332 | **0** | 49 | 332 |
| tiktok | 124 | **0** | 34 | 124 |
| miaoshou | 4 | **0** | 4 | 4 |
| 合计 | 460 | **0/460** | **87/460** | 460/460 |

→ **必须先把 `catalog_files.shop_account_id` 补齐到 460/460**（在采集入库时回填，而不是事后刷库），再改 `data_hash` 口径。
→ `platform_shop_id` 在 file 层 **0/460 完全不可用**，不能作为"次之"选项。

**D15 —— 曾用名 = 别名表里的一条"可参与匹配"的记录（不另建表）。**

平台侧真实店名会变（`DAONE Mall` → `FIORO`，业务已确认）。改名时必须把**旧名写进 `core.shop_account_aliases`**（`alias_value` = 旧名，`alias_normalized` = 旧名的规范化值，`is_active=true`，`is_primary=false`，`alias_type='former_name'`），这样：

- 老数据（携带 `DAONE Mall`）**继续命中同一个店** → 不会掉进 unknown → 不产生分歧；
- 老名与新名**指向同一 `shop_account_id`** → `semantic.fact_orders_atomic.shop_id` 不分裂，`mart.shop_*_kpi` 聚合不断。

**为什么不用独立的曾用名表**：独立表只能追溯、不能匹配 → 老数据认不出店 → 正是要避免的"分歧"。别名表本来就是"原始导出标签 → 标准店铺"的映射表，旧名天然就是一条原始标签。

**代价（可接受且必要）**：写别名会触发 `shop_account_aliases.py:347` `_enqueue_shop_identity_refresh` → `RefreshQueueService.enqueue_refresh` → raw 层全量重建。
**这是正确的**：归属确实要重算一次（老数据从 `store_name_match` 改为 `alias_match`，命中同一个店，结果不变但路径变了）。重算**只在改名时发生一次**，不是每次改名都全量。日常读取不触发。

**改名审计**沿用 `core.shop_accounts.updated_by` / `updated_at` + `core.shop_account_aliases.created_by` 语义，不新建审计表。

**"曾用名"的读写规则**：
- `is_primary=true` 的别名 = 当前生效的平台侧真实名（改名后由新名接管）；
- `is_primary=false` 且 `is_active=true` 的别名 = 曾用名，**仍参与匹配**（候选视图 alias_match 只看 `is_active`，已满足）；
- `is_active=false` = 彻底作废（如 §2.4 那种挂错的孤儿别名），不参与匹配。

**D16 —— 别名应用级约束从"同平台同别名只能一个"放宽为"同平台同别名同区域只能一个"。**
`backend/domains/collection/routers/shop_account_aliases.py:297-307` 的 409 判定同步放宽；`_clear_primary_aliases`(:164-180) 保持"旧别名仅降 `is_primary`、`is_active` 仍为 True"的语义（曾用名机制已现成可用）。
同时明确**匹配侧**对 `shop_region IS NULL` 的处理：NULL 别名优先级最低，仅当"同区域内无候选"时兜底。

**D17 —— 店铺改名联动（改名必须走这一个入口，不允许裸改 `store_name`）。**
`backend/domains/collection/routers/shop_accounts.py:363-405` 的 `update_shop_account` 从裸 `setattr` 改为带联动的更新，顺序固定：

1. **唯一性校验**：同平台 `internal_code` 唯一；同主账号 `store_name` 唯一。
2. **旧名转曾用名**：把旧 `store_name` 写入别名表（`is_active=true`, `is_primary=false`, `alias_type='former_name'`）—— 老数据继续命中（D15）。
3. **新名接管**：新 `store_name` 写入别名表并置 `is_primary=true`（原主别名降为 `is_primary=false`，`is_active` 保持 True）。
4. **同步 `core.dim_shops.shop_name`**（`platform_code = platform AND shop_id = shop_account_id`）—— 否则页面、绩效、提成里显示的还是旧名。
   > **⚠ 不是 `core.platform_accounts`**：该表是**主账号粒度**的旧表（11 行，`account_id` = 主账号 ID，`store_name` = 主账号名如 `Tiktok 1店`，`shop_id` 全为 NULL）→ 改店铺名不该改它。
   > `core.dim_shops`（49 行）里的店铺粒度行（`shop_id = tiktok_my_dawie_mall_local` / `xhkj1.my` 等）的 `shop_name` 已经等于 `core.shop_accounts.store_name`，且被 `hr_commission` / `target_management` / `clearance_ranking_service` / `c_class_data_service` 读取展示。
   > `backend/services/shop_sync_service.py:83-103` 现有的是 `core.platform_accounts` → `core.dim_shops` 的同步（方向相反、粒度不同），**不能直接复用**。
5. **同步 `internal_code`**（若随之改动）。
6. **入刷新队列**：`core.shop_account_aliases` 变更 → `shop_account_aliases.py:347` `_enqueue_shop_identity_refresh` → `RefreshQueueService.enqueue_refresh`。**改名必须触发这一次重算**（归属路径要重算），但**不得**由改名路径触发超出必要范围的全量重建。
   > **已核实（`shop_accounts.py:363-405`）**：`update_shop_account` **已经**调用 `_enqueue_shop_identity_refresh(db, shop_account=record, changed_fields=...)`，且 `_SHOP_IDENTITY_FIELDS`（`:42-47`）已包含 `store_name` → **改名本来就会触发一次刷新**。
   > **但**：`_SHOP_IDENTITY_REFRESH_TARGETS`（`:38-41`）目前只有 `semantic.fact_orders_monthly_atomic_mv` 与 `semantic.fact_analytics_monthly_atomic_mv` 两个**物化视图**；而 `semantic.fact_orders_atomic` 与 `semantic.fact_analytics_atomic` 是**视图**（改定义即生效，但旧数据不会自动重算）→ 实施前必须确认 `RefreshQueueService.enqueue_refresh` 的实际重算范围，并决定是否把这两个视图纳入刷新目标。**这是 B5「改名后自动重认」能否成立的关键。**

---

## 6. 落地批次

### 第一批（止血）

| 项 | 内容 | 作用 | 对应决策 | 验收 |
|---|---|---|---|---|
| ① | 巡店会话真能保存 | 采集反复登录、被弹窗打断 | D1、D2、D4、D5 | A1 A2 A3 A4 |
| ② | 失败不谎报 | 白跑一轮、无从排查 | D2、D3 | A2 |
| ⑤ | 采集用店铺身份编号落库 | **订单重复入账、月结算错** | D14（含前置：补齐 `catalog_files.shop_account_id`） | A5 |
| ⑥ | 认不准就不猜 | 数据张冠李戴 | D13 | A6 A7 |
| ⑧ | 修别名认领失效 | 90 行数据认不出店 | D11、D12 | A8 A9 |
| ⑩ | 别名表区域维度落地（落库与约束） | 同名品牌店可区分 | D10a | A10 |

### 第二批（正本）

| 项 | 内容 | 作用 | 对应决策 | 验收 |
|---|---|---|---|---|
| ③ | 一账号一巡店窗口 | 登录态互相覆盖 | D9 | B1 |
| ④ | 账号标识唯一化 | 串号 | D9 | B2 |
| ⑦ | 改名自动留痕（曾用名进别名表） | 老数据认不出店、数据分裂 | D15 | B3 |
| ⑨ | 改名后按站点自动重认店铺（区域感知匹配） | 改名后全量人工重认 | D10b + D13 | B5 |
| ⑪ | 内部标准名字段 | 唯一、带地区标识 | §4.1 + D17 | B4 |
| ⑫ | 会话新鲜度与持久化口径 | 过期会话被当新会话用 | D7、D8 | A11 A12 |
| ⑬ | 改名联动与刷新队列口径 | 改名产生分歧 | D17 | A13 |

---

## 7. 数据模型变更汇总

迁移落在 `current_migrations/versions/`（新版本号），执行顺序：

**第 1 步 —— 平台大小写归一（D12，先做，避免下一步加约束时冲突）**

```sql
-- 'Tiktok' 的 '菲律宾1店'(id=21, 非active/非primary) 与 'tiktok' 的 'TK菲律宾1店'(id=20, active/primary)
--   指向同一店铺 → 保留 id=20，id=21 降级
UPDATE core.shop_account_aliases
   SET platform = lower(platform), is_active = false, is_primary = false
 WHERE id IN (
   SELECT a.id FROM core.shop_account_aliases a
    WHERE a.platform IN ('Shopee','Tiktok')
      AND EXISTS (SELECT 1 FROM core.shop_account_aliases b
                   WHERE b.platform = lower(a.platform)
                     AND b.alias_normalized = a.alias_normalized
                     AND b.is_active = true AND b.id <> a.id)
 );
UPDATE core.shop_account_aliases SET platform = lower(platform) WHERE platform IN ('Shopee','Tiktok');
```

**第 2 步 —— 别名表加维度与新约束（D10）**

```sql
ALTER TABLE core.shop_account_aliases ADD COLUMN shop_region varchar(50);

-- PostgreSQL 15.14 支持 NULLS NOT DISTINCT；否则必须先回填 shop_region 为 '' 再加普通 UNIQUE
ALTER TABLE core.shop_account_aliases DROP CONSTRAINT uq_shop_account_aliases_active_alias;
ALTER TABLE core.shop_account_aliases
  ADD CONSTRAINT uq_shop_account_aliases_active_alias
  UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active);
```

**第 3 步 —— 内部标准名（D17 / §4.1）**

```sql
ALTER TABLE core.shop_accounts ADD COLUMN internal_code varchar(100);
ALTER TABLE core.shop_accounts
  ADD CONSTRAINT uq_shop_accounts_platform_internal_code UNIQUE (platform, internal_code);
```

**第 4 步 —— 曾用名不建表（见 D15），只需给别名加类型标记**

```sql
-- 曾用名 = core.shop_account_aliases 里 is_primary=false 且 is_active=true 的一条记录
-- alias_type 复用为 'former_name'，便于前端与治理面板区分
ALTER TABLE core.shop_account_aliases
  ADD CONSTRAINT ck_shop_account_aliases_alias_type
  CHECK (alias_type IS NULL OR alias_type IN ('primary','former_name','manual','auto'));
```

ORM SSOT 同步更新 `modules/core/db/schema_parts/platform.py`。
`core.platform_accounts`（旧表，主账号粒度）本轮**不动**；改名时同步的是 `core.dim_shops.shop_name`（店铺粒度，见 D17 第 4 步）。

---

## 8. 验收标准

### 第一批

- [ ] **A1（会话保存）** 面板「保存会话」执行后，`data/sessions/<platform>/<净化后owner>/storage_state.json` 存在，且文件内 `metadata.saved_at` 更新为当前时间、`metadata.manual_seeded=true`。
- [ ] **A2（失败可见）** `pwcli --session no-such-session-xyz state-save` 的 **exit code ≠ 0**；面板对应操作显示失败，且日志区**可见 stdout/stderr 原文**。
- [ ] **A3（读写同路径）** 对 account_id=`hongxikeji:main`：保存写入 `data/sessions/shopee/hongxikeji_main/storage_state.json`；**再次打开时从同一路径加载**（不是 `hongxikeji:main/`），人工登录态被成功复用。
- [ ] **A4（采集优先用人工会话）** 人工保存会话后触发采集 → `executor_v2` 读取的是 `data/sessions/.../storage_state.json`，而非直接复用 profile 目录。
- [ ] **A5（稳定编号落库）** `public.catalog_files.shop_account_id` 覆盖达 460/460；同一份订单数据重复入库时 `semantic.fact_orders_atomic.shop_id` 保持单一值，`mart.shop_*_kpi` 不重复。
- [ ] **A6（不静默错配）** 构造一个同平台同名多候选的标签 → 落 `shop_id='unknown'` 且带 `identity_warning_code='ambiguous_shop_label'`，**不再**归给排序第一的那个店；**四条**语义路径（`fact_orders_atomic` / `fact_analytics_atomic` / `fact_orders_monthly_atomic_mv` / `fact_analytics_monthly_atomic_mv`）判定结果一致。
- [ ] **A7（告警码词表）** `ambiguous_shop_label` / `unmatched_shop_label` 与既有 `missing_identity` / `unresolved_shop_account` / `missing_required_platform_shop_id` 的**并存关系与优先级已定义**（见 D13 的词表）；两个 monthly 资产的词表**一致**；`fact_orders_atomic` 与 `fact_analytics_atomic` 已具备 `identity_warning_code` / `identity_candidate_count` / `identity_candidates` 列。
- [ ] **A8（别名可认领）** 新建别名 `TK-新加坡-1店` → 其 `alias_normalized` 为 `新加坡1店`（Python 与 SQL 两侧一致），能被 `TK新加坡1店` 的原始数据命中；`normalize_alias_key` 单元测试覆盖 `TK-新加坡-1店` / `Malaysia(Flora Mall)` / `TK新加坡1店` 三个用例。
- [ ] **A9（平台大小写）** `core.shop_account_aliases.platform` 全部为小写；`3c店` 冲突已按 §11 第 2 条的决策消解并留痕。
- [ ] **A10（别名区域维度）** `core.shop_account_aliases.shop_region` 列存在；新唯一约束生效；`FIORO` 可同时挂在 `FIORO_SG` / `FIORO_MY` / `FIORO_PH` 三个店上而不冲突；`shop_region IS NULL` 的存量行不绕过约束。
- [ ] **A11（会话新鲜度）** 读一次会话**不会**刷新 `saved_at`；把 `saved_at` 调到 40 天前 + `last_used_at` 调到当前 → 判定为过期。
- [ ] **A12（持久化口径）** TikTok 走持久 profile 模式时，登录后的 storage_state 仍会落盘，且不会覆盖人工保存的 protected 会话。
- [ ] **A13（改名联动）** 改 `store_name` → 旧名进别名表（`is_primary=false`, `is_active=true`, `alias_type='former_name'`）、新名接管 `is_primary`、`core.dim_shops.shop_name` 与 `internal_code` 同步；**改名后携带旧名的历史数据仍归到同一个 `shop_account_id`，不落 unknown**；刷新队列触发**一次**（且仅一次）归属重算。
- [ ] **A14（待认领清单）** `TK新加坡3C店`（monthly 88 行 / atomic unknown 90 行）**按业务决定暂不认领**：保持 `unknown`，并在「未匹配店铺别名」面板可见（含说明：现有 6 个 TikTok 店已被其它标签 1:1 占满，需新建店账号才能认领）。

### 第二批

- [ ] **B1（一账号一窗口）** 同时打开两个账号的巡店窗口，互不踢掉对方；同一账号重复打开才复用/接管。
- [ ] **B2（账号标识唯一）** 中文账号名不再被 slugify 丢弃；`虾皮巴西（东朗照明主体）` 与 `验证码测试账号` 不再塌成同一个 session 名；`data/sessions` 下不再新增因 slug 塌缩而互相覆盖的目录。
- [ ] **B3（曾用名）** 改名后别名表可查到旧名（`is_primary=false`, `is_active=true`, `alias_type='former_name'`）；**老数据（携带旧名）仍命中同一店**；改名触发**一次**归属重算（不是零次，也不是每次读取都重算）。
- [ ] **B4（标准名）** 账号管理页可编辑「内部标准名」，系统给出 `FIORO_SG` 形式建议值（含主账号消歧）；同平台内重名被拒绝并给出冲突详情；同主账号下同名也能正确区分。
- [ ] **B5（改名后自动重认）** TikTok 三店 `store_name` 改为 `FIORO` 后，新采集数据的归属仍按区域正确分流到三个店，且三条语义路径均无 `LIMIT 1` 塌缩。

### 回归护栏

- [ ] `backend/tests/test_session_storage_roots.py` 仍通过（session 目录名与 profile 目录名不同是既定设计）。
- [ ] `backend/tests/test_collection_session_reuse_contract.py` 仍通过（load 优先于 bootstrap）。
- [ ] `backend/tests/test_shop_account_aliases_api.py` 仍通过（其中已有的 4 条 `normalize_alias_key` 断言在新规则下应仍成立）。
- [ ] `backend/tests/data_pipeline/test_shop_identity_resolution_sql.py` 仍通过。
- [ ] `sql/semantic/` 下三条语义路径的解析逻辑统一到同一套候选视图 + 告警码，**不再**各自实现 `LIMIT 1`。
- [ ] MATVIEW 变更后已执行 `REFRESH MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv` 并完成历史回填（改 VIEW 定义不会立即生效）。

---

## 9. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 别名表唯一约束放宽后出现同平台同别名同区域两条 active | 匹配歧义 | 迁移脚本显式消解存量冲突（D12），并加约束校验脚本 |
| `shop_region IS NULL` 在普通 UNIQUE 下互不冲突 | 约束形同虚设 | 用 `UNIQUE NULLS NOT DISTINCT`（PG 15.14）或先回填再约束 |
| 若把 disabled 账号排除出候选池 | 停用/启用会让数据归属在 unknown 与正常店之间漂移 | **明确不排除**（业务确认：停用只是暂时的）；唯一性判定用完整候选集；只有同名冲突才落 ambiguous |
| 旧名写进别名表后与既有别名冲突 | 匹配歧义 | 唯一约束带区域维度 + `NULLS NOT DISTINCT`；冲突时人工裁决，不自动合并 |
| `shop_region` 维度让存量别名（NULL 区域）语义漂移 | 老数据匹配行为变化 | NULL = "不限区域"，匹配时 NULL 别名优先级最低，仅当区域内无候选时兜底 |
| 语义层从"归第一"改成"落 unknown" | 短期 `unknown` 行数上升 | 这是暴露而非制造问题；配套面板给出认领清单，逐条处理 |
| `data_hash` 口径变更导致历史行与新行并存 | 短期重复计数 | **先补齐 `catalog_files.shop_account_id` 再改口径**；变更后触发一次全量 semantic 重建；上线前在快照库演练 |
| `save_session` 在保留 protected 旧 state 时仍刷新 `saved_at` | 新鲜度判定失真 | D7 同时修 `session_manager.py:447` |
| 改名触发一次 raw 层全量重算 | 耗时长 | 这是**必要的**（归属路径确实要重算）；重算只在改名时发生一次，改名路径不得额外触发；上线前在快照库演练 |
| MATVIEW 变更未刷新 | 线上仍走旧逻辑 | 变更脚本内置 `REFRESH MATERIALIZED VIEW` + 前后行数对比 |

---

## 10. 不在本轮范围

- **IP 隔离**（三处断点：`runtime_session.py:422` 白名单丢 `proxy`、`open_persistent_runtime_bundle` 未传 proxy、`executor_v2.py:1817` 注释声明为预留能力）—— 属独立议题。
- **抓取 TikTok Shop Code** —— 平台侧真实名只能从导出表拿，Shop Code 只在店铺设置页 DOM/API、不在 URL（切店仅用 `?shop_region=`），且用户已明确要求复用现有内容。
- **启用被禁用的主账号**（`虾皮巴西（东朗照明主体）`、`验证码测试账号`）—— 业务决策；但其店铺账号当前**仍在语义层候选池里**，D13 的候选集口径需要单独评估这一项。
- **历史别名孤儿目录清理**（`data/sessions` 下 18~20 个）—— 建议单独一次清理任务，不与本次混做。
- **`core.shop_accounts.platform='验证码测试账号'` 脏行清理** —— 需业务确认（见 §11 第 7 条）。

---

## 11. 业务确认结果与仍待确认的问题

### 11.1 已确认（2026-11-01 业务拍板）

| # | 问题 | 结论 | 影响的设计 |
|---|---|---|---|
| 1 | 平台侧真实店名会变（`DAONE Mall` → `FIORO`），最终都要改，不改未来有分歧 | **确认会改** → 改名必须走联动流程；旧名必须继续能匹配 | §3、§4.2、D15、D17 |
| 2 | 内部标准名命名约定 | `FIORO_SG` / `FIORO_MY` / `FIORO_PH`；同平台同区域多主账号冲突时才追加主账号短标识（`FIORO_MY_T1`） | §4.1、D10 |
| 3 | `TK新加坡3C店`（90 行）归属 | **暂不认领**，保持 `unknown` 并登记为待处理 | A14、§2.8 |
| 4 | 语义层候选池是否排除 disabled 账号 | **不排除** —— 停用只是暂时的，可能回来还会启用 | D13 候选集口径 |

### 11.2 仍待确认（不阻塞第一批实施）

1. **`3c店` 冲突的取舍**：`Shopee3C店`→`zewei_toys.sg`（active+primary，店 enabled=true） vs `3C店`→`chenewei666.sg`（店 enabled=false）。D12 的默认规则保留前者，等于让 disabled 的 3C 店永久无别名 —— 是否为业务意图？
   （**注意**：按 11.1 第 4 条"不排除 disabled"，这条的取舍只影响"哪个店认领 `3c店`"，不影响归属漂移。）
2. **两个 disabled 主账号是否启用**（`虾皮巴西（东朗照明主体）` 6 店、`验证码测试账号` 1 店）？面板与采集可见性已一致（都看不见），但语义层候选池仍含它们的店铺账号（65/136 行）。
3. **TikTok 三店改名后的具体归属**：`Tiktok 1店` 下 id 62/63/64（DAONE Mall/SG、DAWIE Mall/MY、Explorers Mall/PH）是否就是要改名为 `FIORO` 的三店？两个 TikTok 主账号各持 3 店、标签前缀完全对称（TK+地区+序号），但 `TK新加坡1店` 同时出现在 id 62（SG，active）与 id 63（MY，inactive）—— 疑似历史误录。
4. **别名 `shop_region` 的回填策略**：存量 21 条别名是否回填区域，还是保留 NULL 作"不限区域"？
5. **`core.shop_accounts.platform='验证码测试账号'` 脏行**：随 D12 一起清为 NULL、删除，还是保留为特例？
6. **两套 alembic 中生产实际使用哪一套**：仓库并存 `current_migrations/versions/`（活动，2026-08+）与 `migrations/versions/`（历史）。本 spec 按前者落点，需运维确认。
