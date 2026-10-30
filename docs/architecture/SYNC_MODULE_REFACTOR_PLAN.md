# 采集同步模块 · 前后端一体优化方案

> 状态：**第 1~4 批已全部落地并提交（本地，未 push）**；历史数据修复**脚本已交付但未执行**。
> 审查范围：`backend/services/{template_hash_policy, semantic_hash_policy_service, semantic_field_registry, template_save_readiness_service, field_mapping_template_service, template_family_service, template_semantic_binding_backfill}.py`、`backend/domains/data_platform/routers/field_mapping_templates.py`、`frontend/src/components/dataSync/{TemplateUpdateWorkbenchDrawer,TemplateDeduplicationReviewPanel}.vue`、`frontend/src/domains/data_platform/utils/{deduplicationSelection,headerBindings}.js`
> 取证方式：真实库只读查询 + 真实 HTTP 接口重放 + node 直跑前端真实模块 + 后端日志还原用户操作序列。全部结论标注了 `文件:行号`。
> 交付提交：`3367d211`（第 1 批 前端止漏）、`f26248f0`（第 2 批 后端口径归一）、`b1b34dfe`（数据修复脚本）、`482705d6`（第 3 批 状态机与家族校验）、`f2b09f5c`（第 4 批 环境与可观测）、`4cf795a1`（数据修复脚本增强 + 真实库执行）、`c5d77f71`（前端守卫测试路径约定修复，见 §3.3）。

---

## 0. 触发事件与一句话结论

用户在做模板更新时看到红色阻断 `orders data requires order_id as a semantic hash identity field.`，但**从未触碰过 order_id**。

**根因**：前端在「需要人工复核」视图里编辑任意一行语义映射时，用**当前视图可见的 2 行**替换了**全量 89~91 条绑定**（`TemplateUpdateWorkbenchDrawer.vue:854`、`:859-861`）；随后用这 2 条绑定重新归一化用户已选的 4 个去重字段，`order_id / product_id / sku_id` 被**静默丢弃**（`deduplicationSelection.js:50-76`）；后端按"用户提交的那份清单"判定，orders 域要求 order_id ⇒ 阻断。而后端回写的归一化结果又把这 1 个字段固化下来（`TemplateUpdateWorkbenchDrawer.vue:888-897`），**用户再也无法通过界面把 order_id 加回来**（`el-select` 同值不触发 change）。

**orders 域要求 order_id 本身是对的，不动**（依据见 §3.4）。

---

## 1. 四个层面的根因

### L1 前端｜视图状态被当成了数据基底

`activeBindingSource`（`TemplateUpdateWorkbenchDrawer.vue:642-647`）的语义是"**当前表格显示哪些行**"，但 `handleSemanticKeyChange`（`:853-879`）把它当成"**要保存哪些绑定**"：

- `:854` `updateHeaderBindingSemantic(activeBindingSource.value, ...)` —— 输入是残缺集合；
- `:859-861` `fullHeaderBindings.value = nextBindings` —— **用残缺集合整体覆盖全量表**；
- `:862` `localHeaderBindings.value = nextEditedBindings` —— 同样只剩复核行。

默认 `bindingsViewMode = 'needs-review'`（`:423`），而 `localHeaderBindings` 装的是后端 `review_header_bindings`（`:608-612`，后端 `_filter_bindings_for_manual_review` 只保留 pending/冲突行，`field_mapping_templates.py:372-402`）⇒ **默认视图下基底恒为 2 行**。

不可逆：`headerBindings.js:590-624` 的 `updateHeaderBindingSemantic` 用 `.map()`，**输出条数 == 输入条数、不补齐缺失行**；`deduplicationSelection.js:90-114` 的 `mergeHeaderBindingsForSave` 也只做并集 ⇒ **被截断的行永远回不来**。

### L2 前端｜静默剔除 + 没有自救入口

- `deduplicationSelection.js:50-76`：遍历的 `fields` 是**语义键**，但查表用的是 `bindingByRaw`（键为**表头原文**，`:8-22`）⇒ 语义键永远查不中，只能落到 `:73` 的 `semanticKeys.has(value)`；而 `semanticKeys` 只收 `confirmed_semantic` 的绑定（`:23-29`）⇒ 查不到就**什么都不做地走完循环**，无提示、无标记。
- **同一字段两处默认互相矛盾**：`:698` 显示层按「空状态 = 已确认」放行，`deduplicationSelection.js:57` 提交层按严格判断丢弃。
- **自救入口不可达**：order_id 已确认 ⇒ 不进复核表（`:699`）；要手工确认必须切到 `All Fields`，但该行下拉框的值**本来就是** `order_id`（`:846-851`），而 Element Plus `useSelect.mjs:326-329` `if (!isEqual(props.modelValue, val)) emit(CHANGE_EVENT, val)` ⇒ **同值不 emit** ⇒ `handleSemanticKeyChange` 不会被调用 ⇒ 永远写不进 `confirmed_semantic`。
- **回写固化**：`handleHashPolicyChange`（`:881-898`）用后端 `normalized_deduplication_fields` 直接替换用户选择，没有差异提示。

### L3 后端｜读写两套语义 + 确认闸门事实上失效

- **库里根本没有状态字段**：模板 345 的 91 条 binding 里，**`semantic_review_status` 这个键压根不存在**（同样不存在 `hash_eligible`）——实测 binding 里出现过的键只有 `aliases / confidence / display_name / hash_participates / position / raw_name / required / sample_type / semantic_key / semantic_role`。来源是回填脚本 `template_semantic_binding_backfill.py:84-92` 只写 `raw_name/display_name/semantic_key/position`。
- **读取侧兜底**：`_filter_review_candidates` 同源的 `:388-390` 按「空状态 + 有语义键 ⇒ confirmed_semantic」放行 ⇒ **接口层看起来一切正常**。
- **保存侧自动确认**：`:668-673` 在请求未带合法状态但能推断出语义键时**自动写 `confirmed_semantic` 并落库**（`:1166` → `:1275` → `field_mapping_template_service.py:120`、`:134-136`）；legacy `mappings` 命中也强制确认（`:744`）。
  ⇒ **含义**：模板 345 **只要成功保存过一次**，91 条绑定就会带齐状态，后续不再丢字段。当前因 L1/L2 永远保存不成功 ⇒ **死锁无法自愈**。
- **`hash_eligible` 从不落库**：Pydantic 模型 `field_mapping_template.py:23-37` 与归一 payload `:687-701` 都没有该字段，而后端自己还在读它（`:395`）、前端把它当硬闸门（`deduplicationSelection.js:26`、`:58`）⇒ **前端的第二道闸门在真实数据上恒不生效**。
- **两道闸口径不一致**：保存实际过 readiness（`template_save_readiness_service.py:79-155`）与 hash policy（`template_hash_policy.py:398-445`）两道闸；`shop_id` 在 hash policy 侧按系统字段豁免（`:432-433`），在 readiness 侧**没有豁免**（`:128-145`）⇒ 系统自动追加的 `shop_id`（`deduplication_fields_config.py:116-140`）可能把保存拦下，且提示指向用户无法自己修的方向。
- **派生字段三套口径**：`_invalid_deduplication_keys` 的 `derived_semantic_keys`（`template_hash_policy.py:414-421`，宽）与 readiness（`:97-104`，宽）一致，但 `_derived_selected_sources`（`:358-374`）额外要求 `source_column in FILE_DATE_SOURCE_COLUMNS`（窄），而 products 周期闸门（`:198`）查的正是窄口径 ⇒ **同一键在"可作 hash 键"与"可作周期键"上判定相反**。
- **策略按粒度分、资格判定不看粒度**：`evaluate_option` 第一行 `del granularity, sub_domain`（`semantic_hash_policy_service.py:55`），而 `validate` 按粒度分裂要求（`template_hash_policy.py:166-225`）⇒ 同一份文件 daily 通过、weekly/monthly 失败。

### L4 数据契约｜一个字段扛三个含义 + 两把尺子

`deduplication_fields` 同时承担：

1. 用户选择的"去重字段"（业务语义）；
2. **hash 计算的键名列表**（物理实现，按**字面拼写**，`deduplication_service.py:142-152`：`is_canonical_semantic_key(field_text)` 对中文名不通过 ⇒ 退回按原始列名匹配 ⇒ 键名变成中文）；
3. **家族一致性校验的语义键集合**（逻辑判断，`field_mapping_templates.py:146-167` `_canonical_user_hash_key_set` 把两者都归一化成语义键 ⇒ 判"完全一致"）。

**实测（同一行数据、同一 scope、同一 bindings）**：

| `deduplication_fields` | 实际 `data_hash` | 家族校验尺子 |
|---|---|---|
| `['product_id','platform_sku','sku_id','order_id']` | `6f63ee40504f66d5…` | `{product_id,platform_sku,sku_id,order_id}` |
| `['产品ID','平台SKU','SKU ID','订单号']` | `7b9a4f0acd2c9741…` | **同上 ⇒ 判"一致"** |
| `['订单状态','产品ID','平台SKU','SKU ID']` | `77574a63924567dc…` | `{product_id,platform_sku,sku_id}` |

⇒ **假一致**：语义键集合一致，hash 却不同。

**库里正好存在这一对**：id=344 `shopee_orders__weekly_v3`(archived) 用中文名，id=345 `shopee_orders__weekly_v4`(published) 用语义键；另 id=312/314/316 用 `订单编号`、id=344 用 `订单号` ⇒ 同一列两种写法。

**库内后果（实测）**：`b_class.fact_shopee_orders_weekly` **114 组**业务键对应多个 `data_hash`；`_monthly` **410 组**；weekly 同一批文件 2828 被写了两遍（`template_id=345` 721 行 vs `template_id=NULL` 558 行）。
⚠️ **归因未坐实**：重复确实存在（已证），但"中文名 vs 语义键是唯一成因"尚未排除（`metric_date`/绑定差异同样会改 hash）。本方案先修机制，数据回填另立专项。

---

## 2. 目标模型：四个单一事实来源

| # | 目标 | 落地方式 |
|---|------|---------|
| **T1** | **语义键唯一表示** | `deduplication_fields` **只存 canonical semantic_key**；表头名只存在于 `header_bindings[].raw_name`。历史中文名模板需迁移（§3 第 3 批）。 |
| **T2** | **hash 身份键唯一定义** | `SemanticHashPolicyService.evaluate_option` 是唯一权威（含域级/粒度级限制与 `blocked_reason`）；前端**不再本地重算** `eligible`。 |
| **T3** | **确认状态唯一来源** | `semantic_review_status` 必须落库；读写两侧使用**同一套**默认规则；"自动推断"默认 `pending`，只有用户显式确认才写 `confirmed_semantic`（自动确认可保留为迁移期开关）。 |
| **T4** | **绑定集合单一载体** | 视图模式只控制**显示**；编辑对象与提交集合**永远**取全量绑定表。前端任何"缩减"必须是用户显式操作 + 可见提示。 |

---

## 3. 改造清单

### 第 1 批｜前端止漏（不动后端契约、不动数据，可独立提交）

| # | 改动 | 位置 |
|---|------|------|
| 1.1 | 拆分 `activeBindingSource`：新增 `bindingBase`（恒为全量 `fullHeaderBindings`/`fullContextHeaderBindings`），视图模式只控显示 | `TemplateUpdateWorkbenchDrawer.vue:642-647` |
| 1.2 | `handleSemanticKeyChange` 用**全量表**按 `raw_name` 定位、只替换目标行；不再写回残缺集合 | 同上 `:853-879`（`:854`、`:859-862`） |
| 1.3 | 归一化改为**只增不删**，并返回「被移除项 + 移除原因」，前端渲染成标黄提示 | `deduplicationSelection.js:1-88` |
| 1.4 | 后端归一化回写改为**只增不删**；收窄时只提示不覆盖 | `TemplateUpdateWorkbenchDrawer.vue:881-898` |
| 1.5 | 每行提供**独立、幂等的「确认映射」按钮**（绕开 `el-select` 同值不 emit） | 同上 `:256-263`、`:835-851` |
| 1.6 | 提示文案：优先展示后端中文可执行文案（`missing_required_groups[].message`），并用 `accepted_keys` 生成「点这里去确认『订单号』」引导；英文 `legacy_error` 降为次要/折叠 | `TemplateDeduplicationReviewPanel.vue:386-400`、`DataSyncTemplates.vue:791-824`、`:846`、`:852`、抽屉 `:941-943` |
| 1.7 | 保存改为可等待（`await` 父页 handler），失败原因回传抽屉就地展示 | 抽屉 `:938-976`、父页 `DataSyncTemplates.vue:857-958` |
| 1.8 | `reloadContext` 加请求令牌；重载只更新"服务端事实"，保留"用户本地编辑"与视图偏好 | 抽屉 `:978-997`、`:604-629` |
| 1.9 | 移除前端对 `hash_eligible` 的判断（该字段后端从不落库，恒不生效） | `deduplicationSelection.js:26`、`:58` |
| 1.10 | `effectiveHashOptions` 合并顺序改为**后端优先**（本地只补 `raw_name`/`label`） | 抽屉 `:494-536`（`:533`）、`TemplateDeduplicationReviewPanel.vue:288-300` |

### 第 2 批｜后端口径归一（不改数据）

| # | 改动 | 位置 |
|---|------|------|
| 2.1 | `hash_eligible` 二选一：**补落库**（由 `evaluate_option` 回填）**或全局移除**。推荐移除（T2） | `field_mapping_template.py:23-37`、路由 `:687-701`、`:395` |
| 2.2 | readiness 复用 `SYSTEM_SCOPE_FIELD_SET` 豁免；两道闸的错误文案统一来源 | `template_save_readiness_service.py:128-145`、`template_hash_policy.py:432-433` |
| 2.3 | "derived"收敛为**一个**函数（保留日期列约束）；products 周期闸门改查 `resolved_keys`，消除 daily/weekly 判定相反 | `template_hash_policy.py:358-374`、`:414-421`、`:198`、`template_save_readiness_service.py:97-104` |
| 2.4 | `evaluate_option` 承接**域级**限制（inventory 不接受 `product_name`），把错误提前到"选择阶段" | `semantic_hash_policy_service.py:108-121`、`template_hash_policy.py:251-269` |
| 2.5 | `visitor_count.hash_eligible` 改 `False`（消除与 `kind="metric"` 的自相矛盾） | `semantic_field_registry.py:181-188` |
| 2.6 | 删除死代码与重复元数据：路由 `:753-774` 两个无调用封装、`:1039-1047` 不可达块、`PRODUCT_OPTIONAL_IDENTITY_KEYS`、`_derived_selected_keys`、`is_hash_eligible_semantic_key`；registry `:8-56` 初版（被 `:393-401` 覆盖） | 见各处 |
| 2.7 | 异常不吞：投影失败进响应标志；`list_templates`/`get_template` 的异常上抛而非返回空集合 | `field_mapping_template_service.py:137-145`、`:230-232`、`:261-263` |
| 2.8 | `blocking_errors` 改用中文 `message`，`legacy_error` 仅作 `legacy_error` 字段并存 | `template_hash_policy.py:137-138`、`:226-233` |

#### 第 2 批实施后的口径修订（2026-10-30，附实证）

| # | 原计划 | 实际落地 | 原因 |
|---|-------|---------|------|
| 2.3 | derived 收敛为**一个**函数，products 周期闸门改查 `resolved_keys` | 拆成**两个有名有责**的函数：`_file_companion_date_sources`（窄：来源列是 `__file_date_from__`/`__file_date_to__`，代表"文件伴生日期"，不区分行，只作周期标识）与 `_parse_rule_provided_keys`（宽：只要有解析规则产出该语义键就算"有数据来源"）。**products 周期闸门保持查窄口径** | ① 窄口径是"行内列 vs 文件伴生日期"的语义分界：若把窄口径放宽成宽口径，`metric_date ←「日期」` 这类**行内日期列**会被踢出 `user_identity_fields` ⇒ hash 不再区分日期 ⇒ **不同日期的行互相覆盖**（严重回归）。② daily 用 `metric_date`、monthly 用周期边界，是**刻意的粒度差异**（`test_products_monthly_requires_period_boundaries_not_metric_date_only` 在保护它），不是 bug；强行统一会破坏该测试且降低月粒度精度。真正要消除的是"同一个词三套含义"，已通过改名 + 单一职责达成。 |
| 2.8 | `blocking_errors` 改用中文 `message` | **双轨并存**：`blocking_errors` 保持英文原文（向后兼容，既有测试 `backend/tests/test_template_hash_policy.py:99-101`、`:292-294` 断言精确相等），**新增** `blocking_messages`（纯中文）+ `requirement_groups[].legacy_error` 字段 | 直接替换会破坏既有契约测试。中文文案通过 `blocking_messages` / `missing_required_groups[].message` 双通道提供，前端优先读中文（第 1 批已改）。 |
| 2.2 | readiness 复用 `SYSTEM_SCOPE_FIELD_SET` 豁免 | 已落地，并**额外**把"绑定是否已确认"的判定抽成共享函数 `resolve_binding_review_status`（`semantic_field_registry.py`），hash 闸门 / readiness 闸门 / hash_options / hash_participates 四处统一使用 | 方案 L3 指出"读取侧兜底空状态=已确认、写入侧却不兜底"这一矛盾。共享函数消除了同一绑定在四处得到不同结论的可能。**既有测试零影响**（全部显式带 `semantic_review_status`），但**真实库 17 个模板由"被误阻断"变为"可保存"**。 |

**第 2 批真实库验证结果**（`scripts` 下的一次性脚本，真实库只读）：

- 检查 253 个模板 → **17 个判定结果变化，0 个回归**（全部是"解除误阻断"方向）；
- 其中包括用户当时被阻断的模板 **345 `shopee_orders__weekly_v4`（published）**：`invalid_keys` 从 `['order_id','platform_sku','product_id','sku_id']` 变为 `[]`，`can_save` 从 `False` 变为 `True`；
- 变化原因：模板 345 的 91 条 binding **没有** `semantic_review_status` 字段（历史数据从未落库），读取侧按"空状态+有语义键 ⇒ 已确认"放行，而 hash 闸门与 readiness 闸门却严格判断 ⇒ 同一绑定在两端结论相反。统一后消除。

#### 第 2 批剩余（与第 3 批 worker 文件重叠，待其结束后补做）

- 2.1 `hash_eligible` 从 binding 层移除（`backend/schemas/field_mapping_template.py:23-37`、路由 `:687-701`、`:395`）；
- 2.6 路由死代码删除（`:753-774` 两个无调用封装、`:1039-1047` 不可达块）；
- 2.7 异常不吞（`field_mapping_template_service.py:137-145`、`:230-232`、`:261-263`）。

### 第 3 批｜数据与状态机（**需单独授权数据修复**）

| # | 改动 | 说明 |
|---|------|------|
| 3.1 | 保存链路合并为**单事务**；响应增加 `family_id / active_version_id / projection_status` | `field_mapping_template_service.py:135-162`、`template_family_service.py:520`、schema `:180-194` |
| 3.2 | 家族校验改比"**实际参与 hash 的字段对**"，直接复用 `deduplication_service` 的解析函数；archived 版本也参与比较 | `field_mapping_templates.py:125-167`、`:962-1037` |
| 3.3 | 历史模板 `deduplication_fields` 统一重写为语义键 + 已入库行 `data_hash` 重算（**本次未授权执行**） | 需先在一次性库验证影响面 |
| 3.3a | **已交付脚本**：`scripts/normalize_template_deduplication_fields.py`（干跑 / `--apply` / `--restore`），测试 `backend/tests/test_normalize_template_deduplication_fields.py`（11 项，隔离库） | 干跑诊断结论见 §3.1 |
| 3.4 | 事实表**列策略**：当前 weekly 表 104 列里堆叠了至少 4 代模板的表头（`订单编号` #92 有值 98.5%；`订单号`/`平台SKU`/`SKU_ID` 全空 0%；另有 `ID`/`商品`/`平台`/`买家支付` 与 `col_3pl运费折扣` 这类改名列）⇒ 需要"新版本用新列 / 重建宽表"的明确策略 | `b_class.fact_shopee_orders_weekly` |
| 3.5 | 契约失效提升为一等状态（`contract_invalid`）+ 契约回填（当前 459 个文件仅 24 个带契约） | `template_variant_takeover_service.py:281-334`、`template_contract_service.py:253-289` |
| 3.6 | 抽唯一 `resolve_template_for_file(platform, domain, granularity, sub_domain, account)`，供入库判定/治理看板/投影三处共用（消除"严格 5 维 vs 3 级降级"与 `_legacy_shadow_compare` 第三把尺子） | `data_sync_template_status_service.py:75-98`、`template_matcher.py:95-160`、`template_family_service.py:248-262` |

#### 第 3 批实施结果（2026-10-30）

| 方案项 | 实际落地 | 关键取舍 |
|-------|---------|---------|
| 3.1 | 保存链路合并为单事务（`async with db.begin()`）；投影失败整体回滚并抛 `TemplateFamilyProjectionError`，路由转错误码 1003，**不再"报成功但没投影"**；响应新增 `family_id`/`active_version_id`/`projection_status` | — |
| 3.2 | 家族校验改比「实际参与 `data_hash` 的字段对」：比较对象是 `{身份键: 实际取值来源列}`，身份键判定与 `calculate_data_hash` **完全同序**（先对**原文**判 canonical，中文列名不会被提升）。这修掉了「中文名 vs 语义键」被判「完全一致」的**假一致** | **archived 版本参与比较但只提示不阻断**（阻断基准仍是最新 published）。若 archived 也阻断，`shopee/orders/weekly` 家族会被**永久锁死**（用户既改不了历史版本，也存不进新模板），而历史口径修复属未授权的数据变更 |
| 3.5 | 契约失效提升为一等状态：新增 `contract_status`（`valid`/`invalid`/`missing`）+ `contract_invalid` + `contract_fallback{applied,reason,fallback_template_id}`，在全部返回路径透出；读取契约抛异常不再静默（记入 `contract_resolution_status` 并合并进返回体） | — |
| 3.6 | 抽出唯一 `resolve_template_for_file`（异步 + 同步孪生），入库判定 / 治理看板 / 家族投影三处共用；`resolve` 调用已传 `account` | 消除了"resolver 报 missing_family、匹配器报有模板"的两套结论 |
| 新增 | 家族投影**版本化**：每次发布新增一条 version 行、旧行置 `superseded`，历史版本可返回；删除模板改为**归档 + 同事务重投影**（该维度无 published 模板时家族 `governance_status='missing_template'`、`active_version_id=NULL`） | 前端变体表会一并列出历史变体（`flattenVariants` 展平所有版本），未擅自裁剪 |

**本轮额外补上的一层（关键，否则 3.2 会在用户保存一次后失效）**：

新增 `semantic_review_source` 字段区分「用户明确确认」与「系统按表头名推断」：

| 来源 | 前端标记 | 后端落库 |
|------|---------|---------|
| 批量推断（`normalizeHeaderBindings`） | `inferred` | `inferred` |
| 用户在下拉框改（`updateHeaderBindingSemantic`） | `user` | `user` |
| 用户点「确认映射并加入」 | `user` | `user` |

只有**非 `inferred`** 的确认绑定才允许被提升成语义身份。没有这一层区分，「产品ID」会被当成 `product_id` ⇒ 3.2 修掉的假一致会在用户保存一次模板后**重新出现**（前端原先对所有推断出的键一律标 `confirmed_semantic`，后端保存侧也会自动确认）。

同时把「绑定是否已确认」的判定统一到 registry 的 `resolve_binding_review_status`，消除读取侧与两道闸门各判一套的旧矛盾。

### 第 4 批｜环境与可观测

| # | 改动 | 说明 |
|---|------|------|
| 4.1 | **修正超时预算倒置**：DB `statement_timeout` 必须 < 前端超时（`api/index.js:30-32` 的注释要求如此，实际 120s > 70s）⇒ DB 设 60s，前端保持 70s | `frontend/src/api/index.js:25-37`、`backend` DB 配置 |
| 4.2 | `/api/dashboard/clearance-ranking` 慢查询治理（索引/预聚合）。实测该查询跑满 120s，间隔 71/72/73 秒重试，且占满事件循环使模板请求排队 | `frontend/src/api/dashboard.js:113`、`data_sync.py` 对应实现 |
| 4.3 | 错误文案区分"超时 / 断网 / 服务端错误"（现在 `timeout of 70000ms exceeded` 被当网络错误原样抛出） | `frontend/src/api/index.js:688-708` |

#### 第 4 批实施结果（2026-10-30）

| 项 | 实际落地 | 与原计划的差异 |
|---|---------|---------------|
| 4.1 | 连接池级默认**保持 120s 不变**（`DB_POOL_STATEMENT_TIMEOUT_MS`）——Celery/后台批量采集导入直接用 `AsyncSessionLocal()`、不经过请求级预算，把池默认值砍到 60s 会打断这些长事务。**新增按路径分级的请求级预算**，用 `SET LOCAL` 局部收紧：`/dashboard` 60s（前端 70s）、普通接口 25s（前端 30s）、`/preview` 50s（前端 60s）、`/mapping` 80s（前端 90s）、`/ingest` 170s（前端 180s）、`/collection` 290s（前端 300s）、`/governance` 60s（前端 120s）、`/scan` 60s（前端 120s） | 原计划是「DB 统一设 60s」。实测 governance/scan 的耗时在 **Excel 表头解析（纯 IO）** 而非 DB 侧，故按路径分级比全局一个值更贴合余量 |
| 4.2 | 视图层优化（`sql/api_modules/clearance_ranking_module.sql`）：去掉 `to_jsonb(o)->>'...'` 整行转 jsonb、去掉金额的 `numeric→text→正则→numeric` 往返、把 `mart.inventory_backlog_base` 从 LATERAL 的 N+1 重复计算物化成 CTE、LATERAL 驱动行去重成 `(ranking_month, platform_code, sku_key)`。选行规则与输出列保持原样 | 原计划写的是「索引/预聚合」。实测真正的主因是 **LATERAL N+1 放大**（原视图即使只留 tiktok 一个平台也 >600s 打不出来），单加索引不解决 |
| 4.3 | 新增 `classifyRequestFailure` / `buildFailureMessage`，区分 timeout / network / server / http 四类。**不改变任何既有错误字段契约**（`message`/`response`/`data`/`isNetworkError`/`code`/`type` 原样保留），只新增分类字段 | 无差异 |

**4.2 慢查询实测对比**

| | 优化前 | 优化后 |
|---|---|---|
| 真实接口 `GET /api/dashboard/clearance-ranking` | **HTTP 500 @ 120.09s**（DB statement_timeout） | 视图 SQL **42.5 / 43.5 / 43.7s**（3 次实测） |
| LATERAL 选行阶段 | 18.1s（tiktok 单平台） | **1.03s**（17 倍） |
| 全量 atomic 扫描 | 24.9s | 24.9s（剩余成本在此，需要配合"月窗口下推"才能再降） |

⚠️ **两个必须知道的事实**：

1. **视图定义变更不会自动生效**。`refresh_runner.py:409-413` 明确「普通视图的数据是查询时实时算的，定义变更请走 `scripts/rebuild_views.py` 显式重建」。
2. **真实库当前生效的视图与仓库最终文件不等价**。`ops.pipeline_run_log` 显示 **2026-10-30 05:51 UTC（13:51 本地）** 有一次 `bootstrap_postgresql_dashboard.clearance_ranking` 自动重建，它读到的是当时工作区里**尚未写完的中间版本**。两者差异是实质性的：中间版本把 `b.platform_code = m.platform_code AND b.sku_key = m.sku_key` 放在 LATERAL 的 **JOIN ON** 侧，最终版本放在 LATERAL 子查询的 **WHERE** 侧 —— 后者才会先按 sku 过滤再按日期取最新，前者会先全局取最新一行再由 ON 过滤。CTE 结构（`order_months / order_sku_month / backlog_rows / stagnant_before_month / shop_month`）两者一致。
   ⇒ 对齐命令：`python scripts/rebuild_views.py --target api.clearance_ranking_module`（会短暂持有排他锁）。

#### 视图重建对齐（2026-10-30，已执行）

- 备份当前库内视图定义 → `C:\Users\...\AppData\Local\Temp\clearance_ranking_module_backup.sql`（4334 字符）。
- 执行 `python scripts/rebuild_views.py --target api.clearance_ranking_module` ⇒ **成功 1 个、失败 0 个**。
- **重建前后逐词对比**（语义 token 差异为空，逐词差异仅 8 词且全部是 DDL 外壳 `CREATE OR REPLACE VIEW ... AS` 与备份文件多出的一个分号；`WHERE 侧含 sku_key 匹配` 重建前后**均为 True**）。

> ⚠️ **纠正上一版的错误结论**：先前判定"真实库视图与仓库文件不等价"是**误读** —— PostgreSQL 会把视图定义做字面量规范化存储（`btrim` 小写、`''::text`、`NOT (EXISTS (...))`、自动补表名限定与括号），这些是**存储格式差异**，不是语义差异。必须用逐词归一化或结果集对比来判断，不能靠字符串 diff。重建后库内定义与仓库文件**逐词等价**。
- 重建后复测耗时：全量 **44.27s**、限 200 行 **47.24s**，与优化后的 42.5~43.7s 同一量级。
- ⚠️ 视图**仍恒返回 0 行**（见 §5「待确认」），这是**既有生产缺陷**、非本次重建引入。

---

## 3.1 数据修复诊断结论（2026-10-30，只读诊断；执行结果见 §3.2）

脚本：`scripts/normalize_template_deduplication_fields.py`（干跑模式），验证：`backend/tests/test_normalize_template_deduplication_fields.py`（18 项，隔离库全绿）。

> ⚠️ 本节记录的是**首轮诊断**（脚本初版，仅"表头名 → 语义键"替换）。脚本随后做了能力增强并**已对真实库执行**，见 §3.2。本节表格里的「可安全改写 2 个」是初版口径。

**核心结论：历史模板的去重字段配置本身是错的，不只是"写法不统一"。**

| 指标 | 数值 | 依据 |
|------|------|------|
| 配置了 `deduplication_fields` 的模板 | **114** 个 | 真实库查询 |
| 其中可**安全自动改写**（表头名 → 语义键且改写后仍通过两道闸门） | **2** 个（id=286、298，analytics 的 `日期` → `metric_date`） | 脚本干跑 |
| 改写后**仍不通过**闸门 ⇒ 保持原样并需人工确认 | **112** 个 | 脚本干跑 |
| 库内 `header_bindings` 总条数 / 其中带 canonical `semantic_key` 的 | 3703 / **143**（3.9%） | 真实库查询 |
| 全局可唯一复用的 表头名 → 语义键 映射 | 22 个（`订单号`/`订单编号`→`order_id`、`产品ID`→`product_id`、`平台SKU`→`platform_sku`、`SKU ID`→`sku_id`、`商品名称`→`product_name`、`日期`→`metric_date` 等） | 跨模板学习 |

**112 个模板失败的根因（两类，都不是"改个写法"能解决的）**：

1. **把业务属性/度量列写进了去重字段** —— 如 `订单状态`、`满意度`、`聊天询问`、`被分配会话数`、`规格编号`、`规格名称`、`全球商品货号`、`状态`、`访客数`。这些列**无法区分行**，放进 Data Hash 只会让同一行在不同批次算出不同 hash（它们是值，不是身份）。
2. **缺少域级必需身份键** —— 如 orders 域缺 `order_id`、products 域缺 `product_id`（或周期边界）、services 域缺 `service_id`。脚本已逐模板输出「还缺这些身份键」清单。

⇒ **需要业务/数据侧确认后才能修**：初版脚本刻意**不**自动补齐缺失身份键（补哪个、从哪列补，是业务判断，不是机械映射）。§3.2 的增强版改为**受控补齐**：只有模板自身确实有数据来源（已确认绑定 / 解析规则）时才补，补齐后复验两道闸门。

**事实表重复现状**（真实库实测，归因未完全坐实）：

> ⚠️ 分组口径说明：下表按**该表实际存在的全部业务键列**分组（weekly 含 `订单号`/`订单编号`/`产品ID`/`平台SKU`/`商品` 等，其中部分列 100% 为空，会把同组行拆得更散）；§1 L4 里的「weekly 114 组 / monthly 410 组」用的是更窄的键集 `(platform_code, shop_id, 订单号, 产品ID, 平台SKU)`。两者口径不同，**同一张表在不同键集下组数差异极大**，这本身也说明"事实表里到底哪些列算业务键"缺少统一约定。

| 表 | 行数 | 业务键重复的冗余行 | 同一业务键对应多个 `data_hash` 的组数 |
|----|------|-------------------|------------------------------|
| `b_class.fact_shopee_orders_weekly` | 1298 | 18 | 12 |
| `b_class.fact_shopee_orders_monthly` | 26627 | **5261** | **2807** |
| `b_class.fact_tiktok_orders_weekly` | 208 | 0 | 0 |
| `b_class.fact_tiktok_orders_monthly` | 4662 | 852 | 657 |

⚠️ **本脚本刻意不做 `data_hash` 重算**。原因：事实表是**展开后的宽表**（weekly 表 104 列里堆叠了至少 4 代模板表头，`订单号`/`平台SKU`/`SKU_ID` 三列 100% 为空，`订单编号`(#92) 98.5% 有值），无法按入库时的行结构逐字节重建；强行重算会与既有行的 hash 全部错位，把"重复"变成"两份不同 hash 的同一行"，需要配套的合并/清理决策与回滚方案，超出本次授权。

---

## 3.2 数据修复执行结果（2026-10-30，脚本增强 + 真实库已执行）

### 3.2.1 脚本能力增强（`scripts/normalize_template_deduplication_fields.py`）

初版只做"表头名 → 语义键"替换，命中率极低。本轮补齐四项能力：

| # | 能力 | 说明 |
|---|------|------|
| E1 | **非身份字段剔除** | 表头名在语义字段注册表里**完全不存在**、也没有任何模板能给出映射 ⇒ 判为业务属性/度量，从去重字段中剔除。判定留痕（`evidence`：`binding_without_semantic_key` / `no_binding` / `semantic_metric`），并汇总成「被剔除的列名清单」供人工审阅 |
| E2 | **业务列名提示（按域限定）** | `商品编号`→`product_id`、`规格编号`→`sku_id`（仅 products 域）、`客服id`→`service_id`（仅 services 域）。**只写在脚本内**，不改全局 registry —— registry 是全局语义契约，随手加别名会改变 `normalize_semantic_key` 行为，进而影响历史 hash 取值路径与前后端一致性测试 |
| E3 | **受控自动补齐** | 域级必需身份键（orders→`order_id`、products→`product_id`、services→`service_id`…）缺失时，**只有"模板自身确实有数据来源"**才补：① 模板有已确认绑定指向该语义键；② 解析规则能产出该语义键。**绝不凭空造出没有数据的键**；补齐后必须复验两道闸门 |
| E4 | **解析规则来源列保护** | 解析规则的 `source_column` 是**有数据**的（规则把这一列解析成某个语义键），不能当成"无效列"剔除。唯一派生键 ⇒ 改写；多派生键 ⇒ 判为多候选、保持原样 |

其它口径修正：
- 补齐 `sub_domain` 参与两道闸门判定（`orders` 明细子域的 `line_id`/`sku_id` 要求依赖它，初版恒传 `None`）。
- 剔除后**不允许剩下空身份键集**；两道闸门（readiness + hash policy）复验不通过 ⇒ 整体跳过、不改写。

### 3.2.2 真实库执行结果

执行命令：`python scripts/normalize_template_deduplication_fields.py --apply --backup <备份>`（脚本自带 `--restore` 回滚；另有全量 253 模板快照做二次兜底）。

**改动范围：253 个模板中仅 5 个 `deduplication_fields` 发生变化，248 个未动。**

| 模板 | 域/粒度 | 状态 | 改前 | 改后 | 动作 |
|------|---------|------|------|------|------|
| 286 `tiktok_analytics__daily_v2` | analytics/daily | archived | `['日期']` | `['metric_date']` | 替换 |
| 298 `tiktok_analytics__monthly_v2` | analytics/monthly | archived | `['日期']` | `['metric_date']` | 替换 |
| 357 `tiktok_orders__daily_v4` | orders/daily | archived | `[..., '订单状态']` | `[...]` | 剔除 |
| 359 `tiktok_orders__daily_v5` | orders/daily | **published** | `[..., '订单状态']` | `[...]` | 剔除 |
| 364 `tiktok_analytics__monthly_v5` | analytics/monthly | archived | `['metric_date','退款金额']` | `['metric_date']` | 剔除 |

**被剔除的列名清单（人工审阅）**：

| 列名 | 涉及模板 | 证据 | 判定依据 |
|------|---------|------|---------|
| `订单状态` | 357、359 | `binding_without_semantic_key` | 该列的 binding `semantic_key = null`（从未被确认为任何语义键）；同表的 `订单号` → `order_id` 已确认。状态是**值**不是身份 |
| `退款金额` | 364 | `binding_without_semantic_key` | 同上；`metric_date` 已确认，退款金额是**度量**不是身份 |

### 3.2.3 执行后验证

| 检查项 | 结果 |
|--------|------|
| 5 个改动模板的保存就绪闸门 `can_save` | ✅ 5/5 = True |
| 5 个改动模板的 hash 策略 `passed` | ✅ 5/5 = True |
| 改后 `resolved_keys` | 286/298=`['metric_date']`；357/359=`['order_id','platform_sku','product_id','sku_id']`；364=`['metric_date']` |
| **幂等性**（重跑规划，待改写模板数） | ✅ **0** |
| **家族 hash 口径一致性**（357 archived vs 359 published） | ✅ 字段对完全一致：`{'product_id':'产品ID','platform_sku':'平台SKU','sku_id':'SKU ID','order_id':'订单号'}`，`is_compatible=true`（此前因 `订单状态` 参与 hash 而不一致） |
| 事实表是否被触碰 | ✅ 未触碰：`b_class.fact_*` 的 `ingest_timestamp` 最大值（2026-10-26 / 2026-10-29）**早于**本次写入时间（2026-10-30 06:32 UTC） |
| **回滚演练**（`--restore` → 重新 `--apply`） | ✅ 回滚后 253 个模板与改前快照 **0 差异**；重新应用后与首次应用后的快照 **0 差异** ⇒ 改动**完全可逆且幂等** |

### 3.2.4 剩余 109 个模板（**口径纠正：不是「109 次人工确认」**）

> ⚠️ **2026-10-30 第 9 轮纠正**：本节原标题「剩余 109 个模板的 binding 语义映射人工确认」
> 容易被读成「有 109 个模板要人工逐条确认字段」。**不是这个意思。**
>
> * **109** = 真实库里 114 个配置了 `deduplication_fields` 的模板 − 本轮已安全改写的 5 个，
>   说的是「**还没被归一化的模板数**」；
> * 「人工确认」指的是**在工作台里把映射确认下来**这一个动作，
>   而不是「每个字段都要逐条点一遍」。
>
> 真正的人工量在 §3.5 被重新量化过：改完之后，114 个模板里 **94 个**在
> 「重新进一次工作台」后就能正常保存，**剩下的 20 个**才是真需要业务判断的。

真实库 114 个配置了 `deduplication_fields` 的模板，根因分布：

| 根因 | 模板数 | 说明 |
|------|-------|------|
| `deduplication_fields` 已全部是规范语义键，**且**绑定有 confirmed 语义键 | 14 | 本就合规，无需改写 |
| `deduplication_fields` 已全部是规范语义键，**但绑定缺 confirmed 语义键** | 31 | 卡点在 `header_bindings`，不在去重字段 |
| `deduplication_fields` 含表头名 | 69 | 其中 5 个可安全改写（见 §3.2.2），其余 64 个仍被绑定层卡住 |

**全库 binding 复核状态分布（3703 条）**：

| 状态 | 条数 | 带 canonical `semantic_key` |
|------|------|----------------------------|
| `pending` | 3558 | 0 |
| `confirmed_semantic` | 143 | 143 |
| `confirmed_non_semantic` | **2** | 0 |

⇒ **95.9% 的绑定从未被确认**。这正是第 1 批前端工作台要解决的问题：**语义映射必须由用户在界面上确认**，不能由脚本对每一列盲目猜测。

脚本**刻意不自动补 binding 的 `semantic_key`**：那只会把第 3 批刚修掉的「假一致」（推断即确认）重新制造出来。`semantic_review_source` 已能区分 `user` / `inferred`，自动推断出来的键不能当 `confirmed_semantic` 用。

⇒ **这 109 个模板的归一，前提是在工作台确认字段映射**（§3.5 已把它拆成
「系统能自动认出的」和「真要人判断的」两类，并给出量化结果）。

> ⚠️ **2026-10-30 第 9 轮补充**：上面这条「不自动推断」后来被细化成两件不同的事，
> 不要混为一谈：
>
> | | 做什么 | 谁做 | 状态 |
> |---|---|---|---|
> | **列名识别** | 看到表头 `商品编号` 就知道它是 `product_id` | 系统（**按数据域限定**） | ✅ 已做，见 §3.5 |
> | **映射确认** | 把某一列**认定**为某个语义身份 | 人（工作台点「确认映射并加入」） | 由用户在工作台完成 |
>
> 列名识别的结果一律标记 `semantic_review_source=inferred`，
> 家族 hash 一致性比较仍然只认 `user` ⇒ **不会制造「假一致」**。

### 3.2.5 仍未授权、未处理

- **`data_hash` 重算**：仍未做（理由见 §3.1 末尾）。事实表里"同一业务键对应多个 `data_hash`"的冗余**依然存在**（`fact_shopee_orders_monthly` 26627 行 / 2807 组 / 5261 冗余行等），需要配套的合并/清理决策与回滚方案。
- **事实表合并/清理**：未做。
- **新增索引**：见 §5「待确认」，`b_class.fact_*` 的 `(platform_code, shop_id, <业务键>)` 唯一索引建议**未建**（需先清理冗余行）。

---

## 3.3 验证缺口：采集同步模块的前端守卫一直是「哑测试」（2026-10-30 发现并修复）

### 3.3.1 问题

标准前端跑法是 `cd frontend` 后 `node --test "scripts/**/*.test.mjs" "tests/**/*.test.mjs"`。但 `frontend/scripts/` 目录内部**混用了两套 cwd 约定**：

| 约定 | 数量 | 解析结果 |
|------|------|---------|
| 按 `frontend/` 目录解析（`src/...`） | 13 个 | ✅ 正确 |
| 按**仓库根**解析（`frontend/src/...`） | **4 个** | ❌ 在 `cd frontend` 下解析成 `frontend/frontend/src/...` ⇒ `readFileSync` **ENOENT 崩溃** |

⇒ 那 4 个文件**在断言执行之前就崩了**，断言从未运行过。它们长期显示为"失败"，但既不是功能缺陷、也不是断言不通过，而是**读不到文件**。

**后果**：`dataSyncTasksHeaderChangeUi` / `dataSyncTemplateSaveApiNaming` / `frontPagePermissionAudit` 这 3 个**采集同步模块自己的守卫**，长期是哑的 ⇒ **第 1 批前端止漏与第 3 批契约显式化实际上没有有效守卫**，"失败集合零新增"这个结论对它们**不成立**。

### 3.3.2 修复

统一到目录内主流约定（`frontend/` 目录解析 `src/...`）：

| 文件 | 原约定 | 现约定 |
|------|-------|-------|
| `frontend/scripts/businessOverviewKpiGranularity.test.mjs` | `resolve(cwd,'frontend')` | `resolve(cwd)` |
| `frontend/scripts/dataSyncTasksHeaderChangeUi.test.mjs` | `resolve(cwd,'frontend/src/…')` | `resolve(cwd,'src/…')` |
| `frontend/scripts/dataSyncTemplateSaveApiNaming.test.mjs` | `resolve(projectRoot,'frontend/src/api/index.js')` | `resolve(projectRoot,'src/api/index.js')` |
| `frontend/scripts/frontPagePermissionAudit.test.mjs` | `path.resolve('frontend/src/router/index.js')` + `path.resolve('frontend/src/config/rolePermissions.js')` | 去掉 `frontend/` 前缀（**两处**） |

另修 `frontend/tests/hrShopCommissionConfigApi.test.mjs`：引用的是迁移前旧路径 `src/views/hr/ShopAssignment.vue`，实际已迁到 `src/domains/business/views/hr/ShopAssignment.vue`。

### 3.3.3 修复后的结果（**这条最重要**）

前端全量失败数 **16 → 11，零新增**，5 个假失败消除。这 4 个文件**恢复为真正执行断言后全部通过** ⇒ **被它们守卫的契约本来就成立**，第 1 批 / 第 3 批的前端改动**确实有守卫且确实通过**。

其中 `dataSyncCleanupUi.test.mjs` 的 4 个采集同步核心用例全部通过：

- `template update workbench uses backend hash options for Data Hash choices`（第 1 批 1.10 后端优先）
- `template update workbench auto-selects newly confirmed strong hash identities`（第 1 批 1.7）
- `template hash panel merges backend options with edited bindings`（第 1 批 1.4）
- `template save errors explain family hash semantic key changes`（第 3 批契约显式化）

⚠️ 修复后 `frontPagePermissionAudit` **新暴露 1 个真实用例失败**：`active routes do not declare roles without matching permissions`（路由声明了没有对应权限的 `roles`）。这是**权限契约问题**，属路由/权限模块，不在本次采集同步改造范围，已记录。

---

## 3.4 往后看的标准：`data_hash` 到底该怎么定

### 3.4.1 先把因果链摆正（已全部核实）

```
deduplication_fields 写法不一（订单号 vs order_id）
   └→ deduplication_service.py:144  只有「规范语义键」走语义解析，中文表头名走字面匹配
        └→ 拼 hash 的 JSON 时，键名用的就是字段写法本身
             └→ 同一笔业务在不同模板下算出不同 data_hash
                  └→ raw_data_importer.py:1093 的 ON CONFLICT
                     (platform_code, COALESCE(shop_id,''), data_domain, granularity, data_hash)
                     ⇒ 唯一约束撞不上 ⇒ 同一业务被插入多行
```

**关键认知：`data_hash` 不是"一个可选的指纹"，它是数据库唯一约束的输入。**
事实表上的唯一索引**早就建好了**（`uq_<表>_hash`），入库走的就是 `ON CONFLICT ... DO UPDATE / DO NOTHING`。
**重复行能存在，不是因为没兜底，而是因为"身份证号算得不一样，兜底就失效了"。**

### 3.4.2 标准（三层 + 三问）

`data_hash` 的素材 = **L1 范围层 + L2 身份层 + L3 时间层**：

| 层 | 内容 | 谁来管 | 业务含义 |
|---|------|--------|---------|
| **L1 范围层** | `platform_code / shop_id / data_domain / granularity / sub_domain` | **系统自动加**，模板不许碰（`deduplication_service.py:241`） | 保证不同店铺、不同粒度的数据不会撞车 |
| **L2 身份层** | 模板的 `deduplication_fields` | **模板只该放这一层** | "这条记录是哪一笔业务" |
| **L3 时间层** | 周期标识（`metric_date` / `period_start_date` / `period_end_date`） | **解析规则自动派生** | 防止不同周期的同一笔业务互相覆盖 |

**一个字段能不能进 L2，用三问判定**（这三条已分别由代码里三套机制实现）：

| 问法 | 判据 | 不合格就怎样 | 代码落点 |
|------|------|------------|---------|
| **问 1：是标识还是描述？** | 这一列的值变了，业务上还是"同一笔"吗？ | 还是 ⇒ 它是**描述**（金额/数量/状态/满意度），**剔除** | `semantic_field_registry` 的 `kind=metric` ⇒ `classify_semantic_key` → `ACTION_REMOVE` |
| **问 2：粒度够不够？** | 这一列 + 其它身份列能唯一确定一行吗？ | 不能 ⇒ **缺域级必需身份键** | `template_hash_policy` 的 `requirement_groups`（orders→`order_id`、products→`product_id`、services→`service_id`、inventory→`warehouse_name`） |
| **问 3：来源稳不稳？** | 这个值来自行内吗？同一文件里每行都一样吗？ | 一样 ⇒ 它是**文件级伴生日期**，只能当周期标识，**不能当身份键** | `parse_rule_provided_semantic_keys`（宽）vs `_file_companion_date_sources`（窄） |

**一句话标准**：**`data_hash` 回答"这一行是哪一笔业务"，不回答"这一行长什么样"。**
描述性字段（金额、数量、状态、评分）进 `data_hash` ⇒ 同一笔业务状态一变就换一个身份证 ⇒ 必然重复入库。

### 3.4.3 历史数据不管，是**可以**的（前提是口径先统一）

| | 结论 |
|---|---|
| 已入库的老行 | **不动**。老 hash 老行，不影响新逻辑 |
| 唯一约束 | **已在**（`uq_<表>_hash`），不需要新建；口径统一后它自然重新生效 |
| 幂等性 | 从今天起恢复：同一文件再导一次 ⇒ hash 相同 ⇒ 被 `ON CONFLICT` 合并/跳过 ⇒ **行数不增** |
| 代价 | 过渡期内同一业务可能新老各一行（老 hash / 新 hash）。但**不会再无限增长** |

⇒ **所以真正要做的不是清洗历史数据，而是把"算法口径"定死并让所有模板统一到它上面。**
⇒ 顺带解决了上一版"清理事实表冗余行"的优先级问题：它从"必须做"降级为"可选的收尾优化"。

### 3.4.4 完整优化方案（往前看）

| # | 动作 | 解决什么 | 谁做 | 优先级 |
|---|------|---------|------|-------|
| **P1** | **端到端幂等性验证**：同一源文件连续导入两次，断言第二次行数不增、`data_hash` 不变、唯一约束真的命中 | 目前只验到"闸门层"，**没验过"入库层"**。这是口径统一后的第一道验证 | 我 | **最高** ✅ **已完成** |
| **P2** | ~~109 个模板的 binding 语义映射人工确认~~ → **口径已纠正，见 §3.5** | 模板升级时的契约判定不准 ⇒ 误判/漏判"模板待确认" | 大部分已由「域限定列名识别 + 工作台自动归一」消解（42→103 个模板可保存）；services 店铺级豁免已按业务决定实施（§3.5.5） | 高 |
| **P3** | **模板口径体检工具常态化**：把 `scripts/normalize_template_deduplication_fields.py` 的诊断能力做成只读巡检，定期跑、报"新模板是否踩坑" | 防止新模板再把度量字段写进 `deduplication_fields` | 我 | 高 ✅ **已完成**（§3.7） |
| **P4** | **CI 护栏：禁止哑测试** | 本次发现 4 个守卫长期 ENOENT 崩溃、断言从未执行 ⇒ 结论不可信 | 我 | 高 ✅ **已完成**（§3.6） |
| **P5** | **数据健康度巡检**：定期看"同一业务键多行"的**增量**（不是存量） | 重复问题在长大前被发现 | 我 | 中 ✅ **已完成**（§3.8） |
| **P6** | **服务层月窗口下推**（clearance-ranking 44s → 约 11s） | 数据涨一倍就撞 60s 超时预算 | 我（需改仓库分层规则或加接口层） | 中 ⏸ **未做**（P7 已把查询压回 47.7s，但真正的热点在语义层的逐行别名解析，见 §3.9.7） |
| **P7** | **`api.clearance_ranking_module` 恒 0 行**：`sku_key` 口径统一 | 报表恒空（既有生产缺陷） | 业务定口径 + 我实施 | 中 ✅ **已完成**（§3.9） |
| **P8** | **后端测试基线治理**（179 failed） | 长期红灯 ⇒ 真回归被淹没 | 另立专项 | 低（本轮范围外） |

### 3.4.5 P1 验证结果（已完成，端到端证据）

交付物：`backend/tests/test_data_hash_idempotency_contract.py`（4 项，隔离库全绿）。
用**真实入库器** `RawDataImporter`（真实建表 + 真实 `ON CONFLICT`）跑，不是模拟。

| 用例 | 断言 | 结果 |
|------|------|------|
| `test_same_data_imported_twice_stays_single_row` | 同一份数据导两次 ⇒ 第二次 `inserted=0, updated=1`，**行数保持 1**，`data_hash` 不变 | ✅ |
| `test_different_source_headers_merge_into_one_row` | 源文件表头 `订单号` vs `订单编号`，模板都已归一为 `order_id` ⇒ **算出同一个 `data_hash`** ⇒ 落表**合并成 1 行** | ✅ |
| `test_unnormalized_template_would_split_the_same_business` | **反证**：模板未归一（`['订单号','产品ID']`）⇒ hash 不同 ⇒ 同一笔业务被写成 **2 行** | ✅ |
| `test_normalized_template_is_stable_under_health_check` | 归一后的模板是**稳定态**，体检脚本判定"无需改写" | ✅ |

**这条测试证明的完整链路**：

```
模板去重字段已归一（只用语义键）
   → calculate_data_hash 走语义解析（:144）
      → 两个不同表头写法的源文件算出同一个 data_hash
         → ON CONFLICT (platform_code, shop_id, data_domain, granularity, data_hash)（:1093）命中
            → 同一笔业务在事实表里只有一行，重复导入不再增行
```

**结论**：**§3.4.2 的标准是成立的，而且可执行、可验证。**
历史模板不归一会怎样，也被量化了：**同一笔业务两行**（第三个用例）。
⇒ **"把模板口径统一"就是"让数据库唯一约束重新生效"**，这是往前看的真正抓手。

---

## 3.5 验收标准：「源文件变动 → 工作台更新模板 → 正常同步」（2026-10-30 第 9 轮）

### 3.5.1 验收标准与结论

> **业务验收标准**：今天优化完成后，**后续源文件有变动，我们去工作台更新模板，就能正常同步**。

| 问题 | 结论 |
|---|---|
| 114 个模板里，多少个能在工作台正常更新并保存？ | **103 个**（改前只有 42 个）；剩下 11 个改对表头行后也能存（已用真实文件逐个验证） |
| 「109 个模板人工确认」要花多少人力？ | **不是 109 次人工**。绝大多数模板在工作台里点一次「保存」就完成归一（前端会自动剔除度量字段、自动补域必需身份键） |
| 「源文件有变动」后要做什么？ | 进工作台 → 选新文件 → **改表头行（若表头变了）** → 必要时重新映射改名列 → 点「使用伴生日期/周期」（若文件里没有日期列）→ 保存 → 同步 |

### 3.5.2 真正的拦路虎不是「人工确认」，是「系统认不出真实列名」

第 9 轮用**真实前端模块**（`frontend/src/domains/data_platform/utils/deduplicationSelection.js`）
+ **真实后端判定**（`TemplateSaveReadinessService.assess`）复现了完整的工作台流程，
量出来的结果和第 1~4 批的假设很不一样：

| 口径 | 能保存 | 不能保存 |
|---|---|---|
| 改前 | 42 | **72** |
| 改后（§3.5.3） | **103** | **11** |

72 个卡住的模板，根因不是「字段要人确认」，而是：

```
源文件表头是平台自己的叫法（商品编号 / ID / 规格编号 / *商品SKU / 客服ID）
   └→ 全局语义别名表里没有这些列名
      └→ 列名推断不出来 ⇒ 绑定停在 pending
         └→ 工作台把「未确认绑定的列」当成废字段自动剔除（这是对的：度量字段该剔）
            └→ **可它把身份列也一起剔了**（商品编号=product_id、ID=product_id…）
               └→ 必需身份键（products_identity / orders_identity）满足不了
                  └→ 保存被闸门拦下 ⇒ 返回 400「去重字段无法解析到已确认的语义映射」
```

**⇒ 「人工确认」这个说法把问题指错了方向。** 真正要修的是「系统要认得出平台真实列名」。

### 3.5.3 做了什么（§3.5.2 的对症修复）

**F1｜域限定的列名识别**（前后端同源）

| 位置 | 改动 |
|---|---|
| `backend/services/semantic_field_registry.py` | 新增 `DOMAIN_COLUMN_SEMANTIC_OVERRIDES`（数据域 → 列名 → 语义键）与 `infer_semantic_key_for_domain()` |
| `backend/domains/data_platform/routers/field_mapping_templates.py` | `_normalize_header_bindings(..., data_domain=None)` 按域推断；7 个调用点分别传「文件域 / 模板域 / 请求域」 |
| `frontend/src/domains/data_platform/utils/headerBindings.js` | 同源映射表 + `inferHeaderBindings({ dataDomain })` |

映射表内容（**全部来自真实源文件的表头**，不是猜的）：

| 数据域 | 列名 | 语义键 |
|---|---|---|
| products | `商品编号` / `商品 ID` / `ID` | `product_id` |
| products | `规格编号` | `sku_id` |
| services | `客服ID` / `客服编号` | `service_id` |
| inventory | `*商品SKU` | `platform_sku` |
| inventory | `*商品名称` | `product_name` |

**为什么必须按域限定、不能进全局别名表**：
`ID` 在 products 域是商品 ID，在别的域未必是身份列；`客服ID` 在 services 域是服务人员 ID。
放进全局表 = 跨域污染，别的域的同名列被误提升成语义身份。

**为什么不会重新制造第 3 批修掉的「假一致」**：
域限定推断出来的绑定一律标记 `semantic_review_source=inferred`；
家族 hash 口径比较（`_binding_lookup_by_source`）**只认 `user`** ⇒ 推断即确认的老毛病不会复发。

**F2｜工作台自动补域必需身份键**（前端）

`products → product_id`、`orders → order_id`、`services → service_id`
（对应后端闸门 `requirement_groups` 的必需身份键）。
以前只有 products 域会补，orders 域的模板因为「去重字段里没勾订单号」而被拦下，
现在只要文件里有订单号列就会自动带上。

**F3｜度量字段仍由前端自动剔除、后端兜底**

工作台保存时会把「绑定未确认 / 非语义 / 不可参与 hash」的列从去重字段里剔掉并给出原因
（`订单状态` / `状态` / `规格名称` / `全球商品货号` 等共 13~21 个模板受益），
后端闸门同时独立拦截（双保险）。

### 3.5.4 端到端契约测试（永久）

`backend/tests/test_workbench_template_update_flow.py`（**18 项，全绿**）覆盖：

1. 真实平台表头被认成身份键；`ID` 不跨域污染；度量类列名永不被认成身份键；
2. products 模板更新后能过闸门，且去重字段被归一成语义键；
3. orders 模板缺 `order_id` 时**必须**被拦下，补上后放行；
4. services 店铺级子域（`ai_assistant` / `agent`）豁免 `service_id`；
   有客服维度的服务报表**照旧**要求 `service_id`；
5. 客服维度报表的 `日期期间` 认成 `metric_date`（周期必须进 hash，否则下一期覆盖上一期）；
6. **hash 口径统一**：源文件把 `商品编号` 改名成 `商品编号(新)`、用户在工作台重新映射后，
   同一笔业务 `data_hash` **不变**（对照用例：模板仍存中文表头名 ⇒ hash 不同 ⇒ 同一业务两行）；
7. 域限定推断出的绑定**不是**用户确认 ⇒ 家族比较不会假一致；
8. 各域必需身份键口径稳定。

### 3.5.5 services 店铺级模板：`service_id` 豁免（**业务已拍板，已实施**）

`services` 域的闸门要求 `service_id`，但有 9 个模板是**店铺级**报表
（Shopee AI 助手 / 客服汇总），源文件里根本没有客服维度列：

| 模板 | 表头（节选） |
|---|---|
| 264/265/266/323（ai_assistant） | `日期` / `服务的访客` / `已回答的问题` / `好评比例` … |
| 226/267/268/269/322（agent） | `日期期间` / `访客数` / `聊天询问` / `访客询问` … |

**业务决定（2026-10-30）**：豁免 `ai_assistant` / `agent` 两个子域的 `service_id` 要求，
行身份退化为「**店铺 + 周期**」。

**实现**（`backend/services/template_hash_policy.py`）：

* 这两个子域的 `services_identity` 变成**天然满足**的组（仍然显示在 `requirement_groups` 里，
  但不阻塞保存、不进 `errors`）；
* 店铺来自 `shop_id`——它是**系统范围字段**，入库时自动进 hash；
* 周期来自 `services_date` 组（`metric_date` / 周期起止）；
* ⚠️ **只豁免这两个子域**：有客服维度列的服务报表（`sub_domain` 为空或别的值）照旧要求 `service_id`。

**顺带修掉一个真实的数据覆盖问题**：客服维度报表（`agent`）**一个文件只有一个周期行**，
且**文件名带的是采集时间、不是周期**（`shopee_services_agent_monthly_20260622_122159.xlsx`
里的 `20260622` 是采集日），周期只写在 `日期期间` 单元格里（`01-06-2026 - 21-06-2026`）。

⇒ 周期**必须**进 hash。否则下一期报表算出**同一个** hash，
把上一期的行**覆盖掉**（事实表里只剩最后一个周期）。
⇒ 所以 `日期期间` 被域限定映射为 `metric_date`（services 域内）。

### 3.5.6 剩下的 11 个模板：表头行设错

| 根因 | 模板数 | 清单 | 处置 |
|---|---|---|---|
| 源文件是多行表头的宽表，模板把表头行记错了 | 11 | analytics 10 个（326/327/329/332/333/351/352/353/358/365）+ products 361 | 工作台改表头行 → 去重字段选 `metric_date` |

**已用真实文件逐个验证**：

* analytics（tiktok）：表头行记的是 **7**，正确是 **8**
  （第 7 行是合并标题 `每日数据`，第 8 行才是 `日期 / GMV / 订单数 / 客户数`）。
  改成 8 之后 `日期` 自动认成 `metric_date` ⇒ `can_save=True`（实测）。
* products 361（tiktok）：表头行 **3** 才对（`商品名 / 商品 ID / GMV 区间 / 发品状态`），
  再加一次「使用伴生日期」⇒ `can_save=True`（实测）。

⇒ 这 11 个不需要改代码，工作台里改一次表头行即可。

### 3.5.7 这一轮的诚实结论

- ✅ 「源文件变动 → 工作台更新模板 → 正常同步」这条链路**在代码层面已经打通**，
  并有永久契约测试守住；
- ✅ 存量模板**不需要批量刷数据**——工作台保存时前端会自动完成归一（剔除度量字段、补必需身份键），
  后端再兜一道闸门；
- ✅ services 店铺级模板的 `service_id` 已按业务决定豁免（§3.5.5）；
- ⚠️ 仍有 11 个模板要先在**工作台里把表头行改对**（一次性动作，已逐个验证可行）；
- ⚠️ **模板口径改一次 = 该模板的 `data_hash` 口径变一次**（历史行不动，新老 hash 过渡期混存，
  与 §3.4.3 的结论一致：唯一索引 `uq_<表>_hash` 早就建好，口径统一后新数据从此幂等）。

---

## 3.6 P4｜CI 护栏：禁止哑测试（2026-10-30 第 9 轮）

### 3.6.1 问题

§3.3 发现 4 个守卫测试因为路径错误在 `readFileSync` 处 ENOENT 崩溃、**断言从未执行**，
却长期伪装成普通失败。追根溯源：**CI 里根本没有前端测试步骤**
（`ci.yml` 的 `test` job 只跑 pytest），所以没人发现。

⇒ 「测试在跑、CI 是红的、于是没人怀疑结论」——这比没有测试更危险。

### 3.6.2 实施

| 位置 | 作用 |
|---|---|
| `scripts/ci_frontend_test_silence_gate.py` | 门禁本体：① **静态**检查测试文件里字面量路径（`readFileSync` / `existsSync` / 动态 `import()`）按 `frontend/` 解析是否存在；② **运行时**跑一次 `node --test`，把 `ENOENT` / `ERR_MODULE_NOT_FOUND` / `Cannot find module` 等「压根没跑起来」的失败**单独**挑出来报警 |
| `tests/unit/test_frontend_test_silence_gate.py` | 门禁的**自测**（5 项）：用真实坏样本证明它会亮红灯，避免门禁自己退化成永远绿的摆设 |
| `.github/workflows/ci.yml` | 新增 `frontend-guard` job（Node 24 + `npm ci` + 跑门禁），并接入 `notify` 汇总 |

**设计要点**：

* **普通断言失败不归本门禁管**（仓库当前有 9 条已知失败基线），
  门禁只对「哑测试」亮红灯 ⇒ 不会把已知红灯和真问题混在一起；
* 静态检查先跑（秒级），在浪费一次测试运行之前就把路径问题抓出来；
* 门禁退出码：`0` 通过 / `1` 发现哑测试 / `2` 门禁自身出错。

**验证**：

| 场景 | 结果 |
|---|---|
| 对**真实前端**跑完整门禁 | 静态 0、运行时 0、普通断言失败 9（只汇报不拦截）⇒ **exit 0** |
| 对**构造的坏样本**跑（路径写错的测试） | 静态 1 条 + 运行时 2 条 ⇒ **exit 1**，并打印具体文件与行号 |
| 门禁自测 | **5 项全绿** |

### 3.6.3 门禁上线后自己红了：又一个「哑测试」（2026-10-31 第 11 轮）

P4 门禁上线后，`main` 的 `CI Pipeline` **连续 8 次红**，原因不是新代码坏了，
而是**门禁自己抓到了第 5 个哑测试**：

```
frontend/scripts/manualChunksCycle.test.mjs:18
  Error: ENOENT: no such file or directory,
  scandir '.../frontend/dist/assets/js'
```

这条测试检查的是**前端构建产物**（Vite 打包出来的 chunk 有没有循环引用）。
`frontend/dist/` 是 gitignore 且未跟踪 ⇒ CI 的全新检出里**根本不存在**；
而 `frontend-guard` job 只做 `npm ci`，**不跑 `vite build`** ⇒ 目录永远不存在。

⇒ 测试在 `readdirSync(jsDir)` 处直接崩掉，**断言一次都没执行**，
和它要抓的那 4 个哑测试是同一种病。

**修法：显式跳过，而不是崩掉。**

```js
const skipReason = existsSync(jsDir)
  ? false
  : 'dist/assets/js 不存在：需要先构建前端产物（例如 npm run build）才有可检查的对象'

test('build output does not create a circular import between ...', { skip: skipReason }, () => { ... })
```

要点：

* **没有构建产物 ⇒ 没有可检查的对象 ⇒ 显式 skip 并写清原因**，
  而不是让测试「崩掉」伪装成一条普通失败（这正是门禁要禁止的形态）；
* 门禁本身**不削弱**：运行时检查照旧扫 ENOENT 等信号 ——
  只是这条测试不再制造假信号；
* 本地/任何先构建过前端的上下文里，这条测试**仍然是真检查**（`skip: false`）；
* 没有去改门禁去「忽略 dist 下的 ENOENT」—— 那等于给门禁开一个可以藏真 bug 的口子。

**修完的实测**：

| 场景 | 修之前 | 修之后 |
| --- | --- | --- |
| 本地（有 `dist/`） | 真跑断言，通过 | **真跑断言，通过**（不变） |
| 模拟 CI（无 `dist/`） | ENOENT 崩溃 → 门禁 exit 1 | **`skipped 2`（带原因），无 ENOENT → 门禁 exit 0** |
| 全量前端测试失败基线 | 9 条 | **9 条**（名单逐条一致） |
| 门禁本地跑 | — | 静态 0 / 运行时 **0** / 普通断言失败 **9** ⇒ **exit 0** |

**教训（写给以后）**：门禁上线时，它会立刻把「以前没人看的红灯」全部暴露出来。
这是好事，但必须**当场把暴露出来的红灯处理掉** ——
否则就是「永远红的 CI」，而永远红的 CI 和永远绿的 CI 同样有害：
真回归会被淹没在里面。

---

## 3.7 P3｜模板口径体检巡检（2026-10-31 第 10 轮）

### 3.7.1 为什么需要它

第 1~4 批把模板保存口径和 hash 闸门收紧了，但**闸门只在保存那一刻拦**。
已经存在的模板、以及新建模板时误选的字段，如果没有定期巡检，
就会一直烂在库里，直到某次同步把重复数据写进去才被发现。

### 3.7.2 判定口径（**最容易做错的地方**）

"过不了保存闸门"必须按**工作台提交口径**判断，**不能**拿库里的存量字段直接评估：

| 工作台在提交前做了什么 | 对应实现 |
|---|---|
| 剔除**未确认**的表头列（用户没点过确认 ⇒ 不进 hash） | `build_workbench_effective_deduplication_fields` |
| 剔除**解析规则派生**的字段（如文件伴生日期派生的 `metric_date`） | 同上 |
| 剔除**不可参与 hash** 的度量字段 | 同上 |
| 自动**补齐**该数据域必需的身份键（前提是文件里认得出这一列） | `TemplateHashPolicyService.required_identity_keys` |

后端等价实现落在
`backend/services/template_save_readiness_service.py::build_workbench_effective_deduplication_fields`，
与前端两处逻辑一一对应：

* `frontend/src/domains/data_platform/utils/deduplicationSelection.js` → `normalizeDeduplicationSelection`
* `frontend/src/components/dataSync/TemplateUpdateWorkbenchDrawer.vue` → `mergeRecommendedIdentityFields`

**域必需身份键的后端唯一口径** = `TemplateHashPolicyService.required_identity_keys`
（products → `product_id`；orders → `order_id`；services → `service_id`，
店铺级子域 `ai_assistant`/`agent` 豁免，见 §3.5.5）。
前端 `DOMAIN_REQUIRED_IDENTITY_KEYS` 必须与它**逐字一致** ——
不一致就会出现"工作台补了字段，闸门却不认"的荒唐状态。
这份一致性由 `tests/unit/test_template_hash_hygiene_audit.py` 的**契约测试**守住。

### 3.7.3 产出

| 位置 | 作用 |
|---|---|
| `scripts/audit_template_hash_hygiene.py` | 只读体检脚本：按上面的口径评估每个模板，输出问题分类 + 明细；支持 `--json` / `--baseline` / `--strict` / `--fail-on-new` / `--status` / `--only-issues` |
| `backend/services/template_hash_policy.py::required_identity_keys` | 域必需身份键的后端唯一口径来源 |
| `backend/services/template_save_readiness_service.py::build_workbench_effective_deduplication_fields` | 工作台提交口径的后端等价实现 |
| `tests/unit/test_template_hash_hygiene_audit.py` | **12 项自测**（含前后端契约校验、报告统计、基线对比） |
| `.github/workflows/data-hash-audit.yml` | 定期入口：每周一 03:30 UTC + 手动触发；需要 `DATABASE_URL` secret（生产库只读），未配置时整体跳过而不是报错 |

**失败策略**：只对**相对上一次巡检新增**的问题亮红灯（`--fail-on-new`）。
存量欠账不该让巡检永远红 —— "永远红的 CI"和"永远绿的 CI"同样有害。

### 3.7.4 问题分类

| 分类 | 含义 | 级别 |
|---|---|---|
| `non_canonical_identity` | 去重字段还是表头名（`商品编号`），不是语义键 | 告警 |
| `metric_in_identity` | 度量字段混进了去重字段（行身份会随状态漂移） | 告警 |
| `missing_identity_key` | 缺该域必需的身份键（hash 口径不全） | 告警 |
| `needs_renormalize` | 已有安全改写方案（跑归一脚本即可解） | 告警 |
| `needs_manual_mapping` | 走工作台口径后仍过不了保存闸门 | **阻塞** |
| `no_dedup_fields` | 没配去重字段（同步时回落到域默认口径） | 告警 |

### 3.7.5 实测（真实库 253 个模板）

| 分组 | 模板数 | 有问题 | 阻塞 |
|---|---|---|---|
| **published（在线模板）** | 27 | 12 | 4 |
| archived（历史模板） | 226 | 206 | 156 |

在线模板的 4 个阻塞项全部是 `products/weekly` 缺 `products_period_date` 要求组
（与 §3.5.6「11 个模板是表头行设错」同源）。

**这条巡检挖出来的一个关键事实**：去重字段写成中文表头名（`商品编号`）时，
`calculate_data_hash` 里的 hash key 就是**中文表头名**；写成 `product_id` 时 key 是 `product_id`
⇒ **同一笔业务在两个模板下算出两个不同的 hash** ⇒ 唯一索引
`(platform_code, shop_id, data_domain, granularity, data_hash)` 拦不住跨模板重复。
这就是"口径不统一"的真实危害，也是 §3.2.2 只改写 5 个模板的依据。

---

## 3.8 P5｜数据健康度巡检（2026-10-31 第 10 轮）

### 3.8.1 为什么需要它

`data_hash` 唯一索引只能保证"**同一个 hash** 不重复"，
保证不了"**同一笔业务** 只有一行"。

把 `订单状态` 这类**度量字段**写进 `deduplication_fields` 时，
业务状态一变 → hash 变 → 库里多出一行"同一笔订单"。
这种重复**不会触发任何报错**，只会悄悄把数据越攒越多、报表越算越歪。

### 3.8.2 产出

`scripts/audit_data_hash_health.py`（只读）：按**业务键**统计"同一笔业务出现了几行"。

| 数据域 | 业务键 |
|---|---|
| orders | 平台 + 店铺 + 统计日期 + 订单号 |
| products | 平台 + 店铺 + 统计日期 + 商品 ID |
| services | 平台 + 店铺 + 子域 + 统计日期 + 服务日期 |

支持 `--json` / `--baseline`（输出**增量**）/ `--strict` / `--fail-on-new`。

### 3.8.3 实测（真实库）

| 数据域 | 总行数 | 重复业务键 | 多出来的行 |
|---|---|---|---|
| orders | 33,265 | **4,409 组** | 4,955 |
| products | 26,634 | 6 组 | 6 |
| services | 368 | 1 组 | 1 |
| **合计** | 60,267 | **4,416 组** | **4,962 行（约 8.2%）** |

这是**存量**欠账（历史模板把度量字段写进了去重字段）。
脚本的价值在于**看增量**：口径统一后新数据不再增长，存量随着模板修复逐步收敛。

---

## 3.9 P7｜`api.clearance_ranking_module` 恒 0 行：根因与修复（2026-10-31 第 10 轮）

### 3.9.1 现象

`api.clearance_ranking_module` 一直返回 **0 行** ⇒ 滞销榜页面恒空。

### 3.9.2 根因 ①：两侧 `sku_key` 定义**不对称**

| 侧 | 原 `sku_key` 定义 |
|---|---|
| 订单侧（`semantic.fact_orders_atomic`） | `sku_id → platform_sku → product_sku → product_id`（**`sku_id` 优先**） |
| 积压侧（`mart.inventory_backlog_base`） | `platform_sku → product_sku → product_id`（**没有 `sku_id`**） |

订单侧 `sku_id` 100% 有值（数字，如 `128245418676`），积压侧 100% 是文字
（如 `HKR-SNH-White12-035`）⇒ **同一个 SKU 在两侧算出两个不同的 key** ⇒ 永远 join 不上。

### 3.9.3 根因 ②：把「数据来源平台」当「销售渠道」做 join

积压行的 `platform_code` 恒为 `miaoshou`（**数据来源是妙手 ERP**），
订单行的 `platform_code` 是 `shopee` / `tiktok`（**销售渠道**）。
原视图的 `b.platform_code = m.platform_code` 拿「来源」比「渠道」⇒ **恒不相等** ⇒ 恒 0 行。

库存是**店铺的库存**，妙手只是管库存的系统；渠道属于订单侧。

### 3.9.4 修复（`sql/api_modules/clearance_ranking_module.sql`）

1. **两侧 `sku_key` 统一成同一个表达式**：`platform_sku → product_sku → product_id`。
   为什么订单侧也去掉 `sku_id`：积压视图根本不提供 `sku_id` 列（它来自妙手 ERP 快照），
   key 必须用**两侧都表达得出**的列来算，否则又变成不对称。
   `sku_id` 只在 `platform_sku` / `product_sku` 都缺时才轮到，
   而积压侧 `platform_sku` 100% 有值 ⇒ 这一档永远配不上，去掉它不改变任何结果。
2. **join 只按 SKU 走**，并保留一条兜底规则：
   * 积压行来自某个**销售渠道**（`platform_code` 出现在订单平台集合里）⇒ 只与该渠道的订单配对；
   * 积压行来自 **ERP**（平台不在订单平台集合里）⇒ 与所有渠道的订单按 SKU 配对。

### 3.9.5 结果

| 口径 | 结果 |
|---|---|
| 修复前 | **0 行** |
| 修复后 | **143 行**（10 个自然月 × shopee/tiktok × 各店铺） |

命中量实测：订单侧 1,080 个 SKU 键、积压侧 503 个，
按 SKU 关联命中 **537 对**（其中 **418 个积压 SKU** 真正进入榜单），
按平台关联命中 **0 对**（= 根因 ② 的直接证据）。

### 3.9.6 同根因的兄弟缺陷（**本次未改，记为遗留**）

`api.sku_clearance_ranking_module` 的 `sold_units_30d` **恒为 0**：
它的 `sales_30d` 用 `platform_code = ANY (SELECT DISTINCT platform_code FROM mart.inventory_state)`
把订单平台限制成库存平台（= `miaoshou`），而订单里没有 `miaoshou` ⇒ 该 CTE 恒空。
修法与本节一致（按 SKU 关联 + 平台规则）。
**本次不动它**：它会改变 SKU 级滞销清单的动销量与 DOS 定价输入，属于另一个业务口径，需业务确认后单独发版。

### 3.9.7 性能（**P6 仍未做，但已不再撞预算**）

视图一旦真的把订单和积压连起来，耗时立刻从"空跑"变成"真算"，必须重新测。
用 `EXPLAIN (ANALYZE, BUFFERS)` 逐节点定位后，做了两处**等价**优化：

| 优化 | 说明 | 省下 |
|---|---|---|
| ① 平台兜底规则**预计算成布尔列** | 原来写在 LATERAL 里逐行判断（`NOT EXISTS (SELECT 1 FROM order_platforms ...)`），改成在 `backlog_rows` 里算好 `from_sales_channel` | **25s**（49.9s → 74s 那次回退的元凶） |
| ② `order_platforms` **从 `order_months` 派生** | 原来为了拿"订单侧平台集合"又扫了一遍 `semantic.fact_orders_atomic`（原子视图每行都要跑一次店铺别名解析 ⇒ 一遍 24.4s）；`order_months` 本来就物化了，从它派生是零成本 | **24.4s** |

| 定义 | 行数 | 耗时 |
|---|---|---|
| 旧定义（恒 0 行，等于没干活） | 0 | 43.8s |
| 新定义 v1（兜底写在 LATERAL + 单独扫原子视图） | 143 | 69~76s ⚠️ 超 60s 预算 |
| **新定义 v2（两处优化后）** | **143** | **47.7s** ✅ 在 60s 的 DB 预算内 |

（dashboard 家族的 DB 预算是 60s，前端 axios 是 70s，见 `backend/utils/config.py`。）

**剩下的 22s 在语义层，不在本视图**：
`semantic.fact_orders_atomic` 为了解析店铺身份，对**每一行**都跑一次
`Limit 1 + Sort` 的关联子查询（扫 `shop_account_aliases` + `shop_accounts`），
33265 行 ⇒ 33265 次 ⇒ 约 22s。
这才是 P6 该动的目标（把关联子查询换成一次性的别名映射 JOIN），
但它属于**语义层**改动、影响所有下游视图，需另立专项评估影响面。

**顺带排除的两个"看起来更快"但其实更慢的写法**（都实测过）：

* 把 `MATERIALIZED` 改成 `NOT MATERIALIZED`：69.2s → 80.4s（月份窗口）/ 100.7s（全量），
  因为 `order_months` 被引用两次，内联后要算两遍，而且外层月份窗口**推不下去**
  （`ranking_month` 是 `date_trunc('month', metric_date)` 的计算列，推不到 `metric_date`）。
* 把 LATERAL 里的 `NOT EXISTS` 换成预聚合的 `max_snapshot_date`：
  结果**完全一致**（全量与月份窗口都逐行比对过），但耗时不变（68.6s vs 69.2s）⇒ 不是瓶颈，没采用。


### 3.9.8 视图改动的落地方式（**发版时必看**）

非生产环境 `AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP` 默认 **true**：
后端重启时会自动把 `sql/` 资产重新灌进库 ⇒ 本地改完视图定义、重启后端即生效。

**生产环境该开关为 false**（`should_auto_bootstrap_dashboard_on_startup("production")` 返回 False），
而且**数据刷新流程与 dashboard bootstrap 都会跳过「已存在的普通视图」**
（`refresh_runner.execute_sql_target` 的 `recreate_views=False`）——
所以生产上改完 `sql/` 资产，**光部署不会生效**，必须显式重建。

> **第 11 轮起，这一步已经接进部署流程，不需要人工去服务器上跑。**

`scripts/deploy_remote_production.sh` 新增 **Phase 2.7**：

```
Phase 2     数据库迁移（智能迁移）
Phase 2.1   schema 完整性门禁
Phase 2.5   生产 bootstrap
Phase 2.6   dashboard 资产 bootstrap（只补「缺失」的视图）
Phase 2.7 ★ 重建视图定义（CREATE OR REPLACE VIEW）
Phase 2.7b ★ 确认重建后的视图确实存在
Phase 3     启动应用层（backend-api / celery / frontend / nginx）
```

执行的命令：

```bash
python3 /app/scripts/rebuild_views.py --target api.clearance_ranking_module
```

**为什么要再加 2.7b**：`rebuild_views.py` 在「目标视图不在库里」时会**跳过并返回 0** ——
那是**静默成功**。只跑重建步骤的话，会出现「部署日志显示成功、视图其实根本没重建」。
2.7b 用 `to_regclass()` 逐个确认目标视图存在，缺失就中止部署并回滚。

（这里**不校验行数**：新环境/空库时视图合法地返回 0 行，行数校验会误报。
行数由发布后的「After Deployment」人工确认，见 `docs/guides/RELEASE_CHECKLIST.md`。）

放在这个位置是有讲究的：

- **在 schema 门禁之后** —— 迁移没过就不会走到这里；
- **在应用层启动之前** —— 新 backend 一起来看到的就是新定义，不会先上线一轮旧口径；
- **旧 backend 容器此时已被 stage 停掉** → `CREATE OR REPLACE VIEW` 的 ACCESS EXCLUSIVE
  排他锁**不会挡住线上查询**（重建期间看板会短暂转圈）；
- **重建失败 ⇒ 部署中止 ⇒ 回滚路径恢复旧容器** ⇒ 绝不会「带着旧定义上线」。

目标清单可用环境变量覆盖（空格分隔）：

```bash
export DEPLOY_REBUILD_VIEW_TARGETS="api.clearance_ranking_module api.sku_clearance_ranking_module"
```

配套改动：

| 文件 | 改动 |
| --- | --- |
| `Dockerfile.backend` | 把 `scripts/rebuild_views.py` COPY 进后端镜像（容器内执行） |
| `scripts/deploy_remote_production.sh` | 新增 Phase 2.7 + 2.7b |
| `scripts/verify_remote_deploy_contracts.py` | 加契约门禁：脚本里必须有重建步骤 + 镜像里必须有重建脚本 |
| `tests/test_verify_remote_deploy_contracts.py` | 6 项自测，锁住「重建早于应用层启动」+「内联 Python 可编译且 import 齐全」 |

**仍然需要人工确认的两种情况**：

1. 视图的**列**变了（增删列、改名）⇒ 纯 `CREATE OR REPLACE VIEW` 会直接报错。
   当前 `sql/api_modules/clearance_ranking_module.sql` 用的是
   `DROP VIEW IF EXISTS` + `CREATE OR REPLACE VIEW` 两段式，列变了也能重建 ⇒ 不受影响；
   别的视图若只写 `CREATE OR REPLACE VIEW`，列变更会失败 —— 部署会中止并回滚，
   属于**响亮的失败**（不是静默错误），按提示改成 DROP + CREATE 即可。
2. 视图**依赖链**变了（新增了上游视图）⇒ 需要把新上游也加进
   `DEPLOY_REBUILD_VIEW_TARGETS`；`rebuild_views.py` 会按拓扑序串行重建，不会自锁。

手动重建的入口仍然保留（本地调试 / 应急）：

```bash
python scripts/rebuild_views.py --target api.clearance_ranking_module
```

### 3.9.9 v7.12.1 上线后的生产实测：**视图口径已修好，但生产仍返回 0 行**（数据侧缺口）

v7.12.1（`5a254d65`）发版后，Phase 2.7 / 2.7b 在生产服务器上跑通：

```
[OK] rebuilt view definitions present: api.clearance_ranking_module
[OK] Backend is healthy / Frontend responded / Nginx /health passed
[OK] Deployment completed. Tags: Backend=v7.12.1, Frontend=v7.12.1
```

**线上第一层结论：视图定义确实换成了新版。**

| 观测点 | 发版前 | 发版后 |
| --- | --- | --- |
| `GET /health` 的 `checks.dashboard.status` | `degraded` | **`ready`** |
| `GET /api/dashboard/assets/status` 的 `assets_drift` | `true` | **`false`** |
| 同上，`clearance_ranking` 模块状态 | `drift` | **`ready`** |
| `GET /api/dashboard/clearance-ranking` 耗时 | — | **38~43s**（在跑新定义的复杂 join，不是秒回空） |

**线上第二层结论：0 行不是口径问题，是生产缺少「距上次进货时长」这份数据。**

生产 `GET /api/dashboard/business-overview/inventory-backlog` 返回：

```json
{"total_value":169752.01,"total_quantity":8412,
 "deep_stagnant_row_count":0,"mid_stagnant_row_count":0,"active_row_count":0,
 "unknown_restock_row_count":309,"top_products":[]}
```

`unknown_restock_row_count` 的定义是 `COUNT(*) FILTER (WHERE days_since_restock IS NULL)`
（`sql/api_modules/inventory_backlog_summary_module.sql`）——
统计的是**同一张** `mart.inventory_backlog_base`，
而滞销榜视图的入选条件正是 `h.age_days >= 30`，
其中 `age_days = COALESCE(b.days_since_restock, 0)`（`sql/api_modules/clearance_ranking_module.sql`）。

⇒ 生产的 309 行积压**全部** `days_since_restock IS NULL` ⇒ `age_days = 0` ⇒ `>= 30` 一条都过不了 ⇒ 视图 0 行。

本地对照（同一套 SQL）：

| 指标 | 本地 | 生产 |
| --- | --- | --- |
| `mart.inventory_backlog_base` 行数 | 506 | 309 |
| `days_since_restock IS NULL` | **0** | **309（全部）** |
| `days_since_restock >= 30` | 409 | 0 |
| `mart.inventory_state`（状态层）行数 | 1230 | 未填充 |

**结论**：P7 的两处口径缺陷（sku_key 不对称、跨域平台 join）在生产已经修掉并生效；
剩下的 0 行是**生产缺少库存状态层数据**——
`mart.inventory_state` 没跑出 `stock_added_at`（距上次进货时长的来源），
和 §3.9.6 记的「miaoshou 订单采集链路未跑」是同一类问题：**采集/状态层在生产没出数**，
不是视图口径写错了。

**⇒ 后续动作（在数据/运维侧，不在视图 SQL 里）**：

1. 在生产服务器上跑通库存快照采集 → 状态层（`mart.inventory_state`）→ `mart.inventory_backlog_base`
   的 `days_since_restock` 链路；
2. 链路出数后，`api.clearance_ranking_module` 会**自动**出数（视图是实时的，不需要再重建）；
3. **不要**为了「让它有数」去改 `age_days >= 30` 这个口径 —— 那会把没有库龄的行也算成滞销，
   属于制造假数据。正确做法是把库龄数据补上。

**⇒ 顺带暴露的一个口径脆弱点（值得记一笔）**：

`COALESCE(b.days_since_restock, 0)` 把「取不到库龄」和「库龄是 0 天」**混成同一个值**，
于是「数据缺失」被伪装成「都是新货」。同一个 NULL 也让 `inventory_backlog_summary` 的
`active_sku_count`（`days_since_restock < 30`）把缺数据的行算成活跃 SKU。
建议后续把「取不到」单独成一档（例如 `-1` 或独立的 `restock_tier = 'unknown'`），
让「没有库龄」在数据上可见，而不是静默变成 0。

---

## 4. 建议的实施顺序

1. **第 1 批**（前端止漏）—— 独立提交，可立即解除当前阻塞。
2. **第 2 批**（后端口径归一）—— 与第 1 批解耦，可在同一分支后续合。
3. **第 4 批**（环境）—— 独立、低风险，同时提升可观测性。
4. **第 3 批**（数据与状态机）—— **另立专项**，需先出影响面报告与回滚方案，再申请数据修复授权。

每批的验证口径：
- 前端：`vue-tsc` 类型检查 + `node --test` **失败名字集合**对比（cwd 约定分裂，不能只看数量）。
- 后端：聚焦回归 + 全量 `pytest` 与基线做**失败集合** diff（零新增失败）。
- 数据相关：先在一次性 PG 容器 + 一次性后端验证，**绝不写真实业务库**（conftest 护栏常开）。

---

## 5. 明确不做 / 待确认

- **不改 orders 域要求 order_id 的策略**。依据：模板 345 的 `header_columns` **确实含「订单号」列**（91 列，前 6 列为 `订单号/订单状态/售后状态/产品ID/平台SKU/SKU ID`），源文件表头为 `订单编号` 且 **100% 有值**（file 2829 / 3007 实测）；且 weekly 事实表**同一产品ID 最多 132 行**（不同订单）⇒ 必须靠订单号区分行，否则会互相覆盖。
- **历史数据修复（`deduplication_fields`）已执行**，范围严格限定为"改写后复验两道闸门通过"的 5 个模板（§3.2.2）；`data_hash` 重算与事实表合并/清理**仍未授权、未执行**。
- **但 `data_hash` 重算与事实表冗余行清理现在降级为「可选收尾」**（依据见 §3.4）：事实表的唯一索引 `uq_<表>_hash` **早就建好**，重复行之所以存在不是"没兜底"，而是"去重字段写法不统一导致身份证号算得不一样"。**把模板口径统一后，唯一约束自然重新生效**（§3.4.5 已用真实入库器端到端验证），新数据从此幂等。历史行不动也不会再无限增长。
- **不自动确认 binding 的 `semantic_key`**。95.9% 的绑定处于 `pending`（§3.2.4），「某一列**就是**某个语义身份」这件事只能由用户在第 1 批做好的工作台确认；自动确认会把第 3 批修掉的「假一致」重新制造出来。
  **但「按表头名认出列是什么」是另一件事**，第 9 轮已按**数据域限定**补上（§3.5.3），
  推断结果一律标 `inferred`，不参与家族口径比较 ⇒ 不产生假一致。
- **待确认**：`b_class.fact_*` 的唯一索引**已存在**（`uq_<表>_hash`），无需新建；如后续要再加业务键维度的唯一索引，必须先清理冗余行（`fact_shopee_orders_monthly` 5261 冗余行 / `fact_tiktok_orders_monthly` 852 冗余行），否则建索引会失败。
- **待确认**：weekly/monthly 事实表里 `订单号`/`平台SKU`/`SKU_ID` 三列 100% 为空——是"旧版模板遗留列"还是"当前口径要求"，需业务/数据侧确认后再决定 3.4 的宽表策略。
- **待确认**：「数据更新成功」这条绿色提示**不在本仓库**（`frontend/src`、`backend`、`frontend/dist`、`git log --all -S` 全无此字面串）⇒ 来自当前代码库之外的产物（浏览器缓存的旧版前端 / Service Worker / 另一套前端）。需当时的浏览器截图 + Network 面板记录才能定位。
- **✅ 已修复（2026-10-31，第 10 轮）**：`api.clearance_ranking_module` **恒返回 0 行**。根因是**两处代码缺陷**，不是数据没到位：① 两侧 `sku_key` 定义不对称（订单侧 `sku_id` 优先、积压侧 `platform_sku` 优先）；② join 条件拿「库存的数据来源平台 `miaoshou`」比「订单的销售渠道 `shopee`/`tiktok`」⇒ 恒不相等。修复后视图从 **0 行变成 143 行**，详见 §3.9。
- **✅ 生产视图重建已接进部署流程（第 11 轮）**：生产环境 `AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP=false`，且数据刷新/bootstrap 都会跳过「已存在的普通视图」⇒ 改完 `sql/` 资产光部署不生效。现在由 `scripts/deploy_remote_production.sh` 的 **Phase 2.7** 在部署中自动执行 `python3 /app/scripts/rebuild_views.py --target api.clearance_ranking_module`（旧容器已停、无排他锁冲突；失败即中止部署并回滚），**不需要人工去服务器上跑**（§3.9.8）。
- **⏸ 仍未做**：P6 服务层月窗口下推。P7 已把滞销榜查询压回 **47.7s**（在 60s 的 DB 预算内），
  但剩下的 22s 在**语义层**：`semantic.fact_orders_atomic` 对每一行都跑一次店铺别名解析
  （33265 次关联子查询）。真正的优化对象是那里，需另立专项评估对所有下游视图的影响面（§3.9.7）。
- **⏸ 同根因的兄弟缺陷（未改）**：`api.sku_clearance_ranking_module.sold_units_30d` 恒为 0（它把订单平台限制成库存平台），改法与 §3.9 一致，但它会改变 SKU 级滞销清单的动销量与 DOS 定价输入 ⇒ 需业务确认后单独发版（§3.9.6）。
- **⏸ v7.12.1 上线后的生产实测（2026-10-31）**：视图口径**已修好并生效**（`assets_drift=false`、模块 `ready`、新定义在跑 38~43s），但生产滞销榜**仍是 0 行** —— 根因是生产的 309 行积压**全部 `days_since_restock IS NULL`**（库存状态层 `mart.inventory_state` 没出数），被 `age_days >= 30` 全过滤掉。**这是采集/状态层的数据缺口，不是口径问题**；动作在数据侧补链路，不在视图 SQL 里改口径（§3.9.9）。
- **⚠️ 口径脆弱点（待处理）**：`COALESCE(days_since_restock, 0)` 把「取不到库龄」和「库龄 0 天」混成同一个值 —— 数据缺失被伪装成「都是新货」，`inventory_backlog_summary` 的 `active_sku_count` 也会把缺数据的行算成活跃。建议把「取不到」单独成一档，让缺失在数据上可见（§3.9.9）。

