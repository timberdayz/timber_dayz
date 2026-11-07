# 停用店铺残留在采集配置里的三层根治 · 方案与实施记录

- 日期：2026-11-07
- 状态：**实施完成，待合并 main + 迁移落库 + 验收**
- 触发：用户在「店铺工作区」截图里发现一行**点不动、也没人说得清为什么**的店铺
- 范围：`backend/domains/collection/routers/collection_config.py`、`backend/domains/collection/routers/shop_accounts.py`、`frontend/src/domains/collection/views/collection/CollectionConfig.vue`、`current_migrations/versions/20261122_remove_disabled_shop_collection_scopes.py`
- 前置批次：[店铺身份未对齐根治](2026-11-06-shop-identity-alignment-remediation.md)（§13.1~§13.8）—— 本批是**同一条根因线的遗留尾巴**

---

## 1. 现象与业务判定

用户截图（采集工作区 / 店铺配置表）里出现一行店铺：

- 那一行**所有数据域复选框都是灰的**，点不动；
- 店铺名显示不出来，只有一串 ID；
- 用户判定：**「停用店铺根本就不应该出现在这个页面上」**。

⇒ 业务口径由此确定：**停用店铺在采集工作区彻底不显示**，而不是"显示成灰的并加个提示"。

## 2. 因果链（开发库实测，非推断）

### 2.1 时间线

| 时刻 | 事件 |
|---|---|
| 2026-11-05 11:55 | `shopee_sg_eternalbloom_local` 的采集 scope 被**创建**（当时它还在营） |
| 2026-11-05 13:23 | 该店被 `manual:fix_shop_identity_alignment` **停用**（上一批身份对齐的副产物） |

⇒ 停用发生在 scope 建成**之后 1.5 小时**，**没人回头清理** ⇒ 残留。

### 2.2 停用只改了一张表

店铺停用只改 `core.shop_accounts.enabled`，而采集配置引用它的是**另外一份数据**：

| 位置 | 内容 |
|---|---|
| `core.collection_config_shop_scopes` | config **31**（monthly，`["analytics"]`）、config **39**（daily，`["products","analytics","services"]` + `{"services":["agent"]}`），两条都是 `enabled=true` |
| `core.collection_config_templates.default_shop_scopes` | template **16**（daily）、**17**（monthly），停用店那一项 `enabled=true` |

### 2.3 为什么变成"一行点不动的复选框"

链路（全部实测）：

1. `collection_config.py:689` `_load_collection_accounts` 只返回 `enabled == True` 的账号 ⇒ 前端 `getAccountById()` **查不到**这个店；
2. `CollectionConfig.vue:1170` `isScopeDomainAvailable()` 取 `account?.capabilities?.[domain]` ⇒ `Boolean(undefined)` = **false** ⇒ **整行 7 个复选框全禁用**；
3. 店名同样取不到（`row.account?.name || scope.shop_account_id`）⇒ 只显示 ID。

### 2.4 数据安不安全：**安全的**

执行侧 `collection_config_execution.py:183-185` 同样按 `enabled == True` 过滤，`245-253` 记 warning 后 `continue`
⇒ **不会真去采集停用店**，数据没错。

**但**顶部统计被带偏了：配置摘要 `account_ids` 里一直挂着这个死账号 ⇒ 「店铺总览 19」与「身份/数据 18」对不上。

### 2.5 模板层更严重：按该模板新建配置会 400

前端新建配置时会把 `selectedTemplate.default_shop_scopes` 整份当 payload 提交
（`CollectionConfig.vue:1353`）⇒ 后端 `_normalize_scope_rows_for_storage` 的 `extra_shop_ids` 校验
（`collection_config.py:587-594`）发现该店不在 `account_map`（只含在营店）⇒ **400**。

## 3. 三层修复（用户拍板"三层全做"）

| 层 | 做什么 | 落点 |
|---|---|---|
| **① 清存量** | 把残留 scope 置 `enabled=false` + 重算配置摘要 + 模板里的停用店项置 `enabled=false` | 迁移 `20261122_remove_disabled_shop_collection_scopes` |
| **② 补停用联动** | 店铺被**停用**或**删除**时，自动摘掉引用它的 scope 并重算摘要 | `shop_accounts.py::_disable_shop_in_collection_scopes` + 两处钩子 |
| **③ 补展示** | 停用店**彻底不出现**在采集工作区（后端响应层过滤 + 前端兜底） | `collection_config.py::_drop_disabled_shop_scopes` + `CollectionConfig.vue` |

### 3.1 为什么用「置 `enabled=false`」而不是物理删除

物理删除**不可逆** —— 删掉之后无法回答"这个店当初配了哪些数据域"。
置为不参与则：采集不再调度它 / 摘要重算时自然排除 / 展示层过滤掉 / **可回滚**（店重新启用后改回 true）。

> 用户下次保存该配置时，前端提交的 scope 不含停用店 ⇒ `_apply_scope_rows` 的
> `config.shop_scopes.clear()` 会把残影**自然物理删除**。两条路都通。

### 3.2 摘要重算口径必须与运行时**逐字等价**

权威实现是 `backend/services/collection_contracts.py::summarize_shop_scopes`。
若迁移算出来的摘要与运行时保存算出来的摘要不一致 ⇒ 用户下次保存配置，顶部数字就会跳。

- ⚠️ 迁移**不 import** 业务模块（迁移应是**冻结的快照**，仓库无此先例）；
- ⇒ 内联一份**逐行同构**的实现（含 `DATA_DOMAIN_SUB_TYPES` 白名单快照）；
- ⇒ 由守护测试断言两者在多组输入下**结果完全一致**；白名单快照另有一条测试断言与业务侧当前值一致。

### 3.3 第三层为什么只改响应、不动 ORM

`config.shop_scopes` 是 relationship，直接赋值会让 SQLAlchemy 把旧行当成 orphan 删除
⇒ **读接口会变成写操作**。所以只改 Pydantic 响应对象。

### 3.4 第二层的一个事实纠正

`collection_config_shop_scopes.shop_account_id` **有** `ON DELETE CASCADE` 外键
（`core.shop_accounts.shop_account_id`）⇒ 删除店铺时 scope 行会被数据库自动带走。

**但配置摘要没人自动重算** ⇒ 不做联动，顶部「店铺总览」会一直挂着一个已经删掉的账号。
⇒ 停用/删除两处钩子仍然必要。

### 3.5 第二层的覆盖边界（诚实说明）

第二层钩子只挂在 **API 路径**（`update_shop_account` / `delete_shop_account`）上。

而这一次残留**不是** API 造成的：`updated_by = 'manual:fix_shop_identity_alignment'`
（API 写入的 `updated_by` 是 `system`）⇒ 是上一批的一次性维护脚本**直接改库**停用的。

⇒ 结论：**任何绕过 API 的直接改库都会绕过第二层** ⇒ 第一层迁移才是兜底。
（未加数据库触发器：启动期不引入这种隐式副作用。）

## 4. 守护测试

`backend/tests/data_pipeline/test_disabled_shop_collection_scope_migration.py`（18 例）：

| 组 | 覆盖 |
|---|---|
| 迁移链 | revision / down_revision 固定；三层都要在 |
| 口径护栏 | 内联实现 ≡ 权威实现（含白名单漂移、legacy 数组、`enabled=false`）；白名单快照 ≡ 业务侧 |
| 存量清理 | scope 被摘掉 / 摘要重算对（**顺序**与**无双重编码**）/ 模板被摘掉 / 幂等 / 可回滚 |
| 第二层 | 停用联动、删除联动、未知店不报错、路由入口真跑（停用与删除各一条） |
| 第三层 | 响应层过滤 + 无停用店时不动响应；前端源码断言 |

> 守护测试用 `AsyncSession.run_sync()` 把同步 Session 喂给迁移 ⇒ **测的就是生产上真正执行的那份代码**，不是测试里复刻的副本。
> 隔离库是 `Base.metadata.create_all` 建的 ⇒ 模型的 `default=` 是 **Python 侧**默认 ⇒ 造数必须走 ORM，裸 SQL 会漏 `batch_status` 这类 NOT NULL 列。

## 5. 实施中发现并修掉的实现缺陷

| # | 缺陷 | 后果 | 修法 |
|---|---|---|---|
| 1 | 迁移内联摘要只认 dict 形态的 `sub_domains`、不过滤白名单 | 与权威口径分叉 | 改为**逐行同构**移植（含 `_normalize_domain_subtypes` + 白名单快照） |
| 2 | 停用联动算完摘要**没有 flush** | 同一事务内后续读到的还是旧值 | 补 `await db.flush()` |
| 3 | 停用联动对**早已 disabled** 的 scope 也改一遍 | `updated_at` 被搅乱、计数失真 | 查询加 `enabled.is_(True)` |
| 4 | 联动与迁移的 scope 排序不一致 | 摘要顺序在"迁移后"与"保存后"之间跳 | 两边都按 `shop_account_id` 排序 |
| 5 | `delete_shop_account` 的注释写"scope 表没有外键级联" | **事实错误** | 实测有 `ON DELETE CASCADE` ⇒ 改正注释并说明"摘要没人管" |

## 6. 顺带定位到的既有缺陷（**不在本批范围**）

**Shopee analytics 域整文件入库失败**（与本批无关，是既有缺陷）：

- 模板 `shopee_analytics__monthly_slash_v3`（id=321，published）声明 `date_format: "dd/mm/yyyy"`；
- 而 Shopee 实际导出已改成 **`dd-mm-yyyy`（连字符）**；
- ⇒ `raw_data_importer.py:627` 抛 `failed to parse metric_date from source_column=日期: 01-11-2026` ⇒ 整个文件失败；
- daily/weekly 模板用 `__file_date_from__`，不受影响。

⇒ 这是「跑一轮真实新采集验证端到端」的**硬阻塞**（受本次身份修复影响最大的正是 Shopee analytics 域，目前无新落库数据可验证）。修法需业务拍板：模板加 `format_candidates` / 改 `date_format` / 改解析器。

## 7. 验证

### 7.1 本轮新增用例

`backend/tests/data_pipeline/test_disabled_shop_collection_scope_migration.py`：**18 例全过**。

### 7.2 全量回归（junit diff）

| | 收集 | 失败 | 备注 |
|---|---|---|---|
| before（`main@a15e5db3`） | 4646 | 156 | |
| after（worktree） | 4664 | 160 | **NEW = 4** |

**NEW failures = 4，归属已逐条查清：**

| 失败 | 归属 | 证据 |
|---|---|---|
| `test_shop_accounts_api::test_status_only_updates_preserve_platform_shop_id_and_disabled_filter_returns_shop` | **本分支引入** | 第二层「写时级联」让 `shop_accounts` 路由要读 `collection_config_shop_scopes`；该测试的 SQLite 夹具只建了 `main_accounts`/`shop_accounts`/`shop_account_aliases`/`shop_account_capabilities` 四张表 ⇒ `sqlite3.OperationalError: no such table: core.collection_config_shop_scopes` |
| `test_shop_rename_flow::test_rename_end_to_end_syncs_three_places_and_keeps_other_fields` | **本分支引入** | 同上 |
| `test_utf8_editor_guardrails_are_declared` | **环境差异** | worktree 缺 `.vscode/settings.json`（被 gitignore，未随 worktree 检出） |
| `test_data_sync_governance_status_consistency::test_governance_detailed_coverage_skips_temp_development_sample_files` | **环境差异** | worktree 缺 `data/`（`data/**/*.json` 被 gitignore）；**已用 `git stash` 隔离证明：把我的改动 stash 掉后该用例仍然失败** ⇒ 与本分支代码无关 |

⇒ 真正需要负责的只有前 2 个；它们的根因正是"写时级联"这个**设计上该取消**的东西
⇒ 处置见《模板 / 同步模块 · 设计层审查与根治方案》§5。

### 7.3 开发库落库状态

- 迁移**尚未落库**（等方案拍板后一并处理）。
- 开发库现状：config 31 / 39 的 `shopee_sg_eternalbloom_local` scope 仍是 `enabled=true`；template 16 / 17 的该店项仍是 `enabled=true`。
