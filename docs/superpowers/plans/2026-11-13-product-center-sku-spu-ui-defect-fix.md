# 商品中心 · SKU 资料页 SPU 缺陷：完整优化方案

> **状态**：批次 A / B / C **全部实施完成**（2026-11-13，本会话做完，不留给其他会话）
> **日期**：2026-11-13
> **发现者**：Walter 在实际使用「商品中心 → SKU 资料」页时发现
> **性质**：前端消费后端真源的方式错了；**后端口径、数据、接口全部正确**
> **实施记录**：见文末 §7（含批次 B1/B2、C1/C2 的取舍与红侧验证）

---

## 0. 一页纸

| 项 | 内容 |
|---|---|
| **现象** | 筛选框里写着 `XH-FASHION-005`，表格里却全是 `XH-TOYS-MYTK` 的货；下拉框是空的；行内换款下拉也打不开 |
| **根因** | 前端拿"可选款名单"时，拿到的是**装着名单的盒子**（一个 ref 容器），不是名单本身 |
| **影响面** | ① SKU 资料页的"所属 SPU"筛选**完全失效**；② 同一页每行的 SPU 下拉**打不开**（改不了归属）；③ 不影响利润测算页、不影响后端、不影响数据 |
| **数据层** | **干净**：1119 条当前归属，没有一个货挂两个款 |
| **后端** | **零改动**：筛选逻辑已正确，日志已证实 |
| **修法** | 改**一个工厂函数**（`createSpuSearch`）+ 一处脚本取值 + 5 处测试断言 + 1 个新守护测试 |
| **SSOT** | **符合**：前端只是没正确消费后端真源；修完不新增口径、不合并口径 |

---

## 1. 业务概念（先把话说清楚）

### 1.1 款与货

| | 是什么 | 例 | 关键属性 |
|---|---|---|---|
| **款（SPU）** | 一个**商品款式** —— 同一款的不同规格/颜色归到一个款 | `XH-TOYS-MYTK`「益智轨道车车辆玩具套装」 | 编码、名称、经营状态、类目 |
| **货（SKU）** | 实际可售的**最小单元** | `166851422928` | 编码、名称、规格、重量、体积、箱规、采购成本、基准售价 |

**关系是"一对多"**：一个款挂多个货；**一个货在同一时刻只能挂一个款**
（数据库层有唯一约束 `uq_bridge_spu_sku_current`；2026-11-13 生产实测 1119 条当前归属，
**零例外**）。

### 1.2 归属关系（款↔货）有三种状态，语义不同、不可合并

| 状态 | 含义 | 能不能复活 |
|---|---|---|
| `active`（当前有效） | 货现在挂在这个款下 | — |
| `inactive`（软删封存） | 款被删了 ⇒ 归属封存 | **能**（恢复款时会复活最早一条） |
| `historical`（换款归档） | 货从款 A 换到款 B ⇒ A 那条归档 | **不能**（它是"这个货换过款"的追溯证据，复活它等于把历史改回去） |

### 1.3 款的生命周期（经营成熟度）

```
candidate（候选，新建的、还没验证）
   → testing（测试，正在验证经营表现）
   → promoted（在营，正式在卖）
   → retired（淘汰，业务上不再经营；但 active 仍为 true，历史可查）
```

**关键不变量**：`active=false ⟹ biz_status='retired'`（删除 ⇒ 必然已淘汰）。
这条不变量由 `dim_spu` 的 **CHECK 约束在数据库层兜底**，不靠"大家记得一起写"。

### 1.4 两个"可选款"口径 —— 这是整个方案的关键

| 口径 | 判定 | 用来做什么 | 在哪用 |
|---|---|---|---|
| **浏览口径** | `active IS TRUE`（含"逻辑淘汰但没删"的款） | **筛选**：查东西，敲什么编码都能查 | SKU 资料页工具栏「所属 SPU」 |
| **可绑定口径** | `biz_status ∈ {candidate, testing, promoted}`（= 不是 retired） | **赋值/换款**：外键，款必须真实存在且现在还允许挂 | SKU 资料页每一行的 SPU 下拉 |

**两个口径不可混用**：筛选是"查询条件"（错一个编码只是查不到）；赋值是"外键"
（必须指向真实存在、且允许挂货的款，否则会造出挂不上的关系）。
⇒ 后端把两个口径**固化成两个独立端点**，前端不许自由拼装。

### 1.5 为什么"平台 SKU 利润测算"页没事

那一页的 SPU 候选来自**测算口径**（受平台 / 收货仓库 / 物流方式约束），
存的是一个 **reactive 数组** ⇒ Vue 正常拆包 ⇒ 下拉正常、筛选参数真的发出去了
（日志实证：`/api/platform-sku-profit/candidates?...&spu=XH-FASHION-006`）。

**这不是"同一件事的两种写法"，而是两个不同页面的两个不同业务问题**
（一个是主数据筛选，一个是定价测算），**不该合并**。

---

## 2. 根因（业务语言 + 技术定位）

### 2.1 一句话

> 前端向"值域工厂"要了一份"可选款名单"，但界面上读到的不是名单，
> 而是**装着名单的那个盒子**（一个 ref 容器）。

Vue 的规则：**模板只自动拆包"最外层"的 ref**。
`spuBrowse` 是工厂返回的**普通对象**，里面的 `options` / `loading` 是 ref
⇒ 模板里 `spuBrowse.options` 拿到的是 **ref 本身**，不是名单。

### 2.2 三个症状，同一个病根

| # | 症状 | 机制 |
|---|---|---|
| 1 | **下拉框是空的** | `:loading="spuBrowse.loading"` 传的是 ref 对象（恒为真）⇒ Element Plus 规则是"选项列表 vShow = options.size > 0 **且** !loading" ⇒ 选项列表**永不渲染** ⇒ 只剩一个空白块 |
| 2 | **一个款也选不中** | `v-for="item in spuBrowse.options"` 迭代的是 ref 的 5 个内部属性（`dep` / `__v_isRef` / `__v_isShallow` / `_rawValue` / `_value`）⇒ 5 个 **value=undefined 的空白项** |
| 3 | **表格永远不按款筛选** | 选不中 ⇒ `skuSpuFilter` 永远是空 ⇒ 请求**从不带 `spu=`** ⇒ 后端只能返回全量第一页 |

### 2.3 最小复现（用仓库自带的 vue 3.5.22 实跑，不是推理）

```
A) 普通对象 + 嵌套 ref（当前代码写法） => <li>[|]</li> × 5      ← 5 个空白项
B) reactive 对照组                   => <li>[XH-FASHION-005|XH-FASHION-005]</li>  ← 1 个正常项
```

### 2.4 证据链

| 证据 | 结果 |
|---|---|
| 生产访问日志 | `/api/spus/options?keyword=XH-FASHION-005` → **200，返回 1 条** ⇒ 后端没问题 |
| 生产访问日志 | `/api/skus` 的请求**从头到尾没有一次带 `spu=`** ⇒ 筛选从未生效 |
| 生产库 | `XH-FASHION-005` 当前挂货 **0 条** ⇒ 若筛选生效表格应为空，实际显示 20 行 ⇒ 证明没筛 |
| 生产库 | 1119 条当前归属，**没有一个货挂两个款** ⇒ 数据层干净 |
| 全前端扫描 | 同一写法**只有这 2 处**；其余 `store.*`（Pinia）、`operatingDimensions.*`（reactive）都正常 |

### 2.5 为什么测试没拦住

现有前端守护测试 `frontend/tests/productCenterSpuOptions.test.mjs` **全是"读源码文本"的断言**
（只验"用了 remote / 用了 allow-create / 接对了端点"），
**没有一个真正渲染过一次组件** ⇒
"端点接对了、代码写对了，但界面上是坏的"这一类缺陷，它**天然看不见**。

---

## 3. 优化方案

### 批次 A（必做，随下一版发版）—— 让界面真的能用

| # | 动作 | 落点 | 说明 |
|---|---|---|---|
| A1 | 值域工厂改成返回 **reactive** 对象，`options` / `loading` 是**普通值** | `frontend/src/domains/business/views/productCenterSpuOptions.js` | **一处改动，两个下拉同时生效** |
| A2 | 脚本里取候选集去掉 `.value` | `ProductCenter.vue` L1280（1 处） | 工厂形状变了，取值跟着变 |
| A3 | 现有测试的 5 处 `.value` 断言跟着改 | `frontend/tests/productCenterSpuOptions.test.mjs` L54/55/65/66/74 | 纯跟随，无行为变化 |
| A4 | **新增运行时守护测试**：用 `vue/server-renderer` 真渲染一次，断言**渲染出的选项数量 > 0 且编码是真编码** | `frontend/tests/`（新文件） | 补上"界面真的能用"这条断言。**放进 `frontend/tests/` 即自动进 CI**（`frontend-guard` job 通过 `scripts/ci_frontend_test_silence_gate.py` 跑 `frontend/{scripts,tests}/**/*.test.mjs`）⇒ **不用改流水线**；本地复现同一条命令：`cd frontend; node --test "tests/**/*.test.mjs"`（当前 195 tests 全绿） |
| A5 | **结构性门禁**：模板里不允许对"工厂返回的普通对象"直接取嵌套 ref | 同 A4（加一条断言） | 从结构上消灭"能work/不能work"两种写法 |

**模板不用改**（A1 改完 `spuBrowse.options` / `spuAssignable.options` 就能正常拆包）。
**后端不用改**（`/api/skus?spu=` 的筛选逻辑已正确，日志已证实）。

**验收口径**：修完后
① 下拉能列出候选款；② 选一款 ⇒ 表格**只**显示该款下的货；
③ 请求里**必须**带 `spu=`（用生产访问日志核对，和利润测算页同款证据）；
④ 行内下拉能打开、能看到"可绑定"候选并能换款。

### 批次 B（另排，建议做）—— 让"选款"这件事本身更好用

> 这批**改的是值域口径**（后端排序/默认候选），与批次 A 不是同一件事，单独排、单独验。

| # | 问题 | 现状（实测） | 建议 |
|---|---|---|---|
| B1 | 默认候选**按编码排序取前 50** | 287 个款里，前 50 个是 `XH-BABY-MC` ~ `XH-FASHION-695`；**`XH-TOYS-MYTK` 排第 277 位** ⇒ 玩具类几乎永远不在默认候选里 | 默认候选改为**按挂货数 / 最近更新**排序（运营找"有货的款"更常用），或至少在框内提示"可输入编码搜索" |
| B2 | 选到一个**没有挂货**的款 ⇒ 表格空 | `XH-FASHION-005` 当前挂货 0 条 | 空结果时给明确文案「该款当前没有挂货」，而不是笼统的"暂无数据" |
| B3 | 值的两个口径在界面上**不可见** | 筛选用浏览口径、赋值用可绑定口径，运营看不出为什么某款能筛到、却不能挂货 | 下拉里用分组/提示区分（如"已淘汰（仅可筛选）"） |

### 批次 C（另排，与前两批无关）—— 本次会话新发现的两条

| # | 问题 | 建议 |
|---|---|---|
| C1 | 同一组接口被**挂载两次**（`collection/routes.py` 与 `platform/routes.py` 都 include 同一批 5 个 router ⇒ 17 个路径 / 24 个条目双注册） | 加"router 唯一挂载点"守护用例 + 去掉重复挂载；今天无功能故障，但违反律 1 |
| C2 | **公开仓库跟踪着生产密码文件**（`.env.production.passwords.txt`，GitHub 仓库为 PUBLIC） | ① 先轮换（公开历史不可撤回）→ ② 取消跟踪 + `.gitignore` → ③（可选）历史清理（会作废全部已发布 tag，不可顺手做）→ ④ 补 `check_precommit_secrets.py` 的漏检 |

---

## 4. 是否符合 SSOT 原则

| 判据 | 结论 | 理由 |
|---|---|---|
| 真源是否唯一 | ✅ **符合** | 修复的是"前端没正确消费后端真源"；`/api/spus/options`（浏览）与 `/api/spus/assignable-options`（可绑定）**仍是唯二口径**，本批**不新增第三个** |
| 口径是否被合并/稀释 | ✅ **符合** | 两个口径保持分离；利润测算页的**测算口径**与主数据口径**不互相污染** |
| 派生关系是否都从真源来 | ✅ **符合** | 「可绑定」判定来自 `product_spu_lifecycle.py`，筛选来自 `product_center.py` 的两个端点；前端只是消费者 |
| **是否存在"同一个概念两套写法"** | ⚠️ **本批要消灭** | 这次缺陷的本质就是"值域"在前端有**能work（reactive）**与**不能work（普通对象+嵌套ref）**两种写法 ⇒ 修完**只保留一种**（工厂只准返回 reactive），并加结构性门禁 |
| **判定口径是否写在测试里** | ⚠️ **本批要补** | 现有前端测试只断言"源码长相" ⇒ 必须补**运行时**断言（真渲染一次），否则同类缺陷还会再犯 |
| 门禁是否真在 CI 里跑 | ✅ **本批顺带修正** | 前端 `frontend-guard` job 已在跑 `frontend/{scripts,tests}/**/*.test.mjs`；本批新增的运行时测试放进 `frontend/tests/` **自动被 CI 跑到**，不新增"写了但不跑"的文件 |

**一句话结论**：**方案符合 SSOT** —— 它不新增口径、不合并口径，只是把"前端怎么读后端的真源"
这件事从"两种写法"收敛成"一种写法"，并把"界面真的能用"钉进测试。

---

## 5. 风险与回滚

| 风险 | 等级 | 处置 |
|---|---|---|
| 改工厂影响利润测算页？ | **无** | 利润测算页的候选来自 `operatingDimensions`（reactive），不经过这个工厂；已核对 |
| 改工厂影响"SPU 管理"tab？ | **无** | 该 tab 用 `/api/spus` 分页表，与值域工厂无关 |
| 现有前端测试要改 5 处断言 | 低 | 纯跟随式改动；改完断言内容不变（数量、编码仍一样） |
| 改完仍不生效 | 低 | 验收口径第 ③ 条用**生产访问日志核对 `spu=`**（同利润测算页的证据法），不靠"看起来对了" |
| 回滚 | — | 纯前端改动，单个 commit，回滚即恢复；不涉及数据、不涉及迁移 |

---

## 6. 需要拍板的点

1. **批次 A 是否随下一版发版**（建议：是 —— 它是"运营能不能用"的阻塞项）。
2. **批次 B 是否要做**（建议：做 B1 + B2；B3 可后置）。
3. **批次 C 的两条**（建议：先做 C2 轮换 + 取消跟踪，C1 另排）。

> **2026-11-13 更新**：Walter 拍板 —— **三个批次全部在本会话实施完，不留给其他会话**。

---

## 7. 实施记录

### 批次 A（前端：让界面真的能用）

| 项 | 内容 |
|---|---|
| **A1** | `frontend/src/domains/business/views/productCenterSpuOptions.js`：`createSpuSearch` 改为返回 **`reactive` 对象**，`options` / `loading` 是**普通值**（不再是藏在普通对象里的 ref）。注释里写明了"为什么必须这样"与事故机制 |
| **A2** | `ProductCenter.vue` L1280：`spuAssignable.options.value` → `spuAssignable.options`（1 处） |
| **A3** | `frontend/tests/productCenterSpuOptions.test.mjs`：5 处 `.value` 断言跟随修改（L54/55/65/66/74），**断言内容不变** |
| **A4** | 新增 `frontend/tests/productCenterSpuOptionsRender.test.mjs`（5 例）：<br>① 模板可见路径拿到的是**名单**（`Array.isArray(options)`）且 `loading` 是**布尔**（不是恒真的 ref）；<br>② **真渲染一次**（`vue/server-renderer` + render function），断言款编码出现在 HTML 里、且没有空白项；<br>③ 搜索失败清空候选且解除 loading；<br>④ 工厂必须 `reactive` 且不许再 import `ref`；<br>⑤ 组件不许再对值域对象取 `.value` |
| **A5** | 结构性门禁即 A4 的 ④⑤ 两条（同一文件，不另起炉灶） |
| **TDD 红侧** | 用**旧写法**在临时目录实跑守护断言：<br>`Array.isArray(options)` = **false**、`typeof loading === 'boolean'` = **false** ⇒ 两条断言都会红；<br>渲染直接崩在 `this.spu.options.map is not a function` ⇒ **守护确实抓得住这个 bug**（不是"写完就绿"的假测试） |
| **验证** | 前端测试 **200 passed / 0 failed**（原 195 + 新增 5）；`npm run build` **✓ built in 13.65s**；eslint 在本仓库**不是门禁**（未改动文件同样 135 个同类 error，CI 无 eslint 步骤）⇒ 不做风格重写 |

### 批次 A 回归修复（提交 `1f7cb413`）

| 项 | 内容 |
|---|---|
| **事故** | 批次 A 把值域工厂的局部状态容器命名成了 `api` ⇒ `api.search(query)` 被前端 API 契约门禁（`scripts/validate_frontend_api_methods.py`，正则 `(?:this\.)?api\.(\w+)\s*\(`）判成「调用了不存在的后端方法 search」⇒ **Validate Data Flow 流水线红**（run `43387187814`） |
| **修法** | 局部容器改名 `valueDomain`，并在注释里写明**为什么不能叫 `api`** ⇒ **不弱化门禁、不改门禁正则** |
| **教训** | 门禁**本来就存在**（`backend/tests/test_validate_frontend_api_methods_contract.py` 断言全量扫描 `missing_calls == 0`）—— 是推送前没跑后端全量才漏出去 ⇒ **推 main 前必须跑完根 `tests/` + 后端全量** |

### 批次 B1：值域默认候选按「当前挂货数」排序（提交 `f8c44012`）

| 项 | 内容 |
|---|---|
| **问题（生产实测）** | 284 个在售款按编码排序时前 50 个是 `XH-BABY-MC` ~ `XH-FASHION-695`，`XH-TOYS-MYTK` 排**第 277 位** ⇒ 玩具类几乎永远不在默认候选里 |
| **修法** | 新增 `_spu_option_order()`（当前挂货数 desc + 编码 asc）；浏览口径与可绑定口径**共用同一份**排序 ⇒ 不会一个按编码、一个按挂货数 |
| **口径纪律** | 排序**不是口径**（哪些款可选仍由各自端点的过滤条件决定）；挂货数判定引用真源 `current_binding_condition()`；用相关子查询而非 join+group_by（不改 SELECT 形状，也不引入「非聚合列」分组问题） |
| **TDD 红侧** | 把 `_spu_option_order` 临时改回「按编码排」⇒ **4 条新用例全红**（3 条行为 + 1 条口径来源）；恢复后 14 passed |
| **测试基建** | 新增本地 fixture：SQLite `ATTACH ':memory:' AS core` 后只建 `dim_spu` / `bridge_spu_sku` —— 生产表挂在 PostgreSQL 的 `core` schema 下，仓库既有 `sqlite_session` fixture 会报 `unknown database core`；沿用仓库里 `backend/tests/data_pipeline/test_refresh_queue_service.py` 的成熟做法 |

### 批次 B2：空结果说清原因与下一步（提交 `c121c3f3`）

| 项 | 内容 |
|---|---|
| **问题** | 选中一个当前挂货 0 条的款（生产实测 `XH-FASHION-005`），表格只显示笼统的「暂无数据」⇒ 运营以为系统坏了；下拉搜不到也只显示「无数据」 |
| **修法** | SKU 表格接 `:empty-text="skuEmptyText"`（按款筛时显示「款 X 当前没有挂货」）；两个下拉各接一套 `no-data-text`（浏览口径「换个关键词」/ 可绑定口径「先去建款」—— 下一步动作不一样） |
| **TDD 红侧** | 临时拆掉表格 `empty-text` 接线、并把浏览口径的 `no-data-text` 换成 assignable ⇒ **2 条接线用例红**；恢复后 7 passed |
| **B3 取消** | 实测浏览口径与可绑定口径**集合完全相同**（生产 284 = 284，差集 0）⇒ 无适用对象，不为不存在的情况写界面；且加 `biz_status` 会破坏既有契约 `set(payload) == {"spu","spu_name"}` |

### 批次 C1：同一组接口被挂载两次（提交 `db57034d`）

| 项 | 内容 |
|---|---|
| **实测（改前）** | development / collector 各 **24 条 (路径, 方法) 重复注册、涉及 17 条路径**；production **0 条**（**production 根本不注册 collection 域**）；FastAPI 生成 OpenAPI 时为每条重复路由打 `UserWarning: Duplicate Operation ID` |
| **修法** | 账号类 router（主账号 / 店铺账号 / 店铺别名 / 平台店铺ID发现 / 仓名别名）的**唯一挂载点**定在 **platform 域**，删掉 collection 侧那 5 条 include。⚠️ **不能反过来删 platform 侧的** —— production 不注册 collection 域 ⇒ 账号类接口在生产上只由 platform 提供 |
| **改后实测** | 四种模式（development / collector / collector+local / production）重复条目**全部归零**（759 → 735、409 → 385） |
| **守护** | 新建 `backend/tests/test_router_unique_mount_points.py`：① 四种模式都不许有重复 (路径, 方法)；② production/dev 下账号类接口依然存在（防「去重复」变「删接口」）；③ 这 5 组端点函数各自只注册一次；④ 生成 OpenAPI 时不许出现 `Duplicate Operation ID` 警告（**这才是重复挂载唯一可观测的信号** —— schema 里 operation_id 反而唯一，只断言 schema 会得到一条「写完就绿」的假测试） |
| **TDD 红侧** | 把 5 条 include 临时放回 collection 侧 ⇒ **6 条守护用例红**；恢复后 19 passed |

### 批次 C2：公开仓库的密钥与店铺账号密文（提交 `c31f77e3`）

| 项 | 内容 |
|---|---|
| **取证** | 只读、全程 SHA-256 比对、不打印任何值。**现役密钥未泄露**（生产 `.env` 与 4 个容器的 5 个敏感值与仓库旧值逐项全不同；旧密钥解不开生产库里的账号密码）。**但公开的是已废弃的旧密钥**，且 —— ⚠️ **密文与解密密钥同时公开**：仓库同时跟踪 `accounts.enc`（Fernet 密文）与 `.env.cleaned`（带 `ACCOUNT_ENCRYPTION_KEY`）⇒ 实测**可用公开仓库里的密钥直接解开** `accounts.enc`，解出 **15 个店铺账号**（Amazon / Shopee / Tiktok / 妙手ERP / miaoshou），**每个都有非空密码**，还带邮箱密码与手机号 |
| **处置** | ① 取消跟踪 4 个文件（`git rm --cached`，本地保留）；② `.gitignore` 补 `.env.*`（含 `.env.limiter` 例外）/ `*.passwords.txt` / `*.enc`；③ `is_blocked()` 从「逐个文件名」改成**按规则**拦（`.env` 家族 / 疑似敏感名 + 数据类扩展名 / 加密与密钥后缀），敏感名规则**不误伤**文档与脚本；④ 新建 `tests/test_secret_files_not_tracked.py` 并进 CI 根契约清单；⑤ `docs/guides/ENV_FILE_CONTRACT.md` 增「Repository Tracking Policy」 |
| **TDD 红侧** | 旧版 `is_blocked()` 对 6 个泄露文件**漏放行 5 个**；取消跟踪前 HEAD 里 4 个文件仍在跟踪 ⇒ 新守护在旧状态下必红 |
| **历史不可撤回** | `git filter-repo` 会作废全部已发布 tag（含 `v7.24.0`）⇒ **本会话明确不做** |
| **仍需拍板** | 轮换那 15 个店铺账号密码、删除生产机上的旧密钥副本、确认旧密钥在已下线环境是否还活着 —— 已写进 `docs/superpowers/plans/STATUS.md` |

### 回归结果（批次 A/B/C 全部落地后）

| 范围 | 结果 |
|---|---|
| 后端全量 `backend/tests` | **4593 passed / 7 skipped / 0 failed**（基线 4579 + 14） |
| 前端 `frontend/tests` | **207 passed / 0 failed** |
| 根 `tests/` | 758（基线）+ 本批新增 35 例密钥守护 |
| API 契约门禁 / 前端 API 方法门禁 | 0 错、0 缺失（基线一致） |

