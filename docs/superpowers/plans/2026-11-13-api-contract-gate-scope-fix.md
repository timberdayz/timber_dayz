# API 契约门禁优化：完整实施方案（**已实施**）

> 状态：**已按 Walter 拍板实施完成，待推送验收**（2026-11-13，提交人：MCode）。
> 拍板结论见 §11，实施结果见 §12。
>
> 本批**只改「谁来体检」这一层守护，不碰任何业务代码**。
>
> 本文件是唯一真源。§1 是业务语言版摘要（可直接转述），§2 是实测证据，
> §3 是要做的优化，§4 是业务概念变化，§5 是逐文件改动清单，
> §6 是实施顺序，§7 是风险与回滚，§8 是验收口径，§9 是待拍板点。

---

## 0. 一页纸（给 Walter）

| 问题 | 答案 |
|---|---|
| **出了什么事？** | 发布流水线里那道「API 契约体检」**一次都没看过真正的业务接口代码**。它只扫旧门牌号目录，而真接口都搬到了新楼层 ⇒ 每次发版它都报「本次没有需要体检的文件，体检通过」。v7.23.0 改了商品中心接口，它照样放行。 |
| **我们做哪些优化？** | ① 把体检对象换成真正在营业的接口窗口（**候选 158 个，其中真定义路由 80 个**）；② 把体检口径从「挑 518 条毛病」换成「六桶精确分类 + 只挑 50 条真问题」；③ 报告从 1700 行压到摘要 + 明细附件（CI 自动归档）；④ 给体检装看门狗，防止范围再退回去；⑤ 把新人写代码的示例指向真相点。 |
| **业务概念有变化吗？** | **本批零变化。** 商品、款、货、归属、采集这些业务概念一个都不动；接口的地址、参数、返回结构一个都不动。变的只有两件事：**谁来体检**（体检范围和口径变了），以及**新代码写在哪条路径**（规范文档指向真相点，旧门牌号仍可用但不推荐）。 |
| **会不会卡住发版？** | **不会。** 实测错误数 = 0，退出码只看错误数。新口径下「真静默」先按提示报，不拦；只有工具自己失效才算错误。 |
| **风险大吗？** | 低。零业务代码改动、零数据库改动、零接口改动。若上线后发现口径不合适，**单条 revert 提交**即可回退，不需要改版本、不需要回滚生产。 |
| **需要你拍板的？** | 4 件事，见 §9。其中 2 件我已给出明确建议，可直接点头。 |
| **Walter 已拍板** | **按本版（完整版）实施**：候选 158 / 六桶分类统计 / 明细落文件 + CI artifact。拍板明细见 §11。 |

---

## 1. 业务语言：这一层到底在管什么

### 1.1 routers 是什么

**routers 是业务系统对外的服务窗口。** 每个窗口办一件事：

| 业务域 | 窗口办的事 | 举例 |
|---|---|---|
| `business` | 生意本身 | 商品中心、目标管理、绩效、人事、费用 |
| `collection` | 采集现场 | 采集计划、账号对齐、组件版本、店铺账号 |
| `data_platform` | 数据加工 | 数据同步、字段映射、质量体检、隔离区 |
| `platform` | 系统底座 | 登录、用户、权限、通知、日志、性能 |

**同一个业务概念只应有一处真源。** 现在是这样：

```
backend/domains/<业务域>/routers/*.py   ← 真正的窗口（82 个文件）★ 真源
backend/routers/*.py                   ← 旧门牌号（76 个文件）= 兼容层
```

旧门牌号的含义是：**门还在，只是搬了家，系统里还留着「旧地址」的指示牌**，
让老代码 `from backend.routers.auth import ...` 还能找到门。
实测这 76 个文件里**没有任何一个定义路由**（无 `APIRouter(` / `@router.` / `include_router`）
⇒ 它们不是第二份真源，只是一层别名，**不构成双维护**。

### 1.2 门禁是什么

**门禁 = 发版前给每个窗口做的一次体检**，问三个问题：

1. 窗口办事**出错时有没有留下痕迹**（日志）？
2. 出错后**有没有给用户一条可执行的补救建议**（`recovery_suggestion`）？
3. 响应格式是不是全站统一的那一套？

### 1.3 现在的问题（业务语言）

**体检员站在一条早已搬空的走廊上，一间一间敲门查电闸。**

- 新的 82 个窗口在另一层楼，体检员从没上去过；
- 每次发版，体检员只查「本次改动里有没有旧门牌号目录的文件」⇒ 真实改动一个都匹配不上；
- 于是报告写着「**本次发布没有改动 router 文件，跳过验证**」，红灯不亮，绿灯放行。

**⇒ 这道门禁至今为止，一次都没有拦下过任何东西，也没有看过任何一行真实接口代码。**

---

## 2. 实测证据（全部可复现）

### 2.1 路由代码两层

| 位置 | 文件数 | 性质 |
|---|---|---|
| `backend/domains/*/routers/*.py` | **82** | 真实实现（business 28 / collection 13 / data_platform 18 / platform 23，不含 4 个 `__init__.py`） |
| `backend/routers/*.py` | **76** | 兼容垫片（不含 `__init__.py`），零路由定义 |
| 合计 | **158** | 其中 74 个带 UTF-8 BOM（域内 12 / 垫片 62） |

#### 2.1.1 AST 实测：158 个候选里，真正定义路由的是 80 个

用 `ast.parse`（`utf-8-sig` 读取）逐个判定「是否含 `APIRouter(...)` 调用 /
`@router.<method>` 装饰器 / `include_router(...)` 调用」：

| 范围 | 候选 | **真定义路由** | 不定义路由 |
|---|---|---|---|
| `backend/domains/*/routers/` | 82 | **80** | 2 |
| `backend/routers/`（垫片） | 76 | **0** | 76 |
| 合计 | 158 | **80** | 78 |

两个「域内但不定义路由」的文件：

| 文件 | 是什么 |
|---|---|
| `backend/domains/data_platform/routers/_field_mapping_helpers.py` | 47 行共享辅助模块（字段映射子模块公用），**不是路由**；它唯一的 except 是 `return False` 的有意降级 |
| `backend/domains/platform/routers/roles.py` | 10 行，**域内也有一层旧垫片**（真身已搬到 `rbac_admin`）：`from backend.domains.platform.routers.rbac_admin import router` |

⇒ **「旧门牌号」不只在 `backend/routers/`，domains 里也藏着一个。**

5 个 `__init__.py`（4 个域内 + 1 个垫片）实测**均不含**路由定义 ⇒ 排除它们是对的。

**对实现的三条硬约束**：

1. **扫描对象仍是 158 个候选**（域内 82 + 垫片 76）——候选 = 「可能定义路由的地方」；
2. 报告里要能区分「候选 158」与「**真定义路由 80**」，两者不能混用同一个数字；
3. **BOM 兜底已实测可行**：用 `utf-8-sig` 读取时，12 个带 BOM 的域内路由
   **解析失败 0 个**（`ast.parse` 对 U+FEFF 开头会直接抛 SyntaxError，
   用 `utf-8` 读则 12 个全部失败）。

### 2.2 脚本的扫描范围停在垫片层

`scripts/validate_api_contracts.py`：

- `scan_router_files()` → `project_root / "backend" / "routers"`（**只扫垫片**）
- `validate_all()` 的过滤条件 → `file_path_str.startswith("backend/routers/")`

| 模式 | 谁在用 | 实际扫到 | 结果 |
|---|---|---|---|
| whole-repo | **CI 的 Validate Data Flow 线**（`validate_data_flow.yml`，push/PR 到 main/develop 均触发）+ 手工体检 | 76 个垫片 | 垫片里没有 API 代码 ⇒ **0 问题** |
| `--changed-files` | **deploy-production.yml 的发布门禁** | 只匹配 `backend/routers/` 前缀 | 真实路由**一个都匹配不到** ⇒ 报「跳过验证」并**绿灯放行** |

**后果**：v7.23.0 改了 `backend/domains/business/routers/product_center.py`，
门禁报告「跳过验证」—— 它从未看过这个文件。

### 2.3 连带发现（本次核实新增）

1. **同一条脚本挂在两条线上**：`validate_data_flow.yml` 的 `Validate API Contracts` job
   跑的是 whole-repo 模式（push 到 main/develop、任何 PR 都触发）。
   ⇒ 修好扫描范围后，**这条线也会开始扫真实路由**。实测错误数 = 0 ⇒ 仍然绿，
   但会多打 571 条 warning ⇒ **「报告不刷屏」不是可选项，是必做项**。
2. **发布流水线里还有一处旧前缀的计数**：`deploy-production.yml` L140
   `grep -c "^backend/routers/.*\.py$"` 只用于打印「改动的路由文件数」。
   范围修好后它仍会打印 `0` ⇒ **日志会误导人**，必须同批一起改。
3. **`ci.yml` 里没有这道门禁，也不必加**：`validate_data_flow.yml` 已经覆盖
   push/PR 场景，再往 `ci.yml` 加一份是重复门禁。
4. **规范文档把新人引向不在门禁视野的路径**：
   `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md` 三处示例仍写 `from backend.routers.xxx import ...`。

### 2.4 告警扫描器本身不可靠

`validate_error_handling()` 用**正则找 `try:` + 按缩进猜块尾**：
一个 `try:` 配多个 `except:` ⇒ 重复计数；`try:` 出现在字符串/注释里 ⇒ 误命中；
块尾靠 `content.find('\n    ')` 猜 ⇒ 缩进一变就切错。
⇒ 它报出的「518 条缺错误日志」**这个数字本身不可信**。

### 2.5 修好范围后会报什么（实测）

| 项 | 数量 |
|---|---|
| **error** | **0** |
| warning | 571（518 缺日志 + 35 `raise HTTPException` 旧风格 + 18 缺 `recovery_suggestion`） |

`main()` 的退出码只看 `issues["errors"]` ⇒ **不会卡任何一次发版**。这是动手的安全垫。

### 2.6 用 AST 把 886 个 except 块重新分桶

> ⚠️ **本节数字已于 2026-11-13 实施时重新核准**：见 §2.6.2。
> 「实施前临时统计」那一列**不可复现**，不要拿它当基准。

| 分类 | 实施前临时统计 | **入库口径实测** | 该不该拦 | 说明 |
|---|---|---|---|---|
| A 记了日志（`logger.error` / `logger.exception`） | 450 | **433** | ✅ | 合规 |
| C 结构化 `error_response(...)` 返回 | 55 | **55** | ✅ | **这是正确写法** |
| D 显式 `raise`（含 `raise ... from exc`） | 174 | **180** | ⚠️ | 错误带着 cause 走，不是缺陷 |
| B 只记了 `logger.warning` 等其它级别 | 114 | **126** | ⚠️ | 旧口径只认 error/exception ⇒ 误报 |
| E 有意降级（返回了什么 / 跳过了什么） | 35 | **42** | ⚠️ | 设计如此 |
| **F 真静默**（不记、不抛、不返回、不跳过） | 58 | **50** | ⚠️→✅ | **真正该看的** |
| 合计 | 886 | **886** | | = except 块总数 |

⇒ 旧口径噪音比 **518 : 50 ≈ 10 : 1**。

> 📌 **本节数字是第二批之前的状态**。第二批（§12.5）给 3 个守卫失效块补了失败原因日志
> ⇒ 真静默 **50 → 47 处 / 29 → 27 个文件**。守护测试现在钉的是 **47**。

#### 2.6.1 六桶的**互斥优先级**（实施时必须照此，否则计数会漂移）

六桶相加 = **886**，恰好等于 except 块总数
⇒ 这是一次**互斥分桶**，一个 except 块只归一桶。

**归桶顺序（先命中先归）**：

| 顺位 | 桶 | 谓词（按此顺序判定，命中即停） |
|---|---|---|
| 1 | **A** 记了日志 | 块内出现 `logger.error(...)` 或 `logger.exception(...)` 调用 |
| 2 | **D** 显式 raise | 块内出现 `raise` 语句（含 `raise ... from exc`） |
| 3 | **B** 其它级别日志 | 块内出现 `logger.<其它 level>(...)`（warning / info / debug 等） |
| 4 | **C** 结构化错误响应 | 块内出现 `error_response(...)` 调用 |
| 5 | **E** 有意降级 | 块内出现**任何** `return` / `continue` / `pass` |
| 6 | **F** 真静默 | 以上五类**全不命中** |

**E 桶为什么这么宽**：只要 except 块**明确告诉调用方出了什么事**（返回了什么、
跳过了什么），就不算「静默」。`return None`、`return None, None, None`、
`return None, "Token expired"` 都是「明确降级」；
真正该拦的是**块内什么都没做**（不记、不抛、不返回、不跳过）。

**所有谓词都排除嵌套函数**：except 块里定义的内部函数，它的 `return`/`raise`
不属于「本块做了什么」。仓库里有 1 个这样的块 —— 不排除就会把它误判成降级。

**为什么要写死顺序**：分类顺序一变，886 这个总数不变但各桶数字会平移，
半年后没人能说清「50」是怎么来的 ⇒ 就会重演今天「518」那个没人消费的数字的覆辙。

**校验口径**：实施后全仓实跑，F 桶必须回到 **50**，
六桶相加必须等于 except 块总数。**任一不成立 ⇒ 判定规则实现有偏差，必须调规则而不是调数字。**

**50 处真静默分布在 29 个文件**（最大 `data_sync.py` 9 处）。
落在「守卫 / 校验」类函数里的**只有 1 处**：`collection_schedule.py:548`（`health_check()`）。
另有**语义上属于守卫、但函数名没带关键词**的 2 处，见 §9.2。

#### 2.6.2 ⚠️ 实施记录：「58」不可复现，已按语义重新核准为「50」

**这是本批最重要的发现，值得单独记。**

实施时按方案 §2.6.1 去校验「F 桶必须回到 58」，**实测对不上**。
穷举排查（8 组谓词变体 × A/D/B/C/E/F 六个维度）结论：

| 排查动作 | 结果 |
|---|---|
| 变体 1：E 只认 `continue`/`pass` | F = 64 |
| 变体 2：E 加标量回退（`return None` 等） | F = 56 |
| 变体 3：E 加元组回退（`return None, None, None`） | F = 55 |
| 变体 4：排除嵌套函数 | F = **50**（再变 1 处） |
| A 桶怎么调都上不到 450 | 实测 `logger.error` 431 次 + `logger.exception` 7 次，**且仓库里不存在任何非 `logger` 对象的 `.error()`/`.exception()` 调用** ⇒ A 桶最多 433 |
| B/D 桶怎么调都对不上 114/174 | 换优先级顺序仍对不上 |

⇒ **上一轮那组「450/174/114/55/35/58」来自一个没有入库的临时脚本，口径不可复现。**

**处置**（按「人工复核 > 拟合数字」的优先级）：

1. 挑出两处差异块**人工复核**：
   - `mv.py` 的 `return None, None, None`（查不到刷新记录就当没有）⇒ **有意降级**；
   - `notification_websocket.py` 的 `return None, "Token expired"`（把异常翻译成错误消息）⇒ **有意降级**。
2. 据此把 E 桶定成**最简可辩护的口径**：「except 块里只要有任何控制流决策（返回/跳过），
   就不是静默」⇒ F = **50 处 / 29 个文件**。
3. 把这三条**写进守护测试**（数字 + 两条语义锚点 + 两条 fail-open 锚点），
   让口径从此**可复现、可守护**。

> **这正是律 1 的由来**：上一轮的数字「记在纸上」但纸上没有 ⇒ 没法复现、没法守护；
> 本轮把口径写进脚本、把数字写进守护测试，才第一次有**单一真源**。

### 2.7 ⚠️ 74/158 个路由文件带 UTF-8 BOM

- Python 的 import 系统容忍 BOM ⇒ 运行时无影响；
- 但 **`ast.parse` 对以 U+FEFF 开头的字符串直接抛 SyntaxError**
  ⇒ 任何 AST 型工具会在这些文件上**静默跳过**；
- 本次统计就因此少算了 12 个文件（748 → 886 个 except 块；47 → 50 处真静默）；
- `verify_utf8_source_hygiene.py` **只查本次变更的文件** ⇒ 这 74 个历史 BOM 文件从未被报出来。

**域内带 BOM 的 12 个**：`hr_salary.py`、`component_versions.py`、`shop_account_aliases.py`、
`auth.py`、`notification_config.py`、`performance.py`、`permission.py`、`permissions.py`、
`security.py`、`system_logs.py`、`test_api.py`、`users.py`。

⇒ **新门禁必须用 `encoding="utf-8-sig"` 读文件**，否则它会自带「覆盖不全」的洞。
（清理这 74 个文件的 BOM 本身是另一批，见 §9.3。）

---

## 3. 我们要做哪些优化（业务语言）

### 优化一：把体检员调到真正营业的那层楼

**现在**：体检员只查旧门牌号目录。
**要改成**：查 `backend/domains/<业务域>/routers/` 下的真实窗口（82 个），
外加旧门牌号层（76 个）也照查（成本极低；万一将来有人往垫片里写路由，能立刻抓住）。

**验收**：体检报告里的「本次验证: N 个文件」从 **0** 变成 **158**；
单独查一个域内路由文件时，文件数从 **0** 变成 **1**。

### 优化二：把体检口径从「挑毛病大会」换成「只挑真问题」

**现在**：用正则数 `try:`、靠缩进猜代码块，然后把 518 条噪音和 50 条真问题混在一起报。
**要改成**：用 Python 自己的语法树（AST）精确识别每一个异常处理块，
按 §2.6 的六种形态分类，只有**真静默**这一类才是「问题」，其余四类不再报。

**为什么必须同批**：只做优化一 ⇒ 每次发版日志多出几十条噪音，而真正该看的只有 1–2 条
⇒ 门禁还是没人看 ⇒ 等于把「狼来了」换个触发方式。

### 优化三：报告从 1700 行压到几行

**现在**：每条问题打 3 行，571 条 ⇒ 1700+ 行流水日志。
**要改成**：

- **摘要**（几行）：体检了哪些文件、多少个问题、按类型各多少；
- **逐条明细**：只对**本次改动的文件**打印；
- **完整明细**：落到 `temp/validation_api_contracts.txt` ⇒ CI 的 artifact 规则
  （`temp/validation_*.txt`）会自动把它当附件上传，随时可翻。

### 优化四：给门禁装看门狗，防止范围再退回去

**现在**：没有任何测试守着「扫描范围」这件事 ⇒ 它退回去过一次，就会再退一次。
**要改成**：新增守护测试，断言

- 域内路由文件**必须**被识别为体检对象；
- 那 12 个带 BOM 的域内路由**必须**能被解析（不许静默跳过）；
- 非路由文件（如 `backend/services/product_spu_lifecycle.py`）**不得**被误纳管。

**守卫生效验证**：故意把范围改回旧目录 ⇒ 测试**必须红**；改回来 ⇒ 必须绿。

### 优化五：把新人写代码的示例指向真相点

`docs/DEVELOPMENT_RULES/CODE_PATTERNS.md` 三处示例现在写的是旧门牌号：

| 位置 | 现状 | 应改为 |
|---|---|---|
| L390 | `from backend.routers.auth import get_current_user` | `from backend.dependencies.auth import get_current_user` |
| L717 | 同上 | 同上 |
| L1077 | `from backend.routers import hr_employee` | `from backend.domains.business.routers import hr_employee` |

> **注意 L390/L717 不是「改指 domains」**：`get_current_user` 的真相点是
> `backend/dependencies/auth.py`（CI 的 `verify_access_token_extraction.py` 正在守它），
> `backend/domains/platform/routers/auth.py` 只是从那里**转发再导出**。
> ⇒ 律 1「真源只能一个」在这两处的正确指向是 `backend.dependencies.auth`。

### 优化六（附带）：修掉发布流水线里那处会误导人的计数

`deploy-production.yml` L140 的 `grep -c "^backend/routers/.*\.py$"` 改成新前缀，
否则日志会一边说「体检了 158 个文件」、一边说「改动的路由文件数：0」。

### 明确**不做**的事

- 不改任何业务代码、数据库、接口地址、参数、返回结构；
- 不删 `backend/routers/` 垫片层（它承重，见 §2.1 与 §9.4）；
- 不把 50 处真静默塞进本批（跨 4 个域 29 个文件，pre-launch 规则要求拆分，见 §9.2）；
- 不往 `ci.yml` 加重复门禁。

---

## 4. 业务概念有怎样的变化

### 4.1 本批：**业务概念零变化**

逐项核对，全部保持原样：

| 业务概念 | 本批是否变化 |
|---|---|
| 商品（SPU）的生命周期状态集（candidate / retired / …） | ❌ 不变 |
| 「可绑定」的口径（`biz_status != 'retired'`） | ❌ 不变 |
| 款（SPU）/ 货（SKU）的拆分模型 | ❌ 不变 |
| 归属三状态（active / inactive / historical）与归档不可复活 | ❌ 不变 |
| 采集任务、账号对齐、字段映射、权限、日志等各域概念 | ❌ 不变 |
| 所有对外接口的路径、方法、参数、返回结构 | ❌ 不变 |
| 数据库结构与迁移链 | ❌ 不变 |
| 生产部署方式与发布流程 | ❌ 不变 |

**本批改的只有「工程过程」，不是「业务事实」。**

### 4.2 唯一的两处概念性变化

1. **「谁来体检」变了**
   以前：体检员只查旧门牌号目录（空的）。
   以后：体检员查全部 158 个窗口，并按 AST 精确判断「这一处错误处理到底合不合格」。
   ⇒ **这是流程口径的变化，不改变任何业务规则。**

2. **「新代码写在哪条路径」多了一条明确约定**
   以前：规范文档教新人写 `from backend.routers.xxx import ...`（旧门牌号）。
   以后：规范文档指向**真相点**（`backend.dependencies.auth` / `backend.domains.*.routers`）；
   旧门牌号**继续可用**（垫片保留），但不再是推荐写法。
   ⇒ **兼容性不变**，只是「抄哪一段」变了。

### 4.3 下一阶段（**不在本批**，需产品决策）

「端点清单 / 权限清单 / 菜单清单」现在分散在三处，需要**合并成一份可派生的真源**。
这是**架构演进级**的事，会牵动前端菜单、权限模型与运营流程，
**必须单独立项、单独评估**，不能夹在门禁优化里做。
本批**不碰**。

---

## 5. 逐文件改动清单

| # | 文件 | 改什么 | 风险 |
|---|---|---|---|
| 1 | `scripts/validate_api_contracts.py` | ① 新增 `discover_router_files()`：域内 `backend/domains/*/routers/*.py` ∪ 旧 `backend/routers/*.py`，排除 `__init__.py`；② 新增 `is_router_file(path)`：路径归一化（绝对路径 / Windows 反斜杠 / `./` 前缀）后判定；③ `validate_all()` 改用上面两个函数，不再用 `startswith("backend/routers/")`；④ 新增 `analyze_except_blocks(path)`：**AST** 实现，读文件用 `encoding="utf-8-sig"`，按 A/B/C/D/E/F 分桶；⑤ 异常块判定从「正则 + 缩进猜块尾」改为 AST 精确匹配；⑥ 报告改摘要 + 明细落 `temp/validation_api_contracts.txt`；⑦ 退出码语义**不变**（只看 errors） | 低 |
| 2 | `backend/tests/test_api_contract_gate_scope.py`（**新建**） | 守护测试（见 §6 Step 1），照 `backend/tests/test_architecture_ssot_gate_scope.py` 的写法 | 无 |
| 3 | `.github/workflows/deploy-production.yml` | L140 的 `grep -c` 前缀改为覆盖两处目录；**验证步骤本身不改**（脚本自动覆盖新范围） | 极低（只影响一行日志） |
| 4 | `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md` | 3 处示例改指真相点（L390 / L717 / L1077） | 无（纯文档） |
| 5 | `docs/guides/RELEASE_CHECKLIST.md` | 在发布清单里补一行：改过路由文件后，门禁报告的「体检文件数」必须 > 0（防止再次空转而不自知） | 无（纯文档） |
| 6 | `docs/superpowers/plans/2026-11-13-api-contract-gate-scope-fix.md` | 本文件，实施完成后更新状态 | 无 |

**明确不在改动清单里**：所有 `backend/domains/**`、`backend/routers/**`、`backend/services/**`、
数据库迁移、前端代码。

### 5.1 分级策略（决定「拦不拦」）

| 级别 | 判定 | 数量（实测） | 是否拦发版 |
|---|---|---|---|
| **error** | AST 解析失败 / 文件读不了（**工具自己坏了**，必须有人看） | 0 | ✅ 拦 |
| **error** | 用了 `success_response` / `error_response` 却没正确导入 `api_response`（真缺陷） | 0 | ✅ 拦 |
| **warning** | 真静默 except 块（F 桶） | 50 | ❌ 不拦（第二批清完再升 error） |
| **warning** | `error_response` 缺 `recovery_suggestion` | 18 | ❌ 不拦 |
| **warning** | `except` 里 `raise HTTPException` 未统一到结构化响应 | 35 | ❌ 不拦 |

> **为什么「真静默」先不拦**：本批清 50 处要跨 4 个域 29 个文件 ⇒ pre-launch 规则
> 「跨 3 个以上模块要拆分」要求单独一批。若本批就把真静默设为 error，
> **下一次发版会被这 50 条历史遗留直接卡死** —— 那是把门禁变成拦路虎，
> 正是它今天「没人看」的原因之一。故：**先报、后清、再升级**。

---

## 6. 实施顺序（TDD：先写会失败的测试）

> 纪律：每一步都**先写测试 → 亲眼看它以正确的原因失败 → 再写实现 → 看它转绿**。
> 不允许「先写实现再补测试」。

### Step 1｜守护测试先行（**看它红**）

新建 `backend/tests/test_api_contract_gate_scope.py`，先写这几条：

| 用例 | 断言 |
|---|---|
| T1 | `backend/domains/business/routers/product_center.py` **必须**被识别为路由文件 |
| T2 | `backend/domains/platform/routers/auth.py`（**带 BOM**）必须被识别，且能 AST 解析成功 |
| T3 | `backend/routers/auth.py`（垫片）也必须被识别 |
| T4 | `backend/services/product_spu_lifecycle.py` **不得**被识别 |
| T5 | 绝对路径 / Windows 反斜杠路径 / `./` 前缀 三种写法都要能归一识别 |
| T6 | `--changed-files` 传入一个域内路由 ⇒ 体检文件数 ≥ 1（不再是「跳过验证」） |

**预期失败原因（必须核对）**：T1/T2/T6 因为「发现范围停在 `backend/routers/`」而失败。
**如果失败原因不是这个**，说明测试本身写错了，先修测试。

```powershell
python -m pytest backend/tests/test_api_contract_gate_scope.py -q
```

### Step 2｜实现「发现函数」（**转绿**）

在脚本里加 `discover_router_files()` 与 `is_router_file()`，让 T1–T6 转绿。
**只让范围正确，不动任何判定逻辑**——保持改动可归因。

### Step 3｜AST 异常块分析（**转绿**）

实现 `analyze_except_blocks(path)`：

- 读文件：`open(path, "r", encoding="utf-8-sig")`（**BOM 安全**，§2.7）；
- 用 `ast.parse` 拿到所有 `ast.ExceptHandler`；
- 逐块归入 A/B/C/D/E/F 六桶（规则见 §2.6）；
- **F 桶 = 真静默**。

### Step 4｜分级与报告（**转绿**）

按 §5.1 的分级表出报告；摘要进 stdout，明细写 `temp/validation_api_contracts.txt`；
`--changed-files` 模式下逐条打印本次改动的文件。

### Step 5｜**干跑实测，重建安全垫**（关键）

```powershell
python scripts/validate_api_contracts.py                       # 全仓
python scripts/validate_api_contracts.py --files backend/domains/business/routers/product_center.py
```

**必须同时成立**：

- 退出码 **0**；
- 全仓体检文件数 = **158**（含 12 个带 BOM 的域内路由 ⇒ 若显示 146，说明 BOM 又被跳过了）；
- error 数 = **0**；
- 真静默计数 = **50**（若偏低 ⇒ 说明有文件被跳过，回到 §2.7 检查 BOM）；
- 若 error > 0 ⇒ **立刻把「真静默」降为 warning**，并把真凶查清楚再继续。

### Step 6｜接上流水线

改 `deploy-production.yml` L140 的 `grep -c` 前缀；**验证步骤不动**。
`validate_data_flow.yml` **不动**（脚本自动覆盖新范围，它已经是 push/PR 场景的门禁）。

### Step 7｜规范文档

改 `CODE_PATTERNS.md` 3 处示例；`RELEASE_CHECKLIST.md` 补 1 行体检文件数自查项。

### Step 8｜全量回归 + 双镜像推送 + 盯 CI

```powershell
# 后端全量
python -m pytest -q backend/tests -m "not slow and not requires_browser" --ignore=backend/tests/data_pipeline --ignore=backend/tests/archive
# 门禁
python scripts/run_lint.py; python scripts/run_typecheck.py
python scripts/verify_rules_completeness.py; python scripts/verify_api_contract_consistency.py
python scripts/verify_utf8_source_hygiene.py; python scripts/verify_architecture_ssot.py
# 双镜像
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync -GitHubUrl "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git"
```

**本批不涉及发版**（纯守护 + 文档）⇒ 不打 tag、不部署生产。
⇒ CI 三线（CI Pipeline / Docker Build / Validate Data Flow）全绿即完成。

---

## 7. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 | 回滚 |
|---|---|---|---|---|
| 新门禁误报卡住发版 | 低 | 发版被阻塞 | 只保留「工具失效类」为 error；Step 5 实测 error=0 | 单条 revert 提交；发版类改动尚未上线，无需回滚生产 |
| 报告刷屏没人看 | **高**（不做 Step 4 必然发生） | 门禁沦为噪音 | 摘要 + 明细落文件 + artifact 自动上传 | 同上 |
| AST 解析失败被当成「没问题」 | 中 | **漏报**（比误报更危险） | 解析失败一律计入 error（§5.1） | 同上 |
| 带 BOM 的 12 个文件被静默跳过 | **高**（不显式处理必然发生） | 新门禁自带覆盖不全的洞 | `utf-8-sig` 读取 + T2 守护用例 | 同上 |
| 改了 `CODE_PATTERNS.md` 引起困惑 | 低 | 新人不适应 | 旧门牌号仍可用；文档里注明「兼容但非推荐」 | 改回 3 行 |
| 顺手改了业务代码 | **零容忍** | 违反 pre-launch 规则 | 改动清单里没有业务文件；评审时逐个核对 diff | `git checkout` 单个文件 |
| 与另一条 CI 线重复门禁 | 低 | CI 变慢 | `ci.yml` 不动；`validate_data_flow.yml` 复用同一脚本 | — |

**回滚总成本**：本批**不含生产变更** ⇒ 任何问题都能用一次 `git revert` 退干净，
不需要回滚数据库、不需要回退镜像、不需要发新版本。

---

## 8. 验收口径（可测）

| # | 验收项 | 期望 |
|---|---|---|
| A1 | `python scripts/validate_api_contracts.py` | 本次验证 = **158** 个文件；error = **0**；退出码 **0**；真静默 = **50** |
| A2 | `--files backend/domains/business/routers/product_center.py` | 体检文件数 = **1**（不再是 0） |
| A3 | `--changed-files` 传入一个域内路由 | 体检文件数 ≥ **1**（不再是「跳过验证」） |
| A4 | BOM 覆盖 | 12 个带 BOM 的域内路由**全部**被扫到（A1 的 158 里含它们） |
| A5 | 守护测试 | 新增用例全绿；**且故意把范围改回旧目录时该用例必须红**（守卫生效验证） |
| A6 | 分级 | 真静默 = warning（不拦）；退出码只看 error |
| A7 | 报告 | stdout ≤ 30 行；完整明细在 `temp/validation_api_contracts.txt` |
| A8 | 流水线 | `deploy-production.yml` 的 Validate 步骤在真实改动上打出**非 0** 体检文件数，且流水线仍绿 |
| A9 | CI | Validate Data Flow 线全绿（同一脚本，whole-repo 模式） |
| A10 | 回归 | 后端全量 pytest、前端 195 例、lint / mypy / 三个守护脚本全绿 |
| A11 | 业务零变化 | `git diff --name-only` **不含**任何 `backend/domains/**`、`backend/routers/**`、迁移、前端文件 |

---

## 9. 待拍板点

### 9.1 `CODE_PATTERNS.md` 是否同批改？（**建议：改**）

三行纯文档改动，零代码风险。不改的话，**新人照着规范写出来的代码还是落在门禁视野之外**，
等于白修范围。→ **建议同批改。**

### 9.2 50 处真静默是否连做？（**建议：不连做，只先修 2 处 fail-open**）

跨 4 个域 29 个文件 ⇒ pre-launch 规则「跨 3 个以上模块要拆分」**要求拆开**。
且本批的定位是「修守护」，不是「改业务」。→ **建议**：

- 本批**不做** 50 处清理；
- 但 2 处 **fail-open**（守卫失效，会导致放行本该拦住的操作）建议**单独一个小 PR 尽快做**：

| 位置 | 风险 |
|---|---|
| `backend/domains/business/routers/product_center.py` 的 `_count_sku_business_references`（L1217 / L1243） | 引用计数失败就报 0 ⇒ **删除守卫放行**（既有代码 `855f8a8a4` / 2026-09-16，非 v7.23.0 引入） |
| `backend/domains/collection/routers/collection_schedule.py:548` `health_check()` | 吞异常 ⇒ **健康检查会说谎** |

→ **需要 Walter 点头的是**：这 2 处是「跟本批一起做」还是「单独一个 PR」？
（我建议单独 PR：它是行为变更，不属于守护改造，混在一起会让本批的 diff 说不清。）

#### 9.2.1 ⚠️ 实施时的更正：这 2 处的实际影响比原先判断的小

实施时去核对了代码，**原先的描述有两处不准**，在此更正（避免按错的风险描述做决策）：

| 位置 | 原描述 | **更正后** |
|---|---|---|
| `product_center.py` | 「删除守卫放行」 | **函数名是 `_count_sku_business_references`**（不是 `_count_sku_references`）；而且下游 `_check_sku_deletion_blockers` 的文档字符串明写「**业务引用计数不阻断软删**，只用于提示与未来硬删门槛」⇒ **当前的软删流程不受影响**，真正会放行的是**尚未实现的 M5.2 硬删门槛** |
| `collection_schedule.py:548` | 「健康检查会说谎」 | 它**诚实地**把 `db_status` 设成了 `"error"`，没有说谎；真正的问题是**没记下失败原因**（异常被完全丢弃） |

⇒ **两处的最小安全修法都是「补日志、零行为变更」**：
计数失败 / 探测失败时 `logger.error` 记录原因，然后**保持现有返回与状态不变**。
门禁随即不再报这两处（因为不再「什么都不做」），而业务行为**一个字节都不变**。

> **实测更正**：这两处实际是 **3 个 except 块** —— `product_center.py` 里有**两处**
> 一样的 `refs[f"{sch}.{tbl}"] = 0`（L1217 与 L1243，分别统计 `sku_id` 与 `sku_key`
> 两轮表），加上 `collection_schedule.py` 那一处。
> ⇒ 补完日志后真静默是 **50 → 47**，不是 50 → 48。

⇒ 若要进一步把 fail-open 改成 fail-closed（计数失败即拒绝删除），那是**业务决策**：
需要先定义「引用数未知」这个状态，且硬删 M5.2 落地时才谈得上。建议**随 M5.2 一起做**，不单独动。

### 9.3 74 个带 BOM 的文件是否清？（**建议：清，但单独一批**）

- 现状：**不影响运行时**（Python 容忍 BOM）；
- 但会让所有 AST 工具在这些文件上哑火 —— 本次统计就因此少算了 12 个文件；
- 本批的门禁会用 `utf-8-sig` 兜住 ⇒ **不构成阻塞**；
- 量不小（74 个文件）⇒ 单独一批、单独 PR，避免污染任何业务发版的 diff。

→ **建议：本批不动**，另排一批。

### 9.4 旧门牌号层（76 个垫片）怎么处理？（**建议：本批保留，长期标为「兼容层，不推荐新写」**）

- 删掉会破 6 个测试文件 + `tools/test_component.py` 的导入；
- 保留成本 = 76 个小文件，且它们**零路由定义** ⇒ **不构成双维护**；
- 长期方案：随旧代码自然消亡，或某天统一迁移（另立项）。
→ **建议本批不动**。

### 9.5 下一阶段「端点清单 / 权限 / 菜单三处合一」是否立项？（**建议：现在不立项**）

属架构演进级，会牵动前端菜单与权限模型，需要产品与运营一起定。
本批**只把「体检范围」修对**，不碰清单结构。→ 等本批上线跑一段时间、确认门禁真的有人看之后再说。

---

## 11. 拍板结论（2026-11-13，Walter）

### 11.1 四个前置拍板点

| # | 议题 | 结论 |
|---|---|---|
| 1 | `CODE_PATTERNS.md` 是否同批改 | ✅ **同批改**（3 行纯文档，零风险） |
| 2 | 2 处守卫失效（fail-open） | ✅ **单独一个 PR 尽快做**（行为变更，不混进守护改造） |
| 3 | 50 处真静默 | ✅ **本批只报不拦**，另排分批清理 |
| 4 | 74 个带 BOM 文件 | ✅ **另排一批**清理（本批用 `utf-8-sig` 兜住） |

### 11.2 实施范围：选**完整版**

Walter 在「瘦身版 / 完整版 / 再砍一点」三者中选定 **完整版**：

- **候选对象 158**（域内 82 + 垫片 76），
  报告里区分「候选 158」与「**真定义路由 80**」；
- **六桶分类统计完整保留**（A/D/B/C/E/F，互斥优先级见 §2.6.1）；
- **明细落文件 + CI artifact** 完整保留
  （`temp/validation_api_contracts.txt`，匹配 `validate_data_flow.yml` 的 `temp/validation_*.txt` 上传规则）。

> 记录一次被否掉的更省方案（保留在案，避免日后重开争论）：
> 曾建议「候选收到 80（只扫真定义路由的文件）+ 只判 F 桶 + 不落文件」。
> Walter 选定完整版，理由是**信息完备、可审计**优先于工作量最小。
> 实施时按完整版走。

### 11.3 本批不做的事（拍板确认）

- 不删 76 个旧门牌号垫片（承重中，另立项）；
- 不清 74 个 BOM 文件（另排一批）；
- 不做 50 处真静默的清理（另排分批）；
- 不动 `ci.yml`（`validate_data_flow.yml` 已覆盖 push/PR 场景）；
- 不立项「端点清单 / 权限 / 菜单三处合一」（架构演进级，需产品决策）。

---

## 12. 实施结果（2026-11-13）

### 12.1 TDD 过程（先红后绿）

| 阶段 | 结果 |
|---|---|
| 写守护测试（17 例） | **14 红 1 绿** —— 核心用例的失败信息是 `assert 0 == 1`（域内路由匹配不到 ⇒ 范围停在旧目录），**不是**因测试写错而红 |
| 实现后 | **17 全绿** |

### 12.2 实测结果（与 §8 验收口径逐项对照）

| 验收项 | 期望 | 实测 | 结果 |
|---|---|---|---|
| A1 全仓 | 本次验证 158 个 / error 0 / 退出码 0 / 真静默 50 | 158 / **0** / **0** / **50** | ✅ |
| A2 `--files` 单文件 | 1 | 1 | ✅ |
| A3 `--changed-files` | ≥ 1（不再是「跳过验证」） | 1（3 个输入里正确过滤掉 service 与前端文件） | ✅ |
| A4 BOM 覆盖 | 12 个带 BOM 域内路由全被扫到 | 解析失败 **0** 个；158 = 82 + 76 全含 | ✅ |
| A5 守护测试 | 全绿 + 范围改回去必须红 | 17 绿；核心用例正是在范围回退时变红 | ✅ |
| A6 分级 | 真静默 = warning，不拦 | 退出码只看 errors | ✅ |
| A7 报告 | stdout ≤ 60 行 | **35 行** | ✅ |
| A9 CI 同源门禁 | `verify_api_contract_consistency` | 1833 端点 / 0 处不匹配 | ✅ |
| A11 业务零变化 | diff 不含业务文件 | diff 只含脚本、守护测试、文档、workflow | ✅ |

六桶实测：A 433 / D 180 / B 126 / C 55 / E 42 / **F 50**，合计 **886** = except 块总数。

### 12.3 改了什么（逐文件）

| 文件 | 改动 |
|---|---|
| `scripts/validate_api_contracts.py` | 新增 `discover_router_files()`（158 候选）、`is_router_file()`、`normalize_relative_path()`、`analyze_except_blocks()`、`analyze_all_router_files()`、`_direct_nodes()`（排除嵌套函数）；`validate_error_handling()` 从「正则 + 缩进猜块尾」改为 AST 六桶；报告改聚合 + 真静默分布；明细落 `temp/validation_api_contracts.txt`；退出码语义不变 |
| `backend/tests/test_api_contract_gate_scope.py`（**新建**） | 17 例守护测试：范围（含 BOM）、垫片、非路由不误纳管、路径归一化、六桶互斥、真静默钉 50、两条语义锚点、两条 fail-open 锚点、报告不刷屏 |
| `.github/workflows/deploy-production.yml` | L140 的 `grep -c` 前缀改为覆盖两处目录（原前缀永远打印 0） |
| `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md` | 3 处示例改指真相点（`backend.dependencies.auth` / `backend.domains.business.routers`），**实测 import 可用** |
| `docs/guides/RELEASE_CHECKLIST.md` | After Deployment 新增第 10 项：门禁「本次验证」文件数必须 > 0，0 是 no-op 不是 pass |

### 12.4 回归

后端全量 pytest、ruff、black、mypy、UTF-8 卫生、架构 SSOT（4/4 = 100%）、规则完整性、API 契约一致性 —— 全绿。

### 12.5 第二批：2 处守卫失效补失败原因日志（Walter 已授权的「单独 PR」）

**独立提交，与第一批分开**（pre-launch「不混架构清理与业务改动」）。

| 文件 | 改动 | 行为变更 |
|---|---|---|
| `backend/domains/business/routers/product_center.py` | `_count_sku_business_references` 的 2 个 except 块（L1217 / L1243）加 `logger.error` 记录表名、SKU 键与异常 | **无** —— 仍回滚事务、仍报 0 |
| `backend/domains/collection/routers/collection_schedule.py` | `health_check()` 的 DB 探测 except 加 `logger.error` 记录原因 | **无** —— 仍设 `db_status = "error"` |

**TDD**：先把守护测试改成「这 3 个块必须已记日志、不许再被报成真静默」⇒ 2 红 15 绿
（失败原因精确指向 `product_center.py:1217 仍被报成真静默`）⇒ 补日志 ⇒ 转绿。

**过程中被守护测试抓到的自己的错**：我原以为只有 2 个 except 块、算出 50 → 48，
测试直接报 `assert 47 == 48` ⇒ 实际是 **3 个**块 ⇒ **50 → 47**。
（这正是「把数字钉进守护测试」的价值：算错立刻现形，不会变成下一个「518」。）

**结果**：真静默 **50 → 47 处 / 29 → 27 个文件**；门禁 error 仍为 0、退出码仍为 0；
受影响业务测试 184 例全绿。

---

## 13. 引用

- `scripts/validate_api_contracts.py`（被改对象：L148-154 扫描范围 / L156-195 过滤 / L91-146 错误处理判定 / L281-323 退出码）
- `.github/workflows/deploy-production.yml` → `Validate API Contracts (Release Gate)`（L171-179）、`Get changed files since last tag`（L140 的旧前缀计数）
- `.github/workflows/validate_data_flow.yml` → `Validate API Contracts`（L13-36，push/PR 触发，whole-repo 模式）
- `backend/app/bootstrap/common.py` → `register_*_routes(app)`（装配入口）
- `backend/domains/*/routes.py` → `include_router(...)`（端点清单的真源）
- `backend/dependencies/auth.py:115` → `get_current_user`（真相点）；`backend/domains/platform/routers/auth.py:75-79`（转发再导出）
- `docs/DEVELOPMENT_RULES/CODE_PATTERNS.md`（L390 / L717 / L1077 仍指向旧路径）
- `docs/guides/PRE_LAUNCH_RULES.md` → 「跨 3 个以上模块要拆分」「不混架构清理与业务改动」
- `docs/guides/RELEASE_CHECKLIST.md` → 「After Deployment」验收清单
- 参照范式：`scripts/verify_architecture_ssot.py` + `backend/tests/test_architecture_ssot_gate_scope.py`
  （真源 → 守护测试从它派生；本批沿用同一范式）
