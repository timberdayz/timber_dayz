# 采集会话复用与店铺身份统一 —— 设计规格

- 日期：2026-11-01
- 状态：待评审（v2，已按独立事实核查修正）
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

### 2.5 live 语义层有三套并存的解析逻辑，且都带 `LIMIT 1`

| 语义对象 | 类型 | 来源文件 | 解析方式 |
|---|---|---|---|
| `semantic.fact_orders_atomic` | VIEW | `sql/semantic/orders_atomic.sql`（2026-06-09） | `LATERAL` 扫 `core.shop_accounts`，条件 **`store_name` 等值 OR `platform_shop_id` 等值 OR 别名匹配**（`:463-467`），`ORDER BY 别名命中 → is_primary → sa.id LIMIT 1`（`:469-473`） |
| `semantic.fact_analytics_atomic` | VIEW | `sql/semantic/analytics_atomic.sql`（2026-06-09） | `LATERAL` 扫候选视图 `ORDER BY resolution_priority, resolved_shop_id LIMIT 1`（`:221-229`） |
| `semantic.fact_orders_monthly_atomic_mv` | MATVIEW | `sql/semantic/orders_monthly_atomic_mv.sql`（2026-06-18） | `LATERAL` 扫候选视图 `ORDER BY c.resolution_priority, c.resolved_shop_id LIMIT 1`（`:139-147`） |
| `semantic.fact_orders_monthly_atomic` | VIEW | — | `fact_orders_monthly_atomic_mv` 的薄封装 |

候选视图 `semantic.shop_identity_resolution_candidates` 的优先级：`platform_shop_id`(1) → `shop_account_id`(2) → `alias_match`(3) → `store_name_match`(4)，**没有区域维度**。

**两个必须记住的坑：**

1. **候选池不按 `enabled` 过滤**（视图 CTE 名叫 `active_shop_accounts`，但 `FROM shop_accounts sa` **无 `WHERE enabled`**），且 `alias_match` 只要求 `saa.is_active = true`、**不看 `is_primary`**。
   实测：32 个 **disabled** 店铺账号贡献 **65** 条候选行，20 个 enabled 账号贡献 71 条（合计 136 行）—— **近半候选来自 disabled 账号**（含 `chenewei666.sg`、28 个 disabled shopee 店、以及 `platform='验证码测试账号'` 的脏行）。
2. **同名塌缩的胜者在两条路径上不同**（只读模拟，未改库）：
   - `semantic.fact_orders_atomic` 路径（`orders_atomic.sql:469-473`）→ 胜者 `tiktok_sg_daone_mall_local`（SG）
   - 候选视图路径（`fact_orders_atomic_mv` / `fact_analytics_atomic`）→ 胜者 `tiktok_my_dawie_mall_local`（MY）

   结论（三店数据全归一店）成立，但**"归 MY 店"只对后两条路径成立**。D12 必须在三条路径上统一判定逻辑。

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
- `modules/apps/collection_center/executor_v2.py:255-309` 的 executor 版 bootstrap **缺** `runtime_session.py:74-136` 的 TikTok 质量门禁。

### 2.8 数据健康缺口（需要业务确认，不在代码范围内）

- `TK新加坡3C店`（新加坡）→ 别名表里**没有这个标签**，`core.shop_accounts` 里也**没有对应的 TikTok 店铺账号**（只有 shopee 的 `chenewei666.sg`，且 `enabled=false`）。
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
| **平台侧真实店名** | `core.shop_accounts.store_name`（现有列） | 可重名 | 现状：直接参与（**要改成只经别名表间接参与**） | `FIORO`、`DAWIE Mall`、`xhkj1.my` |
| **内部标准名** | `core.shop_accounts.internal_code`（**新增列**） | 同平台内唯一 | **否**（仅供人读与内部引用） | `FIORO_SG`、`FIORO_MY`、`FIORO_PH` |
| **原始导出标签** | `core.shop_account_aliases.alias_value` | 平台 + 主账号 + 区域内唯一 | **是（唯一的真实匹配锚点）** | `TK菲律宾1店`、`Shopee3C店` |

**内部标准名不参与匹配。** 数据归属只走 `(平台, 主账号, 原始导出标签, 区域)`。

---

## 4. 对用户两个问题的直接回答

### 4.1 标准名怎么改？——**用户手动改，系统给建议值 + 自动做配套**

**分工**：

| 谁 | 做什么 | 为什么 |
|---|---|---|
| **系统自动** | 按 `store_name` + `shop_region` + `main_account_id` 生成建议值 | 区域是现成的辅助锚点（**但不是唯一锚点**，见下） |
| **用户手动** | 在账号管理页现有编辑弹窗里确认或修改建议值 | 平台侧真实店名我们不知道，**不能自动生成**；标准名是业务命名决策（要不要带平台、要不要带序号），**必须人定** |
| **系统自动** | 同平台内唯一性校验；冲突时给出具体冲突项 | 建议值可能撞车，必须能自动消歧 |
| **系统自动** | 改名时自动记曾用名；同步 `core.platform_accounts.store_name`（否则 `dim_shops` 会被打回旧名，见 `backend/services/shop_sync_service.py:85`）；同主账号下唯一性校验 | 这些是"改名动作的必然副作用"，手工做必然漏 |

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

### 4.2 改名时间点？——**不迫近，但必须排在语义层改造之后**

理由：妙手导出用的是中文别名标签而非平台店名，**改 `store_name` 当下不会让现有数据塌缩**；真正的红线是语义层的 `store_name` 等值 + `LIMIT 1`（§2.5）。

结论：

1. **⑤⑥⑧（语义层止血）先做**，它们不依赖改名，且是订单重复入账的直接成因。
2. **改名放在第二批之后**，且改名时**必须同时**为平台侧真实店名建带区域维度的别名记录 —— 否则改名那一刻就是塌缩时刻。
3. 如果业务侧确实要把 TikTok 三店改成 `FIORO`，请在第一批完成后提出，届时 D9 已就位。

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

**D10 —— 匹配锚点升级为 `(platform, main_account_id, alias_normalized, shop_region)`。**
`core.shop_account_aliases` 新增 `shop_region` 列（可空；NULL 表示"不限区域"，兼容存量）**与 `main_account_id` 维度**（或等价地把别名绑定到店铺账号后从店铺反查主账号），唯一约束改为 `(platform, alias_normalized, shop_region, is_active)` 且**必须使用 `NULLS NOT DISTINCT`**（PostgreSQL 15.14 支持；否则 NULL 行互不冲突，约束对存量行形同虚设，且"FIORO 可挂三店"会变成"FIORO 可挂无限多店"）。

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
- 是否排除 `enabled=false` 的店铺账号？→ **建议排除**（当前候选池有 65/136 行来自 disabled 账号，含脏行 `platform='验证码测试账号'`）；此变更需单独评估历史归属重算范围。
- `alias_match` 是否要求 `is_primary=true`？→ **建议不要求**（"曾用名"机制依赖 `is_active` 即可匹配）。

**告警码词表**：live `semantic.fact_orders_monthly_atomic.identity_warning_code` 现仅 `NULL` 与 `unresolved_shop_account`。
D12 的两个新码与既有 `unresolved_shop_account` 的关系需明确：**建议保留 `unresolved_shop_account` 作为"完全无法定位"的粗粒度标记，新增 `ambiguous_shop_label` / `unmatched_shop_label` 作为细粒度补充**，不做替换。
**列覆盖**：`fact_orders_atomic`（43 列）当前**无** identity/warning/candidate 列，`fact_analytics_atomic` 仅 `identity_source_value`，`fact_orders_monthly_atomic` 有 `identity_source_value` + `identity_warning_code`。D12 需为前两者补列。

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

**D15 —— 曾用名独立成表，不复用别名表。**
新增 `core.shop_account_store_name_history`（`shop_account_pk`、`old_value`、`new_value`、`changed_at`、`changed_by`）。
理由：复用别名表会 (a) 撞平台唯一约束，(b) 每次改名触发全量历史归属重算（`shop_account_aliases.py:347` → `RefreshQueueService.enqueue_refresh` → raw 层全量重建）。

**D16 —— 别名应用级约束从"同平台同别名只能一个"放宽为"同平台同别名同区域只能一个"。**
`backend/domains/collection/routers/shop_account_aliases.py:297-307` 的 409 判定同步放宽；`_clear_primary_aliases`(:164-180) 保持"旧别名仅降 `is_primary`、`is_active` 仍为 True"的语义（曾用名机制已现成可用）。
同时明确**匹配侧**对 `shop_region IS NULL` 的处理：NULL 别名优先级最低，仅当"同区域内无候选"时兜底。

**D17 —— 店铺改名联动。**
`backend/domains/collection/routers/shop_accounts.py:363-405` 的 `update_shop_account` 从裸 `setattr` 改为带联动的更新：唯一性校验 → 写曾用名 → 同步 `core.platform_accounts.store_name` → **入刷新队列的条件必须显式定义**（当前改名路径是否调用 `_enqueue_shop_identity_refresh` 尚未核实，实施前必须确认；B3"改名不触发全量重算"依赖这一点）。

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
| ⑩ | 别名表区域维度落地 | 同名品牌店可区分 | D10 | A10 |

### 第二批（正本）

| 项 | 内容 | 作用 | 对应决策 | 验收 |
|---|---|---|---|---|
| ③ | 一账号一巡店窗口 | 登录态互相覆盖 | D9 | B1 |
| ④ | 账号标识唯一化 | 串号 | D9 | B2 |
| ⑦ | 改名自动留痕（曾用名） | 追溯困难 | D15 | B3 |
| ⑨ | 改名后按站点自动重认店铺 | 改名后全量人工重认 | D10 + D13 | B5 |
| ⑪ | 内部标准名字段 | 唯一、带地区标识 | §4.1 + D17 | B4 |
| ⑫ | 会话新鲜度与持久化口径 | 过期会话被当新会话用 | D7、D8 | A11 A12 |
| ⑬ | 改名联动与刷新队列口径 | 改名触发全量重算 | D17 | A13 |

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

**第 4 步 —— 曾用名表（D15）**

```sql
CREATE TABLE core.shop_account_store_name_history (
  id              serial PRIMARY KEY,
  shop_account_pk integer NOT NULL REFERENCES core.shop_accounts(id) ON DELETE CASCADE,
  old_value       varchar(200) NOT NULL,
  new_value       varchar(200) NOT NULL,
  changed_at      timestamptz NOT NULL DEFAULT now(),
  changed_by      varchar(100)
);
CREATE INDEX ix_shop_account_store_name_history_account
  ON core.shop_account_store_name_history(shop_account_pk, changed_at DESC);
```

ORM SSOT 同步更新 `modules/core/db/schema_parts/platform.py`。
`core.platform_accounts`（旧表）的 `store_name` 同步逻辑在 `backend/services/shop_sync_service.py:83-103`，不新增列。

---

## 8. 验收标准

### 第一批

- [ ] **A1（会话保存）** 面板「保存会话」执行后，`data/sessions/<platform>/<净化后owner>/storage_state.json` 存在，且文件内 `metadata.saved_at` 更新为当前时间、`metadata.manual_seeded=true`。
- [ ] **A2（失败可见）** `pwcli --session no-such-session-xyz state-save` 的 **exit code ≠ 0**；面板对应操作显示失败，且日志区**可见 stdout/stderr 原文**。
- [ ] **A3（读写同路径）** 对 account_id=`hongxikeji:main`：保存写入 `data/sessions/shopee/hongxikeji_main/storage_state.json`；**再次打开时从同一路径加载**（不是 `hongxikeji:main/`），人工登录态被成功复用。
- [ ] **A4（采集优先用人工会话）** 人工保存会话后触发采集 → `executor_v2` 读取的是 `data/sessions/.../storage_state.json`，而非直接复用 profile 目录。
- [ ] **A5（稳定编号落库）** `public.catalog_files.shop_account_id` 覆盖达 460/460；同一份订单数据重复入库时 `semantic.fact_orders_atomic.shop_id` 保持单一值，`mart.shop_*_kpi` 不重复。
- [ ] **A6（不静默错配）** 构造一个同平台同名多候选的标签 → 落 `shop_id='unknown'` 且带 `identity_warning_code='ambiguous_shop_label'`，**不再**归给排序第一的那个店；三条语义路径（`fact_orders_atomic` / `fact_analytics_atomic` / `fact_orders_monthly_atomic_mv`）判定结果一致。
- [ ] **A7（告警码词表）** `ambiguous_shop_label` / `unmatched_shop_label` 与既有 `unresolved_shop_account` 的并存关系已定义；`fact_orders_atomic` 与 `fact_analytics_atomic` 已具备 `identity_warning_code` / `identity_candidate_count` / `identity_candidates` 列。
- [ ] **A8（别名可认领）** 新建别名 `TK-新加坡-1店` → 其 `alias_normalized` 为 `新加坡1店`（Python 与 SQL 两侧一致），能被 `TK新加坡1店` 的原始数据命中；`normalize_alias_key` 单元测试覆盖 `TK-新加坡-1店` / `Malaysia(Flora Mall)` / `TK新加坡1店` 三个用例。
- [ ] **A9（平台大小写）** `core.shop_account_aliases.platform` 全部为小写；`3c店` 冲突已按 §11 第 2 条的决策消解并留痕。
- [ ] **A10（别名区域维度）** `core.shop_account_aliases.shop_region` 列存在；新唯一约束生效；`FIORO` 可同时挂在 `FIORO_SG` / `FIORO_MY` / `FIORO_PH` 三个店上而不冲突；`shop_region IS NULL` 的存量行不绕过约束。
- [ ] **A11（会话新鲜度）** 读一次会话**不会**刷新 `saved_at`；把 `saved_at` 调到 40 天前 + `last_used_at` 调到当前 → 判定为过期。
- [ ] **A12（持久化口径）** TikTok 走持久 profile 模式时，登录后的 storage_state 仍会落盘，且不会覆盖人工保存的 protected 会话。
- [ ] **A13（改名联动）** 改 `store_name` → 曾用名入表、`core.platform_accounts.store_name` 同步、`core.shop_accounts.store_name` 更新；**刷新队列的触发条件与实际行为一致**（改名不触发 raw 层全量重建）。

### 第二批

- [ ] **B1（一账号一窗口）** 同时打开两个账号的巡店窗口，互不踢掉对方；同一账号重复打开才复用/接管。
- [ ] **B2（账号标识唯一）** 中文账号名不再被 slugify 丢弃；`虾皮巴西（东朗照明主体）` 与 `验证码测试账号` 不再塌成同一个 session 名；`data/sessions` 下不再新增因 slug 塌缩而互相覆盖的目录。
- [ ] **B3（曾用名）** 改名后 `core.shop_account_store_name_history` 可查到旧名与变更时间；改名**不触发**全量历史归属重算。
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
| 候选池排除 disabled 账号 | 历史归属重算，部分行从某店移到 unknown | 单独一次变更 + 全量重算 + 前后对比 |
| `shop_region` 维度让存量别名（NULL 区域）语义漂移 | 老数据匹配行为变化 | NULL = "不限区域"，匹配时 NULL 别名优先级最低，仅当区域内无候选时兜底 |
| 语义层从"归第一"改成"落 unknown" | 短期 `unknown` 行数上升 | 这是暴露而非制造问题；配套面板给出认领清单，逐条处理 |
| `data_hash` 口径变更导致历史行与新行并存 | 短期重复计数 | **先补齐 `catalog_files.shop_account_id` 再改口径**；变更后触发一次全量 semantic 重建；上线前在快照库演练 |
| `save_session` 在保留 protected 旧 state 时仍刷新 `saved_at` | 新鲜度判定失真 | D7 同时修 `session_manager.py:447` |
| 改名触发刷新队列 → raw 层全量重算 | 耗时长 | 改名与刷新解耦（D15/D17）；先只更新映射，不立即重算历史 |
| MATVIEW 变更未刷新 | 线上仍走旧逻辑 | 变更脚本内置 `REFRESH MATERIALIZED VIEW` + 前后行数对比 |

---

## 10. 不在本轮范围

- **IP 隔离**（三处断点：`runtime_session.py:422` 白名单丢 `proxy`、`open_persistent_runtime_bundle` 未传 proxy、`executor_v2.py:1817` 注释声明为预留能力）—— 属独立议题。
- **抓取 TikTok Shop Code** —— 平台侧真实名只能从导出表拿，Shop Code 只在店铺设置页 DOM/API、不在 URL（切店仅用 `?shop_region=`），且用户已明确要求复用现有内容。
- **启用被禁用的主账号**（`虾皮巴西（东朗照明主体）`、`验证码测试账号`）—— 业务决策；但其店铺账号当前**仍在语义层候选池里**，D13 的候选集口径需要单独评估这一项。
- **历史别名孤儿目录清理**（`data/sessions` 下 18~20 个）—— 建议单独一次清理任务，不与本次混做。
- **`core.shop_accounts.platform='验证码测试账号'` 脏行清理** —— 需业务确认（见 §11 第 7 条）。

---

## 11. 需要业务确认的问题

1. **`TK新加坡3C店`（monthly 88 行 / atomic unknown 90 行）归属哪个 TikTok 店？**
   现有 6 个 TikTok 店已被 6 个标签 1:1 占满（`Tiktok 1店` 三店 ← TK新加坡1店/TK马来1店/TK菲律宾1店；`chenzeweinbnb@163.com` 三店 ← TK新加坡2店/TK马来2店/TK菲律宾2店）。
   需要新建第 7 个店账号，还是并入现有某店？
   旁证：`chenewei666:main` 的 `main_account_name='shopee新加坡3C店'`，其 disabled 店 `chenewei666.sg` 持有别名 `3C店` —— 是否即同一"3C 品牌"的 TikTok 侧？
2. **`3c店` 冲突的取舍**：`Shopee3C店`→`zewei_toys.sg`（active+primary，店 enabled=true） vs `3C店`→`chenewei666.sg`（店 enabled=false）。
   D12 的默认规则会保留前者，等于让 disabled 的 3C 店永久无别名 —— 是否为业务意图？
3. **两个 disabled 主账号是否启用**（`虾皮巴西（东朗照明主体）` 6 店、`验证码测试账号` 1 店）？当前它们的面板/采集可见性一致（都看不见），但语义层候选池仍含它们的店铺账号。
4. **三个 FIORO 店的真实归属与 `internal_code` 取值**：`Tiktok 1店` 下 id 62/63/64（DAONE Mall/SG、DAWIE Mall/MY、Explorers Mall/PH）是否就是要改名为 `FIORO` 的三店？
   `internal_code` 取 `FIORO_SG`/`FIORO_MY`/`FIORO_PH` 是否符合业务命名习惯（是否要带平台前缀、是否要带序号、跨主账号如何区分）？
5. **别名 `shop_region` 的回填策略**：存量 21 条别名是否回填区域，还是保留 NULL 作"不限区域"？
6. **`Tiktok 1店` 与 `chenzeweinbnb@163.com` 的归属划分**：两主账号各持 3 个 TikTok 店，标签前缀完全对称（TK+地区+序号），但 `TK新加坡1店` 同时出现在 id 62（SG，active）与 id 63（MY，inactive）—— 疑似历史误录，是否确认？
7. **`core.shop_accounts.platform='验证码测试账号'` 脏行**：随 D12 一起清为 NULL、删除，还是保留为特例？
