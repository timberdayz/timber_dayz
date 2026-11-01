# 采集会话复用与店铺身份统一 —— 设计规格

- 日期：2026-11-01
- 状态：待评审
- 范围：`modules/utils/pwcli_native.py`、`scripts/pwcli*.{py,ps1}`、`scripts/pwcli_inspection_panel_static/index.html`、`backend/services/data_ingestion_service.py`、`sql/semantic/*`、`backend/domains/collection/routers/shop_account*.py`、`backend/utils/text_normalization.py`、`frontend/src/domains/platform/views/AccountManagement.vue`
- 关联文档：`docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md`、`docs/guides/PWCLI_MANUAL_SHOP_INSPECTION.md`

---

## 1. 要解决的业务问题

两件事互相咬合：

**A. 人工巡店保存下来的会话，采集根本用不上。**
运营在本地巡店面板里逐个账号登录、确认店铺、点「保存会话」，本意是让后续采集直接复用这份"人已经用过的登录态"，少弹验证码、少重复登录。实测结果是：**这个保存动作从 2026-04-01 起就一直是坏的**，面板却始终显示「保存成功」。

**B. 店铺身份靠"名字"认，多地同名必然张冠李戴。**
未来会在 TikTok 开多个地区的同名品牌店（例如三个地区都叫 `FIORO`）。当前系统把"店铺名"同时当成展示名和匹配键，一旦同名，多店数据会全部归到其中一个店，订单重复入账、月度结算出错。

两件事必须一起设计：**会话复用决定"采集拿到的是哪个账号的登录态"，店铺身份决定"采回来的数据算哪个店的"。**

---

## 2. 已实测确认的事实（设计依据）

### 2.1 巡店会话链路：三个根因，全部可复现

| # | 位置 | 现象 | 复现命令 |
|---|---|---|---|
| 根因 1 | `modules/utils/pwcli_native.py:320` | `from modules.utils.sessions.session_manager import SessionManager` 在 `scripts/pwcli.ps1:7` 用 `& python <repo>/modules/utils/pwcli_native.py` 启动时，`sys.path[0]` 是脚本目录而非仓库根 → `ModuleNotFoundError: No module named 'modules'`。**打开即回写、保存会话全部失效。** 该导入由 2026-04-01 提交 `662d3c13` 引入，且此文件从未有过任何 `sys.path.insert` → 已坏约 7 个月 | `python modules/utils/pwcli_native.py --session X open <url> --headed --account-id "Y"` |
| 根因 2 | `scripts/pwcli.ps1:7` | 结尾是 `& python $ScriptPath @CliArgs`，**没有 `exit $LASTEXITCODE`**；`Open-PwcliPlatform`/`Save-PwcliPlatformState` 都不检查退出码；面板 `scripts/pwcli_inspection_panel.py:183` 只看 `result.exit_code != 0` → **永远为假，面板永远显示成功** | `pwcli --session no-such-session-xyz state-save` → 打印 `No browser session found for 'no-such-session-xyz'`，**exit code = 0** |
| 根因 3 | `scripts/pwcli_helpers.ps1:204-212` | `Save-PwcliPlatformState -AccountId X` 中 **`X` 完全没被用于定位会话**，只用 `$env:PLAYWRIGHT_CLI_SESSION`（`Get-PwcliActiveSession`, :113-119）。面板是全新 Python 进程、不注入该变量，机器级/用户级也为空 → 落到 `pwcli state-save`，session 被解析为 `"default"` → `require_session("default")` 失败 | `Save-PwcliShopeeState -AccountId 'hongxikeji:main'` → `No browser session found for 'default'`，**exit code = 0**；磁盘旁证 `output/playwright/.pwcli_native/sessions/default/` 只剩空 `profile/`、无 `session.json` |

配套问题：`scripts/pwcli_inspection_panel_static/index.html:320` 的日志只渲染 `result.status`，**不渲染含真实 stdout/stderr 的 `result.message`** → 失败原因对用户完全不可见。

### 2.2 巡店与采集确实共用同一套目录（这部分是对的，不要动）

- `modules/utils/pwcli_native.py:163-164` `runtime_account_profile_dir` 与 `SessionManager.get_persistent_profile_path` 净化规则完全一致 → 巡店与采集共用同一 profile 目录（实测 `profiles/shopee/hongxikejimain` 与 live session `udd` 一致）。
- `pwcli_native.py:310-333` `save_default_storage_state_from_context` → `SessionManager.save_session` → 写入路径与采集读路径一致。

**结论：不需要重做会话存储设计，只需要把断掉的三处接上。**

### 2.3 一处目录不一致（真实 bug，会让巡店登录态加载不到）

`modules/utils/pwcli_native.py:167-175` `runtime_account_state_path` 用**原始 account_id**（`data/sessions/shopee/hongxikeji:main/`），而 `SessionManager` 读写用 `_safe_filename`（`data/sessions/shopee/hongxikeji_main/`）。

磁盘上只存在后者 → **巡店时对 `xxx:main` 形式账号根本没加载 storage_state**。
（profile 目录名 `hongxikejimain` vs session 目录名 `hongxikeji_main` 的差异是既定设计，`backend/tests/test_session_storage_roots.py:30-31` 已断言，不要改。）

### 2.4 店铺身份：三个"名字"目前被塞进一个字段

`core.shop_accounts.store_name` 现在存的是**平台侧真实店名**：

| 平台 | store_name 样例 | platform_shop_id | shop_region |
|---|---|---|---|
| tiktok（6 个） | `DAWIE Mall`、`Malaysia(Flora Mall)`、`Singapore(HX Home)` … | **全部 NULL**（0/6，status=missing） | 6/6 有值 |
| shopee（13 个 enabled） | `xhkj1.my`、`xhkj11.sg`、`hx_home.ph` … | 13/13 有值 | 13/13 有值 |
| miaoshou（1 个） | `xihong` | NULL | `''` |

而 `core.shop_account_aliases` 存的是**内部中文标签**，不是平台店名：

```
('tiktok', 'TK菲律宾1店', '菲律宾1店', 'Explorers Mall', 'PH', primary=True, active=True)
('shopee', 'Shopee马来3店', '马来3店', 'xhkj13.my', 'MY', primary=True, active=True)
```

**关键实测：妙手 ERP 导出文件的「店铺」列，填的就是我们自己的中文别名。**
`b_class.fact_tiktok_orders_monthly`（4662 行，100% 覆盖）的 `(店铺,站点)` 分布：

```
('TK菲律宾1店', '菲律宾', 2171)   ('TK新加坡1店', '新加坡', 1427)
('TK马来1店',   '马来',   503)    ('TK菲律宾2店', '菲律宾',  279)
('TK新加坡2店', '新加坡',  120)   ('TK新加坡3C店','新加坡',   88)
('TK马来2店',   '马来',    74)
```

而 `raw_data` 里真正的身份字段只有 4 个键，且只有 2751/4662（59%）有值：

```
main_account_id  2751 行，取值全部 = 'miaoshou_real_001'（妙手主账号，对 TikTok 无区分度）
shop_account_id  2751 行，取值全部 = 同一个
store_name       2751 行，取值全部 = 'xihong'
shop_id          4662 行，取值全部 = 'xihong'
```

**所以 TikTok 订单在 raw 层唯一可用、且真正起作用的店铺身份，就是妙手导出的「店铺」列（= 别名值）+「站点」列（= 区域）。** 这一点被 live 语义层的解析结果反向印证：

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

### 2.5 别名机制的两个真 bug

**Bug A —— 写侧与查侧规范化规则不一致。**

| 侧 | 规则 | `TK-新加坡-1店` 的结果 |
|---|---|---|
| 写侧（Python，`backend/utils/text_normalization.py:68` `normalize_alias_key`） | 小写 + 折叠空白 + 剥平台前缀，**不删分隔符** | `新加坡-1店` |
| 查侧（SQL，`shop_identity_resolution_candidates.sql:70-80` 等） | 剥前缀 + 删 `[[:space:]_()/-]+` | `新加坡1店` |

→ **认领了也可能永远匹配不上。** 现在 21 条别名恰好都是无分隔符的中文标签，两侧结果碰巧相同，才没暴露。

**Bug B —— 平台代码大小写分裂，唯一约束形同虚设。**
别名表里 `platform` 同时存在 `'Shopee'` / `'shopee'` / `'Tiktok'` / `'tiktok'` 四种写法：

```
('Shopee', '3C店',      '3c店', 'chenewei666.sg', SG, primary=False, active=False)
('shopee', 'Shopee3C店','3c店', 'zewei_toys.sg',  SG, primary=True,  active=True)
('Tiktok', '菲律宾1店', '菲律宾1店', 'Philippines(DAJU Mall)', PH, primary=False, active=False)
('tiktok', 'TK菲律宾1店','菲律宾1店','Philippines(DAJU Mall)', PH, primary=True,  active=True)
```

唯一约束是 `UniqueConstraint("platform","alias_normalized","is_active")`（`modules/core/db/schema_parts/platform.py:227`）—— **大小写敏感，所以 `'Shopee'` 和 `'shopee'` 可以同时 active 一个 `3c店`**。一旦统一大小写，现有数据立刻冲突。

**附带**：`core.shop_account_aliases` 的 `UniqueConstraint` 使得**同平台同一别名只能 active 一条** → 三个 `FIORO` 不可能同时归给三个店。**别名必须引入区域维度。**

### 2.6 live 语义层有三套并存的解析逻辑，且都带 `LIMIT 1`

| 视图 | 来源文件 | 解析方式 |
|---|---|---|
| `semantic.fact_orders_atomic` | `sql/semantic/orders_atomic.sql`（2026-06-09） | `LATERAL` 扫 `shop_accounts`，条件是 **`store_name` 等值 OR 别名匹配**，`LIMIT 1` |
| `semantic.fact_analytics_atomic` | `sql/semantic/analytics_atomic.sql`（2026-06-09） | `LATERAL` 扫候选视图 `LIMIT 1` |
| `semantic.fact_orders_monthly_atomic` | `sql/semantic/orders_monthly_atomic_mv.sql`（2026-06-18） | `LATERAL` 扫候选视图 `LIMIT 1` |

候选视图 `semantic.shop_identity_resolution_candidates` 的优先级：`platform_shop_id`(1) → `shop_account_id`(2) → `alias_match`(3) → `store_name_match`(4)，**没有区域维度**。

**这就是改名的红线：** 一旦多个店的 `store_name` 相同且该名字出现在导出数据里，`LIMIT 1` 会把它们的行全部归给 `ORDER BY ... LIMIT 1` 选中的那一个。

实测（只读模拟）：把 `Tiktok 1店` 的三个店 `store_name` 全改为 `FIORO` → 候选数 3 → 胜出者 `tiktok_my_dawie_mall_local`，**三店数据全归 MY 店**。

### 2.7 改名当前"不会"立刻塌缩——因为妙手导出用的是中文标签

2.4 已证明妙手「店铺」列 = 中文别名标签，所以**只要不把平台侧真实店名写进导出文件的店铺列，改 `store_name` 本身不影响现有 4662 行 TikTok 数据的归属**。

但这层安全是"碰巧"的，不是"设计"的"。两个明确的引爆点：

1. `semantic.fact_orders_atomic` 的 `store_name` 等值匹配 —— 只要导出里出现 `FIORO`，立刻塌缩。
2. 仓库里 `sql/semantic/orders_atomic.sql` / `analytics_atomic.sql` 已改成"名字反查"为主，**一旦部署到 live 并叠加同名改名**，就是活的生产事故。

### 2.8 采集侧的会话短路点（会话线现有设计缺陷，一并纳入）

- `modules/apps/collection_center/executor_v2.py:924`：`if (not has_persistent_profile and effective_storage_state is None and session_owner_id:)` —— **profile 目录非空时，`data/sessions` 下的 JSON 根本不读**。人工在面板保存的会话，对已有 profile 的账号无效。
- `modules/apps/collection_center/runtime_session.py:458-462` `_profile_contains_state` 仅判断 `any(profile_path.iterdir())` —— 目录非空即视为"有会话"。
- `modules/utils/sessions/session_manager.py:523-525` `load_session` **每次读取都回写文件**并刷新 `last_used_at`；`_session_freshness_timestamp`(:108-121) 取 `saved_at/last_used_at/created_at` 最大值 → **30 天过期机制实际永不触发**；文件 mtime 失去参考价值（实测 `Tiktok 1店` mtime 是今日，但 `saved_at` 停在 2026-06-22）。
- `modules/apps/collection_center/executor_v2.py:2822` `_should_skip_post_login_session_persist`：TikTok 走持久 profile 时**不落 storage_state**。

### 2.9 数据健康缺口（需要业务确认，不在代码范围内）

- `TK新加坡3C店`（新加坡，90 行）→ 别名表里**没有这个标签**，`core.shop_accounts` 里也**没有对应的 TikTok 店铺账号**（只有 shopee 的 `chenewei666.sg`，且 `enabled=false`）。这 90 行订单当前归属 `unknown`。
- `core.shop_accounts` 有一行 `platform='验证码测试账号'`（平台字段填了主账号名），属脏数据。
- 2 个主账号 `enabled=false`（`虾皮巴西（东朗照明主体）` 6 店、`验证码测试账号` 1 店）→ 面板与采集同时看不见，一致但属业务死区。
- `data/sessions` 下 27 个 owner 目录中约 21 个是历史别名孤儿（如 `Leslieshop_main`←旧 `Leslieshop:main`，`xihong`←现 `miaoshou_real_001`）。

---

## 3. 概念定义（本设计的核心）

必须把三个被混为一谈的"名字"分开：

| 概念 | 载体 | 是否唯一 | 是否参与数据匹配 | 例子 |
|---|---|---|---|---|
| **平台侧真实店名** | `core.shop_accounts.store_name`（现有列） | 可重名 | 是（现状），改为只经别名表间接参与 | `FIORO`、`DAWIE Mall`、`xhkj1.my` |
| **内部标准名** | `core.shop_accounts.internal_code`（**新增列**） | 同平台内唯一 | **否**（仅供人读与内部引用） | `FIORO_SG`、`FIORO_MY`、`FIORO_PH` |
| **原始导出标签** | `core.shop_account_aliases.alias_value` | 平台内 + 区域内唯一 | **是（唯一的真实匹配锚点）** | `TK菲律宾1店`、`Shopee3C店` |

**内部标准名不参与匹配。** 数据归属只走 `(平台, 原始导出标签, 区域)`。

---

## 4. 对用户两个问题的直接回答

### 4.1 标准名怎么改？——**用户手动改，系统给建议值 + 自动做配套**

**分工**：

| 谁 | 做什么 | 为什么 |
|---|---|---|
| **系统自动** | 按 `store_name` + `shop_region` 生成建议值：`DAWIE Mall` + `MY` → `DAWIE_MALL_MY`；`xhkj1.my` + `MY` → `XHKJ1_MY`（先剥离名称里已含的地区后缀，再大写化、非字母数字转 `_`、拼 `_` + 区域码） | 区域是现成的可靠锚点（主账号内 100% 唯一、全平台 100% 有值） |
| **用户手动** | 在账号管理页现有编辑弹窗里确认或修改建议值 | 平台侧真实店名我们不知道，**不能自动生成**；标准名是业务命名决策（要不要带平台、要不要带序号），**必须人定** |
| **系统自动** | 唯一性校验；同平台内冲突时在建议值后追加主账号短标识（如 `FIORO_MY_T1`），最终命名权仍归用户 | 同平台两个主账号各开一个 `FIORO_MY` 会撞车，必须能自动消歧 |
| **系统自动** | 改名时自动记曾用名；同步 `core.platform_accounts.store_name`（否则 `dim_shops` 会被打回旧名，见 `backend/services/shop_sync_service.py:85`）；同主账号下唯一性校验 | 这些是"改名动作的必然副作用"，手工做必然漏 |

**唯一约束**：`UniqueConstraint("platform", "internal_code")`（同平台内唯一，跨平台允许同名 —— 匹配本来就带 platform 维度，不会歧义）。

**"FIORO" 这个平台侧真实店名要不要进别名表？** 要。但因为 `UniqueConstraint("platform","alias_normalized","is_active")` 的存在，裸 `FIORO` 只能给一个店 → **别名表必须引入区域维度**（见 §5.2）。

### 4.2 改名时间点？——**不迫近，但必须排在语义层改造之后**

理由：妙手导出用的是中文别名标签而非平台店名，**改 `store_name` 当下不会让现有数据塌缩**；真正的红线是语义层的 `store_name` 等值 + `LIMIT 1`（§2.6）。

结论：

1. **⑤⑥⑧（语义层止血）先做**，它们不依赖改名，且是订单重复入账的直接成因。
2. **改名放在第二批之后**，且改名时**必须同时**为平台侧真实店名建带区域维度的别名记录 —— 否则改名那一刻就是塌缩时刻。
3. 如果业务侧确实要把 TikTok 三店改成 `FIORO`，请在第一批完成后提出，届时 §5.2 已就位。

---

## 5. 设计决策

### 5.1 会话线

**D1 — 会话保存走"显式路径注入"，不依赖环境变量。**
`Save-PwcliPlatformState -AccountId X` 必须用 `X` 定位会话（拼出 `shopee-shopee-<slug>-inspect` 形式的 session 名，与 `Open-PwcliPlatform` 保持同一套拼法）。`PLAYWRIGHT_CLI_SESSION` 只作为显式覆盖时的次选。

**D2 — 退出码必须传播到面板。**
`scripts/pwcli.ps1` 结尾补 `exit $LASTEXITCODE`；`Open-PwcliPlatform` / `Save-PwcliPlatformState` 捕获 `$LASTEXITCODE` 并在非 0 时 `throw`；面板 `run_action` 同时看退出码与 stderr。

**D3 — 面板日志必须渲染 `result.message`（含 stdout/stderr 原文），不只是 `result.status`。**

**D4 — 修复 `sys.path`，让 `pwcli_native.py` 无论从哪个目录启动都能 import `modules.*`。**
在 `pwcli_native.py` 顶部按 `__file__` 推出仓库根并 `sys.path.insert(0, root)`。这是最小改动，且对 `python modules/utils/pwcli_native.py` 与 `python -m modules.utils.pwcli_native` 两种启动方式都成立。

**D5 — `runtime_account_state_path` 改用 `SessionManager` 的净化规则**，与 `get_persistent_profile_path` 对齐（复用 `SessionManager` 内部的 `_safe_filename`，不另写一份）。

**D6 — 采集侧会话读取顺序修正。**
`executor_v2.py:924` 的短路条件改为：当存在 `session_owner_id` 且 `data/sessions/<platform>/<owner>/session.json` 存在时，**优先使用该 storage_state**（人工巡店保存的），而不是"profile 目录非空就跳过一切"。会话质量门禁沿用 `runtime_session.py:74-136` 的 TikTok 质量评分（该门禁在 `executor_v2.py:255-309` 的 executor 版 bootstrap 里缺失，需补齐）。

**D7 — 会话新鲜度以 `saved_at` 为准，不再被 `last_used_at` 掩盖。**
`load_session` 的"读时回写"改为"仅在内容真正变化时回写"；`_session_freshness_timestamp` 以 `saved_at` 为主，`last_used_at` 只作辅助。文件 mtime 恢复参考价值。

**D8 — TikTok 持久 profile 模式下也要落 storage_state。**
`executor_v2.py:2822` 的 `_should_skip_post_login_session_persist` 需排除"人工保存的会话"这一来源，否则 D6 拿到的会话会被后续采集覆盖。

### 5.2 身份线

**D9 — 匹配锚点升级为 `(platform, alias_normalized, shop_region)`。**
`core.shop_account_aliases` 新增 `shop_region` 列（可空；NULL 表示"不限区域"，兼容存量），唯一约束改为 `(platform, alias_normalized, shop_region, is_active)`。这样 `FIORO` 可以同时挂在 `FIORO_SG` / `FIORO_MY` / `FIORO_PH` 三个店上。

**D10 — 写侧与查侧共用同一套规范化，且必须幂等、可解释。**
`backend/utils/text_normalization.py` 的 `normalize_alias_key` 改为与 SQL 侧完全一致：剥平台前缀 → 小写 → 折叠空白 → 删 `[[:space:]_()/-]+`。SQL 侧统一改为**直接使用存储的 `alias_normalized`**，不再在查询里做第二次规范化（消除双份规则）。`normalize_alias_key` 成为唯一真源，并加单元测试锁定。

**D11 — 平台代码大小写统一为小写。**
`core.shop_account_aliases.platform`、`core.shop_accounts.platform`、`core.main_accounts.platform` 统一小写化。存量 `Shopee`/`Tiktok` 两行需要先合并（与 `shopee`/`tiktok` 下的同名 alias 冲突时，按"保留 active 且 primary 的那条、其余降为 `is_active=false` 且 `is_primary=false`"处理）。**注意 `3c店` 在 `Shopee3C店`(zewei_toys.sg, active) 与 `3C店`(chenewei666.sg, 非active) 之间已经存在这个冲突，迁移时必须显式决策。**

**D12 — 多候选不静默归一，落 `unknown` + 告警码。**
语义层解析从 `ORDER BY priority, shop_id LIMIT 1` 改为：
- 候选唯一 → 归属该店；
- 候选 0 → `unknown` + `identity_warning_code='unmatched_shop_label'`；
- 候选 > 1 → `unknown` + `identity_warning_code='ambiguous_shop_label'`，并在 `semantic.fact_*_atomic` 暴露 `identity_candidate_count` 与 `identity_candidates`（供"未匹配店铺别名"面板消费）。

这与 `docs/guides/UNIFIED_SHOP_IDENTITY_PRINCIPLES.md` 第 6 条"`unknown` 是治理信号"一致。

**D13 — 数据落库用稳定身份编号，不用名字。**
`backend/services/data_ingestion_service.py:494-495` 的 `file_shop_id = file_record.shop_id or "none"` 改为优先 `shop_account_id`（全平台 20/20 覆盖、永不变化），`platform_shop_id` 次之。`:627-637` 的 `data_hash` 作用域中把 `shop_id` 换成稳定身份编号，避免改名/重命名造成同一份数据重复入库、`semantic.fact_orders_atomic.shop_id` 分裂、`mart.shop_*_kpi` 聚合断裂。

**D14 — 曾用名独立成表，不复用别名表。**
新增 `core.shop_account_store_name_history`（`shop_account_pk`、`old_value`、`new_value`、`changed_at`、`changed_by`）。理由：复用别名表会 (a) 撞平台唯一约束，(b) 每次改名触发全量历史归属重算（`shop_account_aliases.py:347` → `RefreshQueueService.enqueue_refresh` → raw 层全量重建）。

**D15 — 别名应用级约束从"同平台同别名只能一个"放宽为"同平台同别名同区域只能一个"。**
`backend/domains/collection/routers/shop_account_aliases.py:297-307` 的 409 判定同步放宽；`_clear_primary_aliases`(:164-180) 保持"旧别名仅降 `is_primary`、`is_active` 仍为 True"的语义（曾用名机制已现成可用）。

**D16 — 店铺改名联动。**
`backend/domains/collection/routers/shop_accounts.py:363-405` 的 `update_shop_account` 从裸 `setattr` 改为带联动的更新：唯一性校验 → 写曾用名 → 同步 `core.platform_accounts.store_name` → 必要时入刷新队列。

---

## 6. 落地批次

### 第一批（止血）

| 项 | 内容 | 作用 | 涉及文件 |
|---|---|---|---|
| ① | 巡店会话真能保存 | 采集反复登录、被弹窗打断 | `pwcli_native.py`（D4/D5）、`pwcli.ps1`、`pwcli_helpers.ps1`（D1/D2）、`pwcli_inspection_panel.py`、`index.html`（D3） |
| ② | 失败不谎报 | 白跑一轮、无从排查 | 同上（退出码 + 日志渲染） |
| ⑤ | 采集用店铺身份编号落库 | **订单重复入账、月结算错** | `data_ingestion_service.py`（D13）、`core.platform_accounts` 同步 |
| ⑥ | 认不准就不猜 | 数据张冠李戴 | `sql/semantic/*`（D12）、`core.shop_identity_resolution_candidates` 视图 |
| ⑧ | 修别名认领失效 | 90 行数据认不出店 | `text_normalization.py` + SQL 侧统一（D10）、平台大小写统一（D11）、`TK新加坡3C店` 认领 |

外加 D9 的别名表区域维度（`shop_region` 列 + 唯一约束调整）—— D9 是 D12 与未来同名品牌店的共同前置，**放在第一批**。

### 第二批（正本）

| 项 | 内容 | 作用 | 涉及文件 |
|---|---|---|---|
| ③ | 一账号一巡店窗口 | 登录态互相覆盖 | `pwcli_native.py:701-709` `command_open` 只杀同名 session → 改为按账号维度隔离 |
| ④ | 账号标识唯一化 | 串号 | `scripts/pwcli_account_inventory.py:48-55` `slugify` 丢弃全部非字母数字（中文全丢）→ 改为保留中文或用稳定哈希 |
| ⑦ | 改名自动留痕（曾用名） | 追溯困难 | 新表 `core.shop_account_store_name_history`（D14） |
| ⑨ | 改名后按站点自动重认店铺 | 改名后全量人工重认 | 别名区域维度（D9）+ 语义层区域匹配（D12） |
| 新 | 内部标准名字段 | 唯一、带地区标识 | `core.shop_accounts.internal_code` + 账号管理页 |

---

## 7. 数据模型变更汇总

```sql
-- core.shop_accounts
ALTER TABLE core.shop_accounts
  ADD COLUMN internal_code varchar(100);           -- 内部标准名，同平台内唯一
ALTER TABLE core.shop_accounts
  ADD CONSTRAINT uq_shop_accounts_platform_internal_code UNIQUE (platform, internal_code);

-- core.shop_account_aliases
ALTER TABLE core.shop_account_aliases
  ADD COLUMN shop_region varchar(50);             -- 区域维度，NULL = 不限
ALTER TABLE core.shop_account_aliases
  DROP CONSTRAINT uq_shop_account_aliases_active_alias;
ALTER TABLE core.shop_account_aliases
  ADD CONSTRAINT uq_shop_account_aliases_active_alias
  UNIQUE (platform, alias_normalized, shop_region, is_active);

-- 新表：曾用名
CREATE TABLE core.shop_account_store_name_history (
  id            serial PRIMARY KEY,
  shop_account_pk integer NOT NULL REFERENCES core.shop_accounts(id) ON DELETE CASCADE,
  old_value     varchar(200) NOT NULL,
  new_value     varchar(200) NOT NULL,
  changed_at    timestamptz NOT NULL DEFAULT now(),
  changed_by    varchar(100)
);
```

ORM SSOT 同步更新 `modules/core/db/schema_parts/platform.py`。

---

## 8. 验收标准

### 第一批

- [ ] **A1（会话保存）** `pwcli --session <real-session> state-save` 成功后，`data/sessions/<platform>/<owner>/session.json` 存在且 `saved_at` 更新为当前时间；`modules/utils/pwcli_native.py` 在**仓库根**与**其他目录**两种 cwd 下启动均不抛 `ModuleNotFoundError`。
- [ ] **A2（失败可见）** `pwcli --session no-such-session-xyz state-save` 的 **exit code ≠ 0**；面板对应操作显示失败，且日志区**可见 stdout/stderr 原文**。
- [ ] **A3（账号定位）** `Save-PwcliPlatformState -AccountId 'hongxikeji:main'` 写入的 session 路径是 `data/sessions/shopee/hongxikeji_main/`（净化后），**不是** `hongxikeji:main/`；面板「保存会话」按钮对不同账号写入**不同**文件。
- [ ] **A4（采集优先用人工会话）** 对某账号：人工保存会话后触发采集 → `executor_v2` 读取的是 `data/sessions/.../session.json`，而非直接复用 profile 目录。
- [ ] **A5（稳定编号落库）** 同一份 TikTok 订单数据在 `shop_account_id` 不变的情况下重复入库 → `semantic.fact_orders_atomic` 中 `shop_id` 保持单一值，不出现分裂；`mart.shop_*_kpi` 聚合不重复。
- [ ] **A6（不静默错配）** 构造一个同平台同名多候选的标签 → 落 `shop_id='unknown'` 且带 `identity_warning_code='ambiguous_shop_label'`，**不再**归给排序第一的那个店。
- [ ] **A7（别名可认领）** 新建别名 `TK-新加坡-1店` → 其 `alias_normalized` 与查侧规范化结果一致（`新加坡1店`），能被 `TK新加坡1店` 的原始数据命中；`core.shop_account_aliases.platform` 全部为小写。
- [ ] **A8（存量归位）** `TK新加坡3C店`（90 行）要么有归属店铺账号并归位，要么明确登记为待认领项并在面板可见；`semantic.fact_orders_atomic` 的 tiktok `unknown` 行数下降或转为有据可依。

### 第二批

- [ ] **B1（一账号一窗口）** 同时打开两个账号的巡店窗口，互不踢掉对方；同一账号重复打开才复用/接管。
- [ ] **B2（账号标识唯一）** 中文账号名不再被 slugify 丢弃；`data/sessions` 下不再新增因 slug 塌缩而互相覆盖的目录。
- [ ] **B3（曾用名）** 改名后 `core.shop_account_store_name_history` 可查到旧名与变更时间；改名**不触发**全量历史归属重算。
- [ ] **B4（标准名）** 账号管理页可编辑「内部标准名」，系统给出 `FIORO_SG` 形式建议值；同平台内重名被拒绝并给出冲突详情。
- [ ] **B5（改名后自动重认）** TikTok 三店 `store_name` 改为 `FIORO` 后，新采集数据的归属仍按区域正确分流到三个店，且无 `LIMIT 1` 塌缩。

### 回归护栏

- [ ] `backend/tests/test_session_storage_roots.py` 仍通过（session 目录名与 profile 目录名不同是既定设计）。
- [ ] `backend/tests/test_collection_session_reuse_contract.py` 仍通过（load 优先于 bootstrap）。
- [ ] `sql/semantic/` 下三个事实表视图的解析逻辑统一到同一套候选视图 + 告警码，**不再**各自实现 `LIMIT 1`。

---

## 9. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 别名表唯一约束放宽后出现同平台同别名同区域两条 active | 匹配歧义 | 迁移脚本显式消解存量冲突（D11），并加约束校验脚本 |
| `shop_region` 维度让存量别名（NULL 区域）语义漂移 | 老数据匹配行为变化 | NULL = "不限区域"，匹配时 NULL 别名优先级最低，仅当区域内无候选时兜底 |
| 语义层从"归第一"改成"落 unknown" | 短期 `unknown` 行数上升 | 这是暴露而非制造问题；配套面板给出认领清单，逐条处理 |
| `data_hash` 口径变更导致历史行与新行并存 | 短期重复计数 | 变更后触发一次全量 semantic 重建；上线前在快照库演练 |
| 改名触发刷新队列 → raw 层全量重算 | 耗时长 | 改名与刷新解耦（D14）；先只更新映射，不立即重算历史 |

---

## 10. 不在本轮范围

- **IP 隔离**（三处断点：`runtime_session.py:422` 白名单丢 `proxy`、`open_persistent_runtime_bundle` 未传 proxy、`executor_v2.py:1817` 注释声明为预留能力）—— 属独立议题。
- **抓取 TikTok Shop Code** —— 平台侧真实名只能从导出表拿，Shop Code 只在店铺设置页 DOM/API、不在 URL（切店仅用 `?shop_region=`），且用户已明确要求复用现有内容。
- **启用被禁用的主账号**（`虾皮巴西（东朗照明主体）`、`验证码测试账号`）—— 业务决策。
- **历史别名孤儿目录清理**（`data/sessions` 下约 21 个）—— 建议单独一次清理任务，不与本次混做。
