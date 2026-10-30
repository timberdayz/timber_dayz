# 采集同步模块 · 前后端一体优化方案

> 状态：审查结论 + 待拍板方案（**本文档不含任何已落地的代码改动**）
> 审查范围：`backend/services/{template_hash_policy, semantic_hash_policy_service, semantic_field_registry, template_save_readiness_service, field_mapping_template_service, template_family_service, template_semantic_binding_backfill}.py`、`backend/domains/data_platform/routers/field_mapping_templates.py`、`frontend/src/components/dataSync/{TemplateUpdateWorkbenchDrawer,TemplateDeduplicationReviewPanel}.vue`、`frontend/src/domains/data_platform/utils/{deduplicationSelection,headerBindings}.js`
> 取证方式：真实库只读查询 + 真实 HTTP 接口重放 + node 直跑前端真实模块 + 后端日志还原用户操作序列。全部结论标注了 `文件:行号`。

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

### 第 4 批｜环境与可观测

| # | 改动 | 说明 |
|---|------|------|
| 4.1 | **修正超时预算倒置**：DB `statement_timeout` 必须 < 前端超时（`api/index.js:30-32` 的注释要求如此，实际 120s > 70s）⇒ DB 设 60s，前端保持 70s | `frontend/src/api/index.js:25-37`、`backend` DB 配置 |
| 4.2 | `/api/dashboard/clearance-ranking` 慢查询治理（索引/预聚合）。实测该查询跑满 120s，间隔 71/72/73 秒重试，且占满事件循环使模板请求排队 | `frontend/src/api/dashboard.js:113`、`data_sync.py` 对应实现 |
| 4.3 | 错误文案区分"超时 / 断网 / 服务端错误"（现在 `timeout of 70000ms exceeded` 被当网络错误原样抛出） | `frontend/src/api/index.js:688-708` |

---

## 3.1 数据修复诊断结论（2026-10-30，只读诊断，**未执行任何真实库变更**）

脚本：`scripts/normalize_template_deduplication_fields.py`（干跑模式），验证：`backend/tests/test_normalize_template_deduplication_fields.py`（11 项，隔离库全绿）。

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

⇒ **需要业务/数据侧确认后才能修**：脚本刻意**不**自动补齐缺失身份键（补哪个、从哪列补，是业务判断，不是机械映射）。

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
- **不执行历史数据修复**（本次用户明确暂不处理数据）。
- **待确认**：weekly/monthly 事实表里 `订单号`/`平台SKU`/`SKU_ID` 三列 100% 为空——是"旧版模板遗留列"还是"当前口径要求"，需业务/数据侧确认后再决定 3.4 的宽表策略。
- **待确认**：「数据更新成功」这条绿色提示**不在本仓库**（`frontend/src`、`backend`、`frontend/dist`、`git log --all -S` 全无此字面串）⇒ 来自当前代码库之外的产物（浏览器缓存的旧版前端 / Service Worker / 另一套前端）。需当时的浏览器截图 + Network 面板记录才能定位。
