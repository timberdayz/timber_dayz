# 人力管理页缺陷修复 + 归属「角色」退休 + 批量能力 —— 优化计划 v2

> 状态：**待实施**（业务已拍板：①角色彻底删除，不做人工勾选，也不做岗位自动判定；②「每月成本录入任务」整条链路删除，避免遗留；③一店一主管的约束取消——现实是一店多管理层同时吃提成）
> 日期：2026-11-26 | v1 结论已被业务现实推翻，本文件为**唯一有效版本**
> 范围：`frontend/src/domains/business/views/HumanResources.vue`、`frontend/src/domains/business/views/hr/ShopAssignment.vue`、`frontend/src/domains/business/views/hr/shopAssignmentRules.js`、`frontend/src/api/index.js`、`backend/services/employee_task_sources.py`、`backend/services/employee_task_policy.py`、`backend/domains/business/routers/expense_management.py`、`backend/domains/business/routers/hr_commission.py`、`backend/schemas/hr.py`、`backend/services/personal_performance_workbench_service.py`、`modules/core/db/schema_parts/business.py`、`current_migrations/versions/`
> 关联：[[2026-11-19-hr-user-management-optimization]]、[[2026-11-21-commission-and-performance-caliber-unification]]（提成口径**不动**）

---

## 0. 业务现实与最终形态

### 0.1 业务现实（业务方 2026-11-26 给出的真实场景）

同一店铺同时有多个层级的人吃提成：

| 人 | 层级 | 提成比 |
|---|---|---|
| 泽伟 | 主管 | 15% |
| 叶海川 | 总经理 | 5% |
| 叶大望 | 总经理 | 5% |
| 张三 | 操作员 | 10% |
| **合计** | | **35%**（上限 100%，余下归公司） |

⇒ **「主管 / 操作员」这个二分法装不下现实**：按岗位自动判定 ⇒ 两个总经理都是"主管"⇒ 一店一主管直接冲突；保留人工勾选 ⇒ 回到"用户每次都要选"的原问题。

### 0.2 最终形态（三个概念各归其位）

```
归属配置 = 「谁在这家店分多少提成」   —— 多人、比例各自、**不再有角色分类**
层级展示 = 员工的**岗位名**（总经理/主管/专员…）—— 来自员工档案，只读，**不手选、不落库**
成本录入 = 不再自动派「店主管」任务    —— 整条早期设计删除
```

**页面长这样**（A 店铺示例，新形态）：

```
人员
  泽伟（主管）      15%
  叶海川（总经理）   5%
  叶大望（总经理）   5%
  张三（专员）      10%
  合计 35%
```

- 不再有"角色"下拉框；
- 不再有"一店一主管"拦截（两个总经理同店合法）；
- 提成金额口径不变：可分配利润 × 归属提成比（零系数），**钱一分不变**。

---

### 0.3 两套都叫「角色」的东西 —— 边界与防误删（实施前必读）

系统里存在**两个互不相干、但中文名几乎撞车**的「角色」：

| # | 是什么 | 存在哪 | 中文名 | 含义 | 本次处置 |
|---|---|---|---|---|---|
| ① | **访问权限角色** | `core.dim_users.roles` + 前端 `frontend/src/config/rolePermissions.js`（`ROLE_CONFIG`）+ `frontend/src/utils/authRoles.js` + 路由 `meta.roles` | admin **管理员** / manager **主管** / operator **操作员** / finance **财务** | **谁能登录系统、能看到哪些页面、能不能改配置** | ✅ **整体不动，一行不碰** |
| ② | **归属角色** | `a_class.employee_shop_assignments.role` + `backend/schemas/hr.py` 的 3 个 schema + 前端 `ShopAssignment.vue` | supervisor **主管** / operator **操作员** | 谁在这家店拿提成时**被归成哪一类** | ❌ **本批次退休并删除** |

**撞车点**：①里的 manager 中文名是"主管"、operator 中文名是"操作员"，与②的 supervisor/operator 中文名**一模一样**。实施时必须按**代码位置**而不是按中文字样判断：

| 保留（①访问权限） | 删除（②归属角色） |
|---|---|
| `frontend/src/config/rolePermissions.js` | `frontend/src/domains/business/views/hr/ShopAssignment.vue` 里的 `form.role` / 角色下拉 |
| `frontend/src/utils/authRoles.js` | `frontend/src/domains/business/views/hr/shopAssignmentRules.js` 里的 `inferAssignmentRole` |
| 路由 `meta.roles`、后端 `require_admin` / `Depends(get_current_user)` | `backend/schemas/hr.py` 的 `EmployeeShopAssignment{Create,Update,Response}.role` |
| `core.dim_users.roles` | `backend/services/employee_task_sources.py` 的 `role == "supervisor"` 判定 |
| 账号管理页的业务角色（`business_role`） | `a_class.employee_shop_assignments.role` 列 |

**自查口径**：改完后，全仓 grep `role` 命中的应当只剩「访问权限角色」「账号业务角色」和无关命名（训练 `role_name`、采集 `participant_role` 等）；**归属相关的 role 必须零命中**。

---

## 1. 事实基线（2026-11-26 生产只读核验）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 人力管理页报错是**纯前端未定义引用**（假警报） | 生产前端 `HumanResources-dd4e75b0.js` 含 `loadEmployees()])}catch(...k.error("加载数据失败，请刷新重试"))`；全文 `loadEmployees` 1 次、定义 0 次；nginx 日志同刻 HR 接口**全部 200** |
| F2 | 角色字段的**看板用途已经死了** | 2026-11-21「三列合一」改造后前端不再消费 `supervisor_profit` / `operator_profit`（`frontend/src` 全量 grep **0 命中**）；后端仍在算，没人看 |
| F3 | 角色字段的**任务派发用途已停摆** | `monthly_cost_entry` 任务生产**仅 2 条，最后一条 2026-06-18**；`a_class.employee_shop_assignments` 现 **0 行** ⇒ `resolve_shop_supervisor_user_id` 必然抛 "No supervisor assignment found"；`expense_management.py:1092` 把异常吞成 warning ⇒ **成本录入正常，协作任务半年多没生成，没人收到** |
| F4 | 角色的第三处下游只是**留痕快照** | `personal_performance_workbench_service.py:394` 写 `role_snapshot=assignment.role` |
| F5 | 提成计算**不依赖**角色 | 后端提成口径是「可分配利润 × 归属提成比」（零系数），全链路无按 supervisor/operator 分流的金额计算 |
| F6 | 比例上限是**按店铺聚合** | `_validate_shop_assignment_ratio_limit(existing_rows=同店同月全部行)` ⇒ 35% 合法，100% 为上限；**不是**按员工聚合 |
| F7 | 归属表零存量 | 生产 `a_class.employee_shop_assignments` **0 行** ⇒ 改口径/删列零历史包袱 |
| F8 | 岗位数据几乎没录 | 生产 11 名员工**仅 1 人**挂岗位（SUPV 主管），部门仅 2 人有 ⇒ 岗位只能当**展示**，不能当判据 |
| F9 | 批量能力现状 | 已有「复制上月配置」（按月覆盖未锁定店铺）+「批量保存」= **串行逐行 `for` + await，遇错即停**；**没有**批量挂靠、**没有**批量改比例、**没有**批量删除 |

---

## 2. 批次

### 批次 1 · 人力管理页假报错修复（前端，零接口改动）

- 删 `HumanResources.vue:875` 的 `loadEmployees()` 调用（父组件不再持有员工列表）。
- 清掉同一次重构残留的死代码 `showPayrollDialog` / `confirmPayroll` / `reopenPayroll` / `markPayrollPaid` 及其专属状态（按引用面确认后删）。
- 验收：进人力管理页**无红条**；console 无 `ReferenceError`；点「刷新数据」不报错；表格与 7/2/2/11 统计不变。

### 批次 2 · 角色退休（前后端 + 迁移，唯一有迁移的批次）

**后端删除**
| 位置 | 动作 |
|---|---|
| `backend/schemas/hr.py` | `EmployeeShopAssignmentCreate/Update/Response` 删 `role` 字段 |
| `hr_commission.py` create/update | 删 `role` 透传；请求里带 `role` 忽略（不报错，兼容旧页面） |
| `hr_commission.py` 结算预览 ×2 | 删 `assign_by_shop` 的 `supervisors`/`operators` 分组与 `supervisor_profit` / `operator_profit` 计算及返回字段 |
| `hr_commission.py` copy-from-prev-month | 不再复制/携带 `role` |
| `backend/services/employee_task_sources.py` | **删** `resolve_shop_supervisor_user_id`、`sync_monthly_cost_entry_task` |
| `backend/services/employee_task_policy.py` | **删** `monthly_cost_entry` 任务策略 |
| `backend/domains/business/routers/expense_management.py` | 删成本录入后的任务派发调用段（成本录入照常成功，不再生成协同任务） |
| `personal_performance_workbench_service.py` | 快照不再写 `role_snapshot`（**实施前确认该列可空性与历史行数**） |
| `modules/core/db/schema_parts/business.py` | `EmployeeShopAssignment.role` 列删除 |
| 迁移 | `current_migrations/versions/xxx_drop_employee_shop_assignment_role.py`（含**可降级**脚本）；同步删/置空快照表的 `role_snapshot`（按确认结果） |

**前端删除 / 改造**
- `ShopAssignment.vue`：删角色下拉框（`form.role` 必填项）、`handleEmployeeChange` 的角色推断、`roleByEmployee` 映射、汇总区与人员行的「主管/操作员」标签、保存时的 role 匹配键（改为按 `employee_code` 匹配）。
- **层级展示改为岗位名**：人员行显示 `泽伟（主管）`，取员工档案 `position_name`；无岗位显示 `（未设岗位）`。
- `shopAssignmentRules.js`：`inferAssignmentRole` 删除；`summarizeEmployeeCommissions` 的 `role` 字段改为 `position_name`（若页面需要层级标签）。
- 标题文案「添加主管/操作员」→「添加人员」。
- **不动**（访问权限体系）：`frontend/src/config/rolePermissions.js`、`frontend/src/utils/authRoles.js`、路由 `meta.roles`、`backend/dependencies/auth.py` 的 `require_admin` / `get_current_user`、`core.dim_users.roles`、账号管理的 `business_role`。

**测试同步**
- `frontend/tests/hrShopAssignmentSettlementPreview.test.mjs:74-80`（断言 role=supervisor）改为断言岗位名展示。
- `backend/tests/test_employee_task_sources.py` 的 supervisor 用例删除；`test_employee_task_policy.py` 的 `monthly_cost_entry` 用例删除；`test_hr_shop_assignment_rules.py` 内 role 相关断言同步。

**验收**：页面上找不到任何"角色/主管/操作员"字样（仅岗位名）；录成本不再生成协同任务也不报错；提成金额与改动前一致（同一输入同金额）；迁移可升可降。

### 批次 3 · 批量能力（用户新诉求）

**现状盘点**：已有「复制上月配置」「批量保存」（串行、遇错即停）。本次补齐：

| 能力 | 交互 | 后端 |
|---|---|---|
| **批量挂靠** | 店铺行多选 → 「批量挂靠」→ 选 1 名员工 + 提成比例（可对所有选中店统一比例）→ 一次提交 | 新增 `POST /hr/employee-shop-assignments/batch`（一个事务，逐项返回成功/失败） |
| **批量改比例** | 人员行多选 → 「批量调整比例」→ 统一设为 X% / 统一加减 X 个百分点 | 同上端点的 `batch-update` 模式（按 assignment id 更新） |
| **批量删除归属** | 人员行多选 → 「批量移除」 | 同上端点的 `batch-delete` 模式 |
| **批量保存加固** | 现有「批量保存」改**并行 + 逐行结果汇总**：成功 N 条 / 失败 M 条 + 失败原因清单，**失败不中断其余行** | 前端并发提交 + 汇总展示（不改接口） |
| **批量挂靠预检** | 提交前对每个受影响店铺做「当月在职人员比例总和 ≤ 100%」预检 | 后端逐店校验，超限的店跳过并在结果里说明是哪家店、超了多少 |

- 原则：**不新增"批量"专用页面**，就在现有配置表上加多选 + 一个批量操作条；批量是"同一动作重复多次"的加速器，不改变业务模型。
- 验收：选 3 家店一次挂同一人（比例 5%）⇒ 3 条归属一次成功；其中 1 家店已超 100% ⇒ 该店跳过并明确提示，另 2 家成功；批量保存里有一行失败 ⇒ 其余行照常保存并看到失败清单。

### 批次 4 · 岗位补录（业务前置）+ 层级展示可维护

- 页面层级直接来自员工档案的职位 ⇒ **必须补录岗位**，否则页面全是"（未设岗位）"。
- 生产现状：11 人仅 1 人有岗位（SUPV 主管）。需给实际负责人挂 SUPV 主管、其余挂实际岗位（职位表已有 10 个标准职位，**无需新建**）。
- 建议在「员工管理」页支持**批量设置职位**，与批次 3 的批量能力同一交互思路。
- 验收：补录后归属页显示真实层级；无岗位者明确显示"（未设岗位）"而不是空白。

### 批次 5 · 守护与门禁

| 项 | 内容 |
|---|---|
| 后端守护 | 新增 `backend/tests/test_hr_assignment_no_role.py`：归属写入/复制不带 role；成本录入不再派任务且不报错；提成金额不受影响 |
| 前端守护 | 新增 `frontend/tests/hrAssignmentNoRoleUi.test.mjs`：页面源码不含"角色/主管/操作员"下拉与标签；层级取岗位名；批量三能力入口存在 |
| 门禁 1 | 清零 `frontend/src/domains/business/views/hr` + `HumanResources.vue` 现有 **25 个 lint 错误**，再把 `eslint --rule '{"no-undef":"error"}'` 挂进前端 CI ⇒ 批次 1 那类"调用了不存在的函数"下次直接红 |
| 门禁 2 | 「月度成本录入任务」删除后，守护测试断言 `monthly_cost_entry` **不再出现在**任务策略与派发链路（防复活） |

---

## 3. 业务侧要做什么

1. **给每个员工挂职位**（职位表已有 10 个标准职位，无需新建）：负责人挂 SUPV 主管，其余按实际岗位。
2. **按新形态重配归属**：一行一人一比例，层级由岗位自动显示，**不再选角色**。
3. **知悉一条能力下线**：录成本不再自动生成「每月成本录入」协同任务（该任务自 2026-06-18 起已在生产静默停摆，删除不改变现状行为，只是不再留半死代码）。

---

## 4. 验证

**本地**
- `npm run build`；前端 `node --test` 全量；后端 `pytest backend/tests` 全量；ruff/black 绿。
- 走查：① 人力管理页无红条；② 归属页无角色、层级显示岗位名；③ A 店 4 人（泽伟 15%/叶海川 5%/叶大望 5%/张三 10%）一次配齐、合计 35% 不报错；④ 批量挂靠 3 店、其中 1 店超限被跳过并说明；⑤ 批量保存部分失败仍能完成其余行。
- **金额回归**：同一店同一月，改造前后**预计提成金额完全一致**（角色不参与计算，只做展示与派发）。

**生产（发版后，只读）**
- 前端产物 grep：无 `role` 下拉文案、无 `supervisor`/`operator` 标签文案；`loadEmployees` 不再出现。
- `healthz/ready` 版本号对上；7 容器 healthy；迁移链头前进且 `missing_tables/columns` 为空。
- `core.employee_tasks` 中 `monthly_cost_entry` 计数不再增长（预期恒为 2 条历史）；录成本接口 200 且无 warning 刷屏。

---

## 5. 风险与回滚

| 风险 | 评估 | 处置 |
|---|---|---|
| 批量写入放大错误面 | 中 | 后端单事务 + 逐店比例上限预检 + 逐项结果返回；失败项不影响成功项 |
| 删 role 列影响绩效快照 | 中 | 实施前确认 `role_snapshot` 可空性与历史行数（**列为实施前必查项**） |
| 删任务链路后有人找"每月成本录入任务" | 低 | 该任务生产已停摆 5 个多月，无人收到；已知会同步业务方 |
| 页面层级显示"（未设岗位）" | 高概率（F8） | 批次 4 岗位补录；页面明确提示而非空白 |
| 回滚 | 低 | 唯一迁移是删列，**需降级脚本**；回滚 = 重新部署上一个 tag + 执行降级迁移（生产 0 行 ⇒ 实际回滚成本≈0） |

**实施前必查项（3 条）**
1. `PersonalPerformanceAssignmentSnapshot.role_snapshot` 列定义与生产历史行数；
2. `copy-from-prev-month` 是否透传 `role`（实施时以代码为准）；
3. 本地库 `a_class.employee_shop_assignments` 是否存在待清理行。

---

## 6. 边界（本次不做）

- 不改提成口径、绩效系数、赛马口径（[[2026-11-21-commission-and-performance-caliber-unification]] 已定稿）。
- 不改「共同承接 100%」的只读展示。
- 不做历史月份归属回填（生产 0 行）。
- 不做"主管/操作员"的任何替代分类（不做岗位自动判定、不做店铺负责人字段）——**层级只是展示，来源是员工档案的职位**。
- 不改看板口径（`supervisor_profit`/`operator_profit` 本就无人消费，随角色一并删除）。

---

## 7. 实施记录（2026-11-26 完成）

### 7.1 实际落地的方案（与计划的两处调整）

1. **层级展示的数据源用「全量员工」而不是「在职员工」**。
   计划里没写死这一条；实现时发现若只用在职名单，**离职员工的归属行会误显示「（未设岗位）」**
   （离职员工的归属行是历史事实，工资单/绩效/提成审计都还指向他）。
   ⇒ 职位映射取全量 `employees`，下拉选人仍只给在职员工（`employeesActive`）。
2. **「工资单草稿弹窗」保留未删**。该弹窗在模板里已无任何入口（薪资维护早已迁到员工薪资页，
   模板里的操作按钮全部改成跳转），但它本身仍被模板引用（`savePayroll` 等），
   按上线前规则「不做宽泛重构」⇒ 本次只删 4 个**确实无引用**的死函数，
   弹窗与表单作为已知遗留项留待后续单独清理。

### 7.2 改动清单

**前端**
- `HumanResources.vue`：删悬空 `loadEmployees()` 调用、4 个死函数、随之失效的 `ElMessageBox` 导入
- `ShopAssignment.vue`：角色退休（删下拉/字段/提交/推断/标签）、层级改职位名、表格多选、
  批量挂靠 / 批量调整比例 / 批量移除、批量保存改并行 + 逐行汇总
- `shopAssignmentRules.js`：删 `inferAssignmentRole`，新增职位名映射与批量载荷构造纯函数
- `api/index.js`：新增 `batchHrEmployeeShopAssignments`
- 新增守护：`hrHumanResourcesPageIntegrity.test.mjs`、`hrAssignmentNoRoleUi.test.mjs`

**后端**
- 删归属 role 全链路（schema / ORM / 路由 / 看板分摊 / 复制）
- 删「每月成本录入任务」整条链路（策略 + 派发函数 + 费用路由调用点）
- 新增 `POST /hr/employee-shop-assignments/batch`（create / update / delete 三模式，单事务、逐项成败）
- 新增迁移 `20261244_drop_employee_shop_assignment_role`（删两列，**可降级**）
- 新增守护：`test_hr_assignment_no_role.py`、`test_hr_employee_shop_assignment_batch.py`

**门禁**
- `ci.yml` 的 `frontend-guard` job 新增：人力域 lint（**显式打开 `no-undef`**）+ 前端测试全量
- 新增契约守护：`tests/test_ci_frontend_quality_gate_contract.py`、
  `tests/test_access_permission_roles_untouched_contract.py`、
  `backend/tests/test_monthly_cost_task_retired.py`（均进根契约清单）

### 7.3 实施中发现并修掉的一个回归

删除「主管/操作员」分组时，把 `supervisor_profit + operator_profit` 改写成了
`allocatable_profit * ratio_sum` —— 这是在路由里**就地复刻提成公式**，
违反「提成公式只许住在 `commission_caliber.py`」的 SSOT。
被 `test_commission_single_source.py` 拦下 ⇒ 改回调用真源
`calculate_employee_shop_commission(...)`（数学等价，量化精度更高）。

### 7.4 验证结果

| 项 | 结果 |
|---|---|
| 后端（本次改动 + 提成口径 + 迁移链 + 三条新守护） | 全绿 |
| 前端 `tests/` 266 + `scripts/` 381 | 全绿 |
| 人力域 lint（含 `no-undef`，CI 门禁同款） | 零错误 |
| `npm run build` | 成功 |
| ruff / black（全部改动文件） | 干净 |
| 构建产物核验 | `HumanResources-*.js` 里 `loadEmployees` **0 命中**；`ShopAssignment-*.js` 里 `supervisor` 与「主管/操作员」**0 命中** |
| 生产数据（只读） | 归属表 0 行、绩效快照表 0 行、`role` 列可空 ⇒ **删列零数据损失** |

### 7.5 仍未闭环（业务动作，非代码）

1. **给每个员工挂职位**：生产 11 名员工仅 1 人有岗位，不补录则页面层级多为「（未设岗位）」。
2. **按新形态重配归属**：一行一人一比例，合计 ≤100%（你的 A 店示例 35% 合法）。
3. **发版**：建议 v7.40.0；含 1 个删列迁移 ⇒ 需带降级脚本，回滚 = 重部署 v7.39.0 + 执行降级。
