# Changelog - 西虹 ERP 系统

## [v7.29.1] - 2026-11-14 - 补齐生产镜像缺失的模板决策资产与治理脚本

> **纯镜像构建改动，无业务代码变更、无数据库变更、无数据迁移。**
> 回退 = 重新部署上一版镜像（`v7.29.0`）即可，数据库侧无需任何动作。

### 一、缺陷：白名单式 COPY 让治理工具**静默缺席**

`Dockerfile.backend` 对 `scripts/` 采用**白名单式 COPY**（逐个 `COPY scripts/xxx.py`，
避免整体复制让镜像膨胀）。v7.29.0 新增的脚本与决策资产目录**没有登记进去** ⇒

```
$ docker exec xihong_erp_backend_api ls -d /app/templates
ls: cannot access '/app/templates': No such file or directory
```

⇒ **业务不受影响**（判定逻辑在 `backend/` 里，照常工作），
但批次 3 的核心价值——「模板决策资产进 Git + 生产侧差异守卫」——**在生产根本跑不起来**。
更危险的是：线上会以为「守卫已经上线了」，实际连脚本都不在镜像里。

| 缺失项 | 用途 | 生产侧后果 |
|---|---|---|
| `templates/` | 27 份维度声明式定义（进 Git 的决策资产） | `--check` 差异守卫无输入 |
| `scripts/template_definitions.py` | 定义格式 SSOT | 同上 |
| `scripts/apply_template_definitions.py` | 差异守卫 + 投影 | 同上 |
| `scripts/export_template_definitions.py` | 从库反向导出 | 无法在生产侧导出 |
| `scripts/replay_drift_caliber.py` | 只读回放两套口径 | 口径问题现场无法自查 |
| `scripts/template_release_sla_metric.py` | 发布→重估闭环指标 | **闭环指标在生产算不出来** |

### 二、修复

1. `Dockerfile.backend` 补 `COPY templates /app/templates` 与 5 个新脚本的 COPY 行
   （`scripts/template_definitions.py` 的 `REPO_ROOT = Path(__file__).resolve().parents[1]`
   ⇒ 镜像内 `/app/scripts/x.py` 正好解析到 `/app/templates/definitions`）。
2. `Dockerfile.collection` **不动**：采集镜像不跑治理脚本，也不需要决策资产。

### 三、守护：把「加了脚本就得同步改 Dockerfile」变成流水线里会红的事实

新增 2 条守护（`backend/tests/data_pipeline/test_template_definitions_guardrails.py`）：

- `test_backend_image_ships_template_decision_assets`
  —— 断言 Dockerfile 里必须有 `COPY templates /app/templates` 与 5 个脚本的 COPY 行；
- `test_dockerignore_does_not_exclude_template_definitions`
  —— 断言 `.dockerignore` 不会把决策资产挡在镜像外。

> 没有这两条，下一个人加运维脚本时还会再漏一次 —— 而且**流水线照样全绿**。

### 四、验证证据

| 项 | 结果 |
|---|---|
| 新增守护测试 | 18 passed（原 16 + 新 2） |
| 宽回归 | 见下方 v7.29.0 与本次发布流水线结论 |
| 生产镜像 | v7.29.1 上线后 `ls /app/templates/definitions` ⇒ 27 份定义在位；`--check` 27/27 一致、退出码 0 |

### 五、已知副作用

1. **镜像层多约 0.5 MB**（27 份 JSON 定义，513.8 KB，无 BOM 全 LF）。
2. **本机开发库曾因验证脚本的删除条件写宽而误删历史模板版本** ⇒ 已用当日 14:23 全量 dump
   精确恢复（13 条历史版本 + 家族投影 + 1819 行 `fact_tiktok_orders_monthly.template_id`），
   并把「误删」这件事的教训写进了验证脚本本身。**生产库全程只读，未受影响。**

## [v7.29.0] - 2026-11-14 - 模板治理闭环 v2：口径拉回「核心字段=需求」+ 模板决策资产进 Git

> **本版本不含任何数据库结构变更，也没有数据迁移。**
> `template_contract_current` 是 `catalog_files.file_metadata`（JSONB）内的**键**，不是新列 ⇒
> 不需要走 `scripts/run_current_schema_migrations.py`，回退也不涉及数据库回滚。
>
> **本版本含一处业务口径变更**（「多一列是否阻断」），已挂**运行时回退开关**
> `TEMPLATE_DRIFT_CALIBER=legacy` ⇒ 万一判断与预期不符，改环境变量 + 重启容器即可回退，
> 不必改代码、不必重新构建镜像。
>
> 事故现象：TikTok 订单月报文件 `catalog_files.id=3059` 保存模板后仍提示「需要更新」+「仍有字段对不上」。

### 一、根因：一条基于过期事实的规则，被提升成了全系统 SSOT

2026-11-13（v7.26.0）新增的 L3 漂移判定入口把「**多一列 ⇒ 阻断 ⇒ 静默丢数据**」
写成了硬规则。但那个前提在批次 E/F 之后**已经不成立**：

| 事实 | 位置 |
|---|---|
| `raw_data` 存的是**整行原始数据**（所有列），不是模板声明的列 | `backend/services/raw_data_importer.py:834` |
| 只为核心字段建物理列，其余只进 `raw_data` JSONB 存档 | `backend/services/raw_data_importer.py:763-765` |
| 下游语义视图**全部**从 `raw_data->>'某列'` 取值 | `sql/semantic/*.sql` |

⇒ 新列的数据**根本不丢**，它原样躺在 `raw_data` 里等语义层接入。
⇒ 这正是 2026-11-07 业务规格 §1.4 的原话：「核心字段没变，只是多了新列 ⇒ **不阻断，照常入库**」。

而 L1（`template_matcher`）的注释、L2（语义契约 `extra_raw_fields`）**一直**是「不阻断」口径
⇒ **L3 是唯一与规格、上下两层同时冲突的一层**。

**口径回退后的判定表**：

| 情形 | 判定 |
|---|---|
| 多一列（非核心） | **不阻断**（数据完整留在 `raw_data`） |
| 少一列，核心字段 `required=false` | 不阻断 |
| 少一列，核心字段 `required=true` / 域级契约 required | **阻断** |
| 少一列，清单已配置但不在清单里 | 不阻断 |
| 少一列，**清单为空** | **阻断**，文案「该维度尚未定义核心字段清单」（业务拍板 B1：配置缺口 ≠ 数据问题） |
| 值形态漂移（列名没变、值形态变了） | **阻断**（入库必然整份失败） |

实测：**27 个 published 模板全部已配置核心字段清单** ⇒ B1 口径当前**零误伤**。

### 二、闭环的三处真 bug（叠加在口径问题之上，让「做对了却看不到效果」）

1. **发布即重检静默漏检**：面板把空 `sub_domain` 渲染成字符串 `"N/A"` 返回给前端，
   前端保存模板时**原样回传** ⇒ 后端拿 `sub_domain = 'N/A'` 查文件表（实际是 `NULL`）
   ⇒ **永远匹配不到** ⇒ 重检 0 命中、且**一行日志都不打** ⇒ 文件要等 15 分钟巡检才放行。
   修复：新增 `normalize_dimension_placeholder()` 统一归一 + 0 命中补 INFO 日志。
2. **`recheck` 字段被 Pydantic 静默丢弃**：`TemplateSaveData` 未声明该字段 ⇒ 前端永远拿不到三态。
3. **文件级结论写错了行**：结论只写在 `covered` 行，前端却在 `needs_update` 行里找
   ⇒ 面板报了一句**错的话**，把排查方向带偏。

### 三、模板决策资产进 Git（决策进 Git，运行时状态留 DB）

| 进 Git | 留 DB |
|---|---|
| 列清单、核心字段清单、解析规则、列语义绑定、表头行、维度、已阅标记 | 版本号、发布时间、命中次数、成功率、审计字段 |

- `templates/definitions/` —— **27 份**声明式定义（一个维度一份，命名即维度）
- `scripts/template_definitions.py` —— 定义格式的**唯一真源**（哪些字段进 Git、哪些不许进，一处定义）
- `scripts/export_template_definitions.py` —— 从库导出（单向、只读库）
- `scripts/apply_template_definitions.py` —— `--validate-only`（离线，**已进 CI**）/ `--check`（差异守卫）/ `--apply`（投影，走界面发布同一条路）
- CI 新增一步「Verify template decision definitions」；另有 16 条守护测试

⇒ 改模板从此是**一次可 review 的提交**，而不是只发生在数据库里的一次改动。

### 四、契约语义拆分 + 发布闭环指标

**契约之前同时承担两个不同的问题**：「当年按哪一版采集」（历史事实）与「现在该按哪一版解释」（判定基准）。
两者互相迁就，最后谁都不准。⇒ 拆成三份：

- `template_contract` —— **登记事实**，只写一次，之后**不可变**（写入层强制，改不动）
- `template_contract_current` —— **当前基准**，契约晋升写它
- `template_contract_promotions` —— **晋升历史**，每次晋升追加一条

判定链路读「当前基准，缺失回退登记事实」；追溯展示读登记事实。

**闭环指标**：`scripts/template_release_sla_metric.py` 算
「模板发布后 T 分钟内，受影响文件完成重估的比例」。
发布事件 = 模板表的一行（保存模板 = 归档旧 + 插入新，新行 id 自增 ⇒ 每个模板行唯一对应一次发布）；
重估记录 = `auto_ingest.last_recheck_at` + `last_recheck_template_id`（本次新增埋点）。

⚠️ 脚本坚持把「**无数据**」与「**达标**」分开计数 —— 绝不把没数据算成按时完成。

### 五、紧急回退保险（本次唯一的业务口径变更）

`TEMPLATE_DRIFT_CALIBER=legacy` ⇒ 「多一列 ⇒ 阻断」回到 2026-11-13 的旧行为，
其余规则（核心字段缺失阻断、值形态漂移阻断、清单未配置阻断）**两套口径完全一致**。
改环境变量 + 重启容器即生效，不改代码、不重建镜像。

### 六、验证证据

| 项 | 结果 |
|---|---|
| 宽回归 | **1688 passed / 3 skipped / 0 failed** |
| 新增守护测试 | 批次 0(5) + 1(8) + 3(16) + 4(10) = **39 条** |
| 静态门禁 | `ruff check` 全过；`black --check` 全过 |
| 前端 | `vue-tsc` exit 0；`vite build` 成功 |
| 离线回放（497 文件） | 旧口径阻断 75 / 新口径阻断 75 / **结论变化 0** ⇒ 口径回退对**存量零影响** |
| 定义差异守卫 | `--check` 27/27 一致、退出码 0；**负向验证**：人为注入差异 → 精确检出并返回退出码 1 |
| 生产基线 | 发布前 v7.28.0 全部 healthy，worker/beat `restarts=0, oom=false` |

> 回放结论有硬证据：探针自检「两套口径对多一列结论不同 = True」，构成统计显示存量里
> **没有一个「多列且未被确认」的文件**。⚠️ 但**回放零影响 ≠ 安全** —— 存量里没有触发条件，
> 真正的受害者是**下一个**带新列的文件。

### 七、已知副作用

1. **那个数据库密码曾在公开仓库里 ⇒ 应视为已泄露，建议尽快轮换**（本次已清除硬编码，但密码本身没换）
2. 模板版本号跳号 v9–v12（`tiktok/orders/monthly`，内容与 v8 完全一致，诊断动作产生）；
   决策内容已进 Git，但**版本号仍是运行时状态**，跳号未根治
3. 闭环指标首日可能仍显示「无数据」（埋点本次才加）⇒ 下一次真实模板变更后才有数
4. `apply_template_definitions.py --apply` 的**写库路径未在真实库实测**（避免又一次版本跳号）
5. `scripts/` 存量 ruff 告警 138 处、仓库整体 556 个文件有 black 差异 ⇒ 均为**存量**，按预发布期规则记 V2 债

**发布与回退 runbook**：`docs/guides/TEMPLATE_GOVERNANCE_V2_RUNBOOK.md`
**设计与实施记录**：`docs/superpowers/specs/2026-11-14-template-governance-v2-design.md`

## [v7.28.0] - 2026-11-14 - 账号设备身份**二次收口**：不造指纹差异，只隔离状态 + 跟出口

> **本版本含一条数据迁移**（`current_schema_20261230_drop_residual_test_accounts`）：
> 删除两个**测试残留**主账号（`shopee / accept_main_1775126941575`、
> `验证码测试账号 / 验证码测试账号`），主账号 **9 → 7**。
> 两者都没有店铺账号、没有 profile 目录 ⇒ 没有登录态会丢；关联行由
> `ON DELETE CASCADE` 自动清理。**不可逆**（数据删除），回退靠发版前的备份。
>
> **本版本仍然不解决 IP 隔离** —— 库里代理配置还是 **0 条**，所有账号仍共用宿主出口 IP。
> 那是采购问题（见 `STATUS.md` 的 G1），不是代码问题。

### 一、方向修订（重要）：上一版的"每个账号一套指纹"被**实测证伪**了

v7.27.0 按「每个主账号一套**自洽**设备画像（浏览器/版本/视口/时区/语言）+ `machine_id` 隔离」
落地。Walter 实际用了巡店面板后追问："既然硬件指纹无法改变，那其他的修改完全没有必要了是吗？
但硬件指纹，大量的电脑都会一样不是吗？"

**2026-11-14 本机实测给出三个结论，直接推翻了那条路径：**

| 实测 | 结论 |
|---|---|
| 同一台机器开两个**独立 profile**，14 项指纹（canvas / WebGL 像素 / 字体集合 / UA / `navigator.platform` / 核数 / 内存 / 屏幕 / 时区 / 语言 / 插件 …）**完全相同**；同一 profile 重开则完全稳定 | **独立 profile 不产生任何指纹隔离** —— 它隔开的是**账号状态层**（cookie / localStorage / 缓存 / 登录态 / 平台自己的设备令牌） |
| 同型号同配置的电脑，硬件指纹**大量重复**（全球几百万台） | 硬件指纹是**群体特征**不是个体特征 ⇒ 平台**不会**拿"指纹相同"判"同一台电脑"（否则误杀几百万正常卖家） |
| 网页 JS 读得到 UA / platform / 核数 / 内存 / 语言 / 屏幕 / 时区 / WebGL 渲染器 / 插件，但**读不到** `machine_id` / `client_id` / `guid` | `machine_id` **平台看不见** ⇒ 改它对电商平台零价值 |

**还有一个被实测纠正的认知**：屏幕尺寸**是改得动的**（Playwright 的 `viewport` 会连带改
`screen`，CDP `setDeviceMetricsOverride` 也能改）。所以"不做尺寸差异化"**不是因为做不到**，
而是因为**做了更糟**：真人管多个店，显示器只有一台 ⇒ 真实用户的分辨率就那么几档；
给 12 个账号派 12 个不重复分辨率 ⇒ 落在真实分布之外 ⇒ **本身就是"批量养号"的特征**。

⇒ **修订后的口径：账号之间只隔离「状态」，不造「指纹差异」。**
真正能分开账号的是 **① 每个账号独立 profile（状态层）** + **② 不同出口 IP**；
软件层只负责**不露馅**与**跟出口自洽**。

### 二、落地了什么

| 项 | 之前（v7.27.0） | 之后（v7.28.0） |
|---|---|---|
| 浏览器环境参数 | 每个账号一套**派生**画像（浏览器/版本/视口/时区/语言全不同） | **与账号无关** —— 所有账号拿到**完全相同**的一份（`modules/utils/sessions/account_browser_identity.py`） |
| UA | 派生出来的（版本号编的） | **真实二进制版本 + 真实宿主 OS token**，只去掉 `HeadlessChrome`（采集跑 headless，带这个标记会被一眼认出自动化） |
| 屏幕尺寸 | 按账号差异化 | **不再注入** ⇒ 沿用真实显示器尺寸 |
| locale / 时区 | 按账号派生 | **跟随出口 IP 所在地区**（现在出口 = 宿主 ⇒ 取宿主；代理到位后按账号查） |
| `machine_id` 隔离 | 按 account_id 改写 `Local State` | **整体撤销**（平台读不到；且 `Local State` 由 Chromium 首次启动时创建 ⇒ 首次巡店必然漏改） |
| 巡店面板徽标 | 5 个（首登/画像/machine_id/出口/画像明细） | **2 个**（已首登 / 出口）—— 去掉"没隔离 = 有风险"的假警报 |
| 面板状态 | 窗口关了**还显示 OPEN**（watcher 只放锁、不回写状态） | **浏览器进程一没就回写** —— 状态真源是进程，不是内存里那句话 |
| 前置体检 | 7 项 | **5 项**（去掉画像与 machine_id 两项） |
| 测试残留账号 | 9 个主账号 | **7 个**（迁移删除两个脏行） |

### 三、明确**不做**的（防御不要过重）

- **不做** canvas / WebGL / 字体 / GPU 音频栈噪声注入 —— 同型号机器本来就撞，
  主动注入只会露馅；且收益接近零。
- **不做**每账号不同浏览器版本 —— 版本取真实二进制。
- **不做**假装换操作系统 / 换国家 —— `navigator.platform` 改不了，地区必须跟出口。
- **不**自建代理池 / 虚拟机集群 —— 代理是采购问题（G1）。

### 四、没解决的

- **IP 隔离**（G1）：库里代理 **0 条** ⇒ 所有账号仍共用宿主出口 IP。
  代理的真实价值是**降连带**（一个账号出事，同出口的其它账号被牵连），
  不是"让矩阵不被认出"（那靠状态层已经解决）。
- **深度指纹**（G2）：**刻意不做**（理由见第一节实测）。
- 存量账号 ID 不合规（G6）：体检记 WARN，**不主动改名**（改名会换 profile 目录 ⇒ 换登录态）。

---

## [v7.27.0] - 2026-11-14 - 账号设备身份收口：让平台无法把这批账号关联成「同一台电脑 + 同一个出口的账号矩阵」

> **本版本不含数据库迁移**。只改代码、规范与本机工具，不动生产 schema。
>
> **本版本不解决 IP 隔离**——库里代理配置仍是 **0 条**，所有账号仍共用宿主出口 IP。
> 机制已就位（见第三节），**资源是采购问题，不是代码问题**。详见第六节「没解决的」。

### 一、业务目标（先说清楚，否则下面全是技术噪音）

电商平台通过**浏览器指纹 + 出口 IP** 把我们的多个店铺账号识别成
「同一台电脑、同一根网线下的账号矩阵」，从而触发关联风控（强制验证、限权、封店）。

我们要的是**让平台关联不起来**，不是「伪装得更像真人」。

**一句话业务定义**：一个登录身份 = 一台电脑 = 一套浏览器人格 = 一个出口 IP。
账号之间必须在**设备侧**和**出口侧**都不同；同一个老板自己的多个店才共享。

> ⚠️ **方向纠偏（重要）**：本轮最初按「让所有账号像**同一台电脑**的多个店」设计，
> 经业务澄清后**推翻**。原方向产出的 6 个文件改动已全部回滚，
> 方向错误时新建的 `device_profile_manifest.py` 已可恢复删除。
> 详见 `docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure-execution.md`
> 的「回滚记录（方向纠偏）」节。

### 二、设备侧：账号之间不再长得像同一台电脑

| 措施 | 之前（实测） | 之后 |
|---|---|---|
| **设备画像** | 旧「人造指纹池」UA 20 × viewport 12 ⇒ 组合上限 60，**实测 `hongxikeji:main` 与 `shopee KR` 完全撞车**（同 ua_index=14 / vp_index=6） | 每个主账号一套**自洽**画像：浏览器 / 版本 / 视口 / 时区 / 语言互相匹配；账号间必然不同、账号内永久稳定（不随代码版本变） |
| **`machine_id`** | 6 个 profile **全部相同** `11608241`（机器级共享） | 按 account_id 确定性改写成独立值 —— 实测 Chromium **持久接受、不重新生成**（headless / headed 均验证） |
| **画像载体** | 无 | `profiles/<平台>/<账号>/.device_profile.json`，与登录态**同生共死**（删账号删目录、拷账号拷目录） |
| **占用校验** | 无 | 目标槽位被别的账号占用 ⇒ **顺延** ⇒ 账号变多也不撞 |

**OS 与地区锁宿主**（这条是踩过坑才定下来的）：画像**不假装换操作系统、不假装换国家**。
理由有二 —— ① Playwright 路径（顺序采集 / 并行扇出）**改不了 `navigator.platform`**，
给 Windows 主机派 macOS 画像 ⇒ UA 写 `Macintosh` 而 `navigator.platform` 还是 `Win32`，
**头身不符**，且字体列表 / WebGL 渲染器 / canvas / 音频栈全是 Windows 特征 ⇒ 当场被识破；
② 平台会把**浏览器时区 / 语言**与**出口 IP 所在国家**交叉比对，而当前**所有账号的出口就是宿主 IP**
⇒ 派 `de-DE / Europe/Berlin` 等于**自己制造**「中国 IP + 德国时区 + 德国语言」的三重矛盾。

⇒ 账号之间的差异来自 **浏览器 / 版本 / 视口 / `machine_id` / 出口 IP**，
**不靠假装换系统或换国家**。地区维度要放开的前提是**每个账号有自己的出口**（见第六节 G1）。

画像里**只有设备特征**，**没有任何凭据**（不写 cookie / token / 代理口令 / 账号密码）。

### 三、三条路径同一套设备 + 出口同源

| 路径 | 注入方式 | 画像缺失时 |
|---|---|---|
| 人工巡店（裸 Chromium） | CDP `Emulation.*`，在**首次导航之前**注入 | 自动分配（巡店启动时） |
| 顺序采集（`launch_persistent_context`） | context 参数注入 | 沿用 profile 原生环境 |
| 并行扇出采集（`browser.new_context`，**不挂载 profile**） | context 参数注入 | **必须 WARN**（`PARALLEL_COLLECTION_NO_DEVICE_PROFILE`），**不得静默** |

**出口同源**：代理权威位上移到**主账号** `core.main_accounts.extra_config['proxy']`（店铺级仅回退），
人工巡店与采集读**同一套优先级规则** ⇒ 登录 IP 与采集 IP 不会不一致（否则平台判定「环境突变」）。
代理配置坏了**显式失败**，不静默直连——静默直连等于账号从宿主 IP 出现。

### 四、新增账号：问题在建号时就能看见

以前「新增一个可用账号」看起来像一步，其实是**三步**（建号 → 建店铺账号 → **人工首登一次**），
第 3 步没有任何界面提示，于是「建完号」看起来像「配好了」，实际第一次采集才暴露问题。

- **新增 `scripts/check_account_readiness.py`（只读体检，7 项检查）**：
  ID 规范 / profile 目录撞车 / 平台白名单 / 画像已分配 / machine_id 已隔离 / 已首登 / 出口 IP。
  两种模式语义不同：新号前置（`--candidate-id`）不合规即 **FAIL**；存量体检（`--all`）只有
  **真实撞车**与「平台不在白名单」才 **FAIL**，ID 不合规记 **WARN**（改名会换登录态，成本高）。
- **巡店面板就绪可见**：新增只读端点 `GET /api/accounts/readiness`；
  卡片徽标显示「已首登 / 画像已分配 / machine_id 已隔离 / 出口已配」+ 画像摘要；
  **每 15 秒自动刷新**（就绪状态会随人工首登变化，静态页面不刷新就永远看不到）。
- **被白名单排除的账号不再静默消失**：以前填了白名单外的 platform，巡店面板**零提示**，
  运维只会以为「这个账号不存在」；现在显式列出并写明原因。

### 五、判据唯一（SSOT）+ 守护进 CI

「有没有人工首登」「machine_id 隔没隔离」这类判定，现在**三处同源**：

| 消费方 | 入口 |
|---|---|
| 采集侧 | `runtime_session._profile_contains_state` → 委托共享模块 |
| CLI 体检脚本 | `scripts/check_account_readiness.py` → `build_profile_state` |
| 巡店面板 | `scripts/pwcli_inspection_panel.py` → `build_account_readiness` |

- 新增 `modules/utils/sessions/account_readiness.py`（判据唯一真源）
- 新增 `modules/utils/sessions/account_device_profile.py`（画像与 machine_id 唯一真源）
- 新增守护 **38 条**：`test_account_device_isolation_contract.py`（25）+ `test_account_readiness_contract.py`（11）
  + `test_account_proxy_source_contract.py`（4，其中 3 条是本轮补的「主账号级代理优先」断言）；
- 三份新守护**全部进 CI 根契约清单**（根契约条目 57 → **60**）
  ⇒ 这条底线不会被一次改动悄悄改坏（仓库历史上有 **221 个守护从不主动执行**）
- ⚠️ 代理契约**刻意做成纯同步文件**：`backend/tests/test_account_proxy_config.py` 含 9 个 async 用例，
  在 CI 钉的 `pytest==7.4.3` / `pytest-asyncio==0.21.1` 下混进根契约清单会拿到**已关闭**的 session
  事件循环（`RuntimeError: Event loop is closed`）⇒ 断言放新文件，异步用例留在原文件由全量回归覆盖

规范同步：`COLLECTION_SESSION_LIFECYCLE.md` 的 **R8** 整节改写为
「账号设备画像（账号间不可关联）」含 R8.0–R8.4，验收项 H 改写；
上位文档 `COLLECTION_SESSION_AND_FINGERPRINT.md`《按账号固定设备画像》整节改写 + 顶部冲突声明。

### 六、没解决的（**别当成已经万无一失**）

| # | 缺口 | 性质 | 解除条件 |
|---|---|---|---|
| G1 | **IP 层无资源**：库里代理配置 **0 条** ⇒ 所有账号仍共用宿主出口 IP，平台仍可用「同一出口多账号」做关联 | **资源缺口（当前最大）** | 采购代理资源并写入主账号 `extra_config['proxy']` |
| G2 | **深度指纹未覆盖**（canvas / WebGL / 字体 / GPU / 音频栈） | 技术债 | V2 专项评估 |
| G3 | 同一主账号下多店铺**共享画像与出口** | **刻意折中**（一个卖家用一台电脑管自己的多个店是真实的） | 业务已确认接受 |
| G4 | 存量 9 个主账号 `machine_id` 仍是 `11608241` | 生效延迟 | 下次巡店/采集**自动**改写（幂等） |
| G5 | `profile_color_seed` 6 个相同 | 技术债 | 与 G2 一并 |
| G6 | 存量账号 ID 不合规（`hongxikeji:main` / `shopee KR` / `Tiktok 1店` 等） | 历史事实 | 体检脚本记 **WARN**；**不主动改名**（改名会换 profile 目录 ⇒ 换登录态） |
| G7 | 测试残留账号 `accept_main_1775126941575`、`验证码测试账号` | 数据脏 | 待业务拍板 |
| G8 | 旧指纹机制与 `data/device_fingerprints/` 26 文件仍在 | 已决策 | 保留给非 profile 路径，暂不清理 |

## [v7.26.0] - 2026-11-13 - 模板治理闭环：「模板已保存，但该样本文件仍未通过治理复核」是句假话

> **本版本含数据库迁移**：`current_schema_20261229_template_format_signature`
> —— 加列 `core.field_mapping_templates.format_signature` → 回填 → 换 published 唯一索引。
> 部署脚本自带**只读 preflight + 迁移前备份 + schema gate**，迁移失败会回滚容器，不会带着半套 schema 上线。
>
> 判定口径与模板数据在**生产（云端）**和**采集机**两个环境里各有一份；
> 代码统一走 git，模板数据另走 `scripts/sync_templates_to_cloud.ps1`（**本次未改其口径**）。

### 一、用户看到的那句提示是假的

**现象**：用户在治理面板更新模板并保存后，界面仍提示
「模板已保存，但该样本文件仍未通过治理复核」——**保存其实成功了**。

**三层根因叠在一起**：

| # | 根因 | 位置 | 表现 |
|---|---|---|---|
| 1 | 「什么算阻断漂移」有**三份**定义 | `template_matcher._classify_header_changes` / `semantic_field_contract_service.evaluate` / `data_sync_status_semantics` | 各域行为不一致；业务口径只能靠 `if` 打补丁（`shopee/orders/monthly` 单开豁免），TikTok 订单接进来时没人想到要一起打 |
| 2 | 面板读的是**漂移快照**，不是实时判定 | 治理覆盖统计 + 前端文案 | 做对了却看不到效果 —— 快照里的 `breaking_drift` 在重检通过前一直保留 |
| 3 | 保存模板**不触发重检** | 定时巡检 15 分钟轮询 | 用户改完模板要等下一轮才可能看到结果 |

顺带清掉一条自相矛盾的状态：**纯列顺序变化**曾被判「阻断漂移」，同时面板显示「匹配率 100.0%」。

### 二、判定权三层分离（判定口径 SSOT）

- 新增 **L3 唯一判定入口** `data_sync_status_semantics.classify_drift`：
  L1 事实（`template_matcher`）→ L2 语义（`semantic_field_contract_service`）→ **L3 结论（`classify_drift`）**；
  编排层（`data_sync_template_status_service`）**只消费不定义**。
- 删掉 `shopee/orders/monthly` 平台特判（它原本会造成新列被静默丢弃）；
  `预估回款金额` 保留在 L3 存量兼容名单，以免行为回归。

### 三、模板发布即闭环

- 新增 `backend/services/template_recheck_service.py`：模板保存成功后**立刻**重检同维度待更新文件，
  能过的当场放行（并完成契约晋升与快照搬移）；
- 定时巡检**复用同一份**逻辑，两处不再各写一套；
- 判定复用 `DataSyncService.get_file_sync_readiness`（与入库前置校验同一条链路），
  避免「面板说过了、入库说没过」。

### 四、面板与文案

- 治理覆盖统计同时给**组合级**与**文件级**结论：漂移快照保待办不消失，
  实时判定回答「这个样本文件此刻行不行」；
- 前端按**三态**提示：放行 / 仍待重检 / 仍有字段对不上；
- 文案不再说「仍未通过治理复核」这种把成功说成失败的句子。

### 五、语义契约升级为业务可用性判据

- 少列按**能否证明它可缺**分三种归宿：已证明可选 / 别名救回 / 其余阻断；
- **该域没有语义契约时保守阻断**（把「没有结论」与「结论是可选」区分开）。

### 六、同维度多格式并存（`format_signature`）

- 模板表加 `format_signature`，取值与变体 `variant_kind` **同一份实现**（列集合 + 解析方式 + 表头行 + 工作表名）；
- published 唯一键从「维度」改为 **(维度, 格式签名)**；
- 归档范围按**保存意图**分：`new_version`（更新既有模板）= **替换**；`create`（新建 / 创建变体）= **并存**；
- 「当前已发布模板」限定在**同格式内**：两种格式并存时不把「并存」误报成「我们升级过模板」；
  但基准那一版**已被归档**时，仍用「当前已发布模板」做对照 —— 升级信号照常成立。

### 七、入库批量刷新

- 刷新队列的合并范围从「pending」扩到 **pending + running**：正在跑的那条吸收后来到的事件并打 `rerun_requested`；
- 它跑完看到标记 ⇒ 重新排回 pending ⇒ **再刷一轮收口**；
- ⇒ 一轮入库至多「跑中的那一轮 + 收口的那一轮」，而不是「每个文件一轮」。

### 八、口径变更（业务需知晓）

| 变更 | 以前 | 现在 | 理由 |
|---|---|---|---|
| 多一列 | 平台特判放行(shopee) / 其它域阻断 | **一律阻断**（除非用户已确认） | 模板没声明的列**不会写进事实表** ⇒ 放行等于**静默丢数据** |
| 少一列 | 语义层自己判 | 无契约域**保守阻断** | 「没有结论」≠「结论是可选」 |
| 列顺序变化 | 报阻断漂移 | **不阻断** | 匹配率 100% 却报阻断是自相矛盾 |
| 「更新模板」 | 同维度全部 published 归档 | 只替换被编辑的那一版；**其它格式继续生效** | 更新 ≠ 新增一种格式 |
| 「创建变体」 | 同上 | 同格式的才替换，**别的格式并存** | 变体 = 同业务的另一种文件格式 |

### 九、验证口径

| 检查 | 结果 |
|---|---|
| 判定口径守护 `test_drift_classification_ssot.py` | **21 passed** |
| 多格式守护 `test_template_format_signature_guardrails.py` | **13 passed**（含**迁移回填 SQL 与 Python 逐字一致**的真库校验） |
| 批量刷新守护 `test_refresh_queue_batch_coalescing.py` | **5 passed** |
| 宽回归（判定/模板/契约/治理/入库） | **1532 passed / 3 skipped / 0 failed** |
| 全量 pytest（改动后） | 6599 passed / 3 failed / 13 skipped |
| 全量 pytest（stash 后基线） | 6559 passed / **同样 3 failed** / 13 skipped |
| **失败集 diff** `scripts/diff_pytest_junit.py` | **NEW failures = 0**；COMMON = 3；ADDED cases = 41；exit 0 |
| 架构 SSOT `verify_architecture_ssot.py` | 4/4 PASSED |
| UTF-8 卫生 / 规则完整性 | PASS / PASS |
| `vue-tsc --noEmit` / `vite build` | exit 0 / built in 34.46s |
| 迁移链 `alembic heads` | **单 head**：`current_schema_20261229_template_format_signature` |
| 采集机本地库 | 已升级到新 head；唯一键无重复 |

### 十、上线前置与实测清单

1. **代码与库必须同时到位**：ORM 已在读 `core.field_mapping_templates.format_signature`，
   而库若还没这一列 ⇒ 任何走真实库的链路（采集登记 → 模板匹配）都会报
   `column field_mapping_templates.format_signature does not exist`，事务被 abort ⇒ 文件登记失败。
   顺序是「**先跑迁移，再上新代码**」。
   采集机已执行 `python output/run_current_migrations_local.py --with-backup`
   （备份 + 漂移检查 + advisory lock 的 fail-closed 入口）。
2. **上线后必须实测一遍闭环**（本机没有 `template_update_required` 的真实文件，端到端只能用夹具验证）：
   改一个模板 → 面板应立刻给出「已放行 / 仍待重检 / 仍有字段对不上」三态之一。
3. **上线后自查同维度多 published 行**：
   `select platform, data_domain, count(*) from core.field_mapping_templates where status='published' group by 1,2;`
   ⇒ 允许同一维度出现多行（那是多格式并存），但**同一 (维度, format_signature) 不能有两行**。

### 十一、遗留（留给 V2，不在本版）

1. 治理面板的「维度行」还没按格式拆分展示（**判定**已按格式，展示仍是「最新一版」）；
2. 物化视图仍是全量 `REFRESH MATERIALIZED VIEW`，没改成增量刷新；
3. 本机 20 个文件全是 `ingested` ⇒ 端到端闭环只能在云端实测；
4. 全量 pytest 的既有基线污染（`test_project_env.py` 泄漏 `DEPLOYMENT_ROLE=local`）按仓库规则属非阻塞 V2 债，
   本次用**失败集 diff** 证明无新增失败。

### 十二、本版提交与文档

- `2839cad5` —— 模板治理闭环（判定口径 SSOT、发布即重检、多格式并存与批量刷新；24 files）
- `bfd976f8` —— 复盘报告 `docs/reports/2026-11-13-template-governance-closure.md`
- ADR：`docs/adr/2026-11-13-template-drift-classification-ssot.md`、
  `docs/adr/2026-11-13-template-multi-format-and-batch-refresh.md`

## [v7.25.0] - 2026-11-13 - 商品中心 SPU 缺陷收口 + 接口去重挂载 + 密钥门禁补强

> **本版本不含数据库迁移**（无新迁移、无存量数据改动）、**无接口契约变更**
> （端点集合、路径、方法均未变）、**无依赖变更**。
> 改动落在四处：① 商品中心「SKU 资料」页的 SPU 值域（前端消费方式 + 排序 + 空态文案）；
> ② 账号类 router 的挂载点去重；③ 公开仓库的密钥/账号密文取消跟踪 + 密钥门禁补强；
> ④ SSH 访问真源文档与守护测试。
>
> 方案与实施记录：`docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md` §7
> 状态索引：`docs/superpowers/plans/STATUS.md`

### 一、商品中心「SKU 资料」页的 SPU 筛选**完全失效**（根因在前端，不在后端）

**现象**（Walter 实际使用中发现）：筛选框里写着 `XH-FASHION-005`，表格里却全是
`XH-TOYS-MYTK` 的货；下拉框是空的；行内换款下拉也打不开。

**根因**：值域工厂 `createSpuSearch` 返回的是**普通对象 + 嵌套 ref**，
而 Vue **只拆包最外层的 ref** ⇒ 模板拿到的不是名单，而是"装着名单的盒子"：

| # | 症状 | 机制 |
|---|---|---|
| 1 | **下拉框是空的** | `:loading="spuBrowse.loading"` 传的是 ref 对象（**恒为真**）⇒ Element Plus 的规则是"选项列表 `vShow = options.size > 0` **且** `!loading`" ⇒ 选项列表**永不渲染** |
| 2 | **一个款也选不中** | `v-for="item in spuBrowse.options"` 迭代的是 ref 的 5 个内部属性（`dep` / `__v_isRef` / `__v_isShallow` / `_rawValue` / `_value`）⇒ 5 个 **value=undefined 的空白项** |
| 3 | **表格永远不按款筛选** | 选不中 ⇒ `skuSpuFilter` 永远是空 ⇒ 请求**从不带 `spu=`** ⇒ 后端只能返回全量第一页 |

**修法**：改**值域工厂**让它返回 **reactive** 对象（`options` / `loading` 是普通值），
而不是改调用方 ⇒ **一处改动、两个下拉同时生效**；模板不用改；**后端零改动**
（`/api/skus?spu=` 的筛选逻辑本来就正确，生产访问日志已证实）。

**证据链**：生产 `/api/spus/options?keyword=XH-FASHION-005` → 200 有数据（后端没问题）；
`/api/skus` 请求**从头到尾没有一次带 `spu=`**；生产库 `XH-FASHION-005` 当前挂货 **0**
（若筛效应是空表，实际显示 20 行 ⇒ 没筛）；1119 条当前归属**无一货挂两个款**（数据层干净）。

**为什么「平台 SKU 利润测算」页没事**：那一页的候选来自 `operatingDimensions`
（**reactive 数组**）⇒ 正常拆包、参数真发出（日志实证 `...&spu=XH-FASHION-006`）。
两者是**两个业务问题**（主数据筛选 vs 定价测算），**不该合并**。

**守护**（新增 `frontend/tests/productCenterSpuOptionsRender.test.mjs`）：
用 `vue/server-renderer` **真渲染一次**，断言款编码出现在 HTML 里、且没有空白项；
另加"工厂必须 `reactive` 且不许再 import `ref`"、"组件不许对值域对象取 `.value`"
两条结构性门禁 ⇒ 把"能 work / 不能 work"两种写法收敛成一种。
**TDD 红侧已验证**：用旧写法实跑 ⇒ `Array.isArray(options)` = false、
`typeof loading === "boolean"` = false ⇒ 断言必红。

**连带修复**（提交 `1f7cb413`）：批次 A 把局部状态容器命名成了 `api` ⇒ `api.search(query)`
被前端 API 契约门禁的正则 `(?:this\.)?api\.(\w+)\s*\(` 判成"调用了不存在的后端方法"
⇒ **Validate Data Flow 流水线红**。修法是**改名**（`valueDomain`）而不是弱化门禁。
**教训**：那道门禁**本来就存在**（既有契约用例断言全量扫描 `missing_calls == 0`），
是推送前没跑后端全量才漏出去 ⇒ **推 main 前必须跑完根 `tests/` + 后端全量**。

### 二、值域默认候选：先给"真正在经营的款"

**问题（生产实测）**：`dim_spu` 有 284 个在售款，按编码排序取前 50 个是
`XH-BABY-MC` ~ `XH-FASHION-695` ⇒ **`XH-TOYS-MYTK` 排第 277 位** ⇒
玩具类几乎永远不在默认候选里（运营不输入关键词就选不到那些款）。

**修法**：新增 `_spu_option_order()`，按**当前挂货数降序 + 编码升序**排；
浏览口径与可绑定口径**共用同一份**排序 ⇒ 不会一个按编码、一个按挂货数。
改后头部就是真正在经营的款（实测 `XH-ELEC-GF` 38、`XH-TOYS-YSC` 37、`XH-ELEC-DM` 28…）。

**口径纪律**：排序**不是口径**（哪些款可选仍由各自端点的过滤条件决定）；
"当前有效归属"的判定**引用真源** `current_binding_condition()`
（`binding_status='active' AND effective_to IS NULL`）⇒ 不手抄；
用**相关子查询**而非 join+group_by ⇒ 不改 SELECT 形状，也不引入"非聚合列"的分组问题。

**TDD 红侧已验证**：把排序临时改回"按编码排" ⇒ **4 条新用例全红**。

### 三、空结果说清原因与下一步

**问题**：选中一个当前挂货 0 条的款（实测 `XH-FASHION-005`），表格只显示笼统的
"暂无数据" ⇒ 运营以为系统坏了；下拉搜不到也只显示"无数据" ⇒ 运营以为根本没有款。

**修法**：SKU 表格接 `:empty-text="skuEmptyText"` —— 按款筛时显示
**「款 X 当前没有挂货」**，没在按款筛时沿用默认文案；两个下拉各接一套 `no-data-text`：
浏览口径提示"换个关键词"，可绑定口径提示"先去「SPU 管理」新建款"
—— 两者的下一步动作不一样。

### 四、同一组接口被**挂载两次**（律 1「真源只能一个」）

**实测**：development / collector 模式各有 **24 条 (路径, 方法) 重复注册、涉及 17 条路径**；
production 模式 0 条（**production 根本不注册 collection 域**）。
FastAPI 生成 OpenAPI 时为每条重复路由打 `UserWarning: Duplicate Operation ID`
—— 这是重复挂载**唯一可观测**的信号（schema 里同一 (路径, 方法) 会被后一次注册覆盖）。

**修法**：账号类 router（主账号 / 店铺账号 / 店铺别名 / 平台店铺ID发现 / 仓名别名）的
**唯一挂载点**定在 **platform 域**，删掉 collection 侧那 5 条 include。
⚠️ **不能反过来删 platform 侧的**：production 模式不注册 collection 域
⇒ 账号类接口在生产上只由 platform 提供 ⇒ 反过来删会**删掉生产接口**。
改后四种模式的重复条目**全部归零**（759 → 735、409 → 385）。

**守护**（新增 `backend/tests/test_router_unique_mount_points.py`）：
四种运行模式逐个断言没有重复注册；production / development 下账号类接口依然存在
（防"去重复"变成"删接口"）；这 5 组端点函数各自只注册一次；
生成 OpenAPI 时不许出现 `Duplicate Operation ID` 警告。

### 五、公开仓库跟踪着生产密钥与**店铺账号密文**（安全）

**取证**（只读、全程 SHA-256 比对、不打印任何值）：

- **现役密钥未泄露** —— 生产 `.env` 与 4 个容器生效环境变量的 5 个敏感值，
  与仓库被跟踪文件里的旧值**逐项全不同**；泄露的旧密钥也**解不开**生产库里
  `core.shop_accounts` 的账号密码（实测 `InvalidToken`）。
- **但公开的是已废弃的旧密钥**，而且 —— ⚠️ **密文与解密密钥同时公开**：
  仓库里同时跟踪着 `accounts.enc`（Fernet 密文）与 `.env.cleaned`（带
  `ACCOUNT_ENCRYPTION_KEY`）⇒ **实测可用公开仓库里的密钥直接解开 `accounts.enc`**，
  解出 **15 个店铺账号**（Amazon / Shopee / Tiktok / 妙手ERP / miaoshou），
  **每个都有非空密码**，还带邮箱账号密码、手机号与代理配置。
  ⇒ 这不是"旧密钥泄露"，是**店铺账号密码公开**。

**本版处置**：

1. **取消跟踪**（`git rm --cached`，本地文件保留）：
   `.env.production.passwords.txt`、`.env.cleaned`、`accounts.enc`、
   `frontend/.env.development`（Mock 开关已从代码删除，是死文件）。
2. **`.gitignore`**：`.env.*`（含 `!.env.example` / `!.env.template` / `!.env.limiter`）
   + `*.passwords.txt` + `*.enc`。
   ⚠️ `.env.limiter` 必须**继续**入库 —— 限流器直接读它，且要求纯 ASCII。
3. **补门禁** `scripts/check_precommit_secrets.py` 的 `is_blocked()`：
   从"只拦文件名**恰好**是 `.env` 与 `.key`/`.enc` 后缀"改成**按规则**拦
   （`.env` 家族 / 疑似敏感名 + 数据类扩展名 / 加密文件与密钥证书后缀）。
   敏感名规则**不误伤**文档与脚本（`scripts/reset_passwords.py` 这类是正常的）
   —— 门禁太宽比没有门禁更糟：大家会开始习惯性 `--no-verify`。
4. **守护测试**（新增 `tests/test_secret_files_not_tracked.py`，并进 CI 根契约清单）：
   这些文件不在 `git ls-files` 里；**全仓扫**确认没有任何被跟踪文件会被门禁拦下；
   门禁对泄露文件判拦、且不误伤模板/文档/脚本；`.gitignore` 真的挡住。
5. **真源文档** `docs/guides/ENV_FILE_CONTRACT.md` 增「Repository Tracking Policy」。

**历史不可撤回** —— `git filter-repo` 会作废全部已发布 tag（含 `v7.24.0`），
**本版明确不做**。**仍需拍板**：轮换那 15 个店铺账号的密码、删除生产机上的旧密钥副本、
确认旧密钥在已下线环境里是否还活着 —— 已写进 `docs/superpowers/plans/STATUS.md`。

### 六、SSH 访问真源文档 + 守护测试（随本版首次发版）

`docs/guides/SSH_ACCESS.md` 把四条通道（GitHub 代码 / 生产运维 / 云端隧道 / 生产部署）
的账号、钥匙、用途写成真源，并配 12 例守护测试（文档 ↔ 脚本一致性、
脚本不得把 `root@` 当登录目标、禁 `sshpass`…）。
起因是一次真实的误判：把"本机没有生产私钥"当成了事实，据此写下"部署类核验无法登机"。
真相是：交互式生产身份是 `deploy@` + `~/.ssh/github_actions_deploy`，
`root@` 只属流水线（私钥在 GitHub Actions Secret）——**本机登不上 root 是设计，不是缺私钥**。

### 七、发布与部署后验收

**发布物料**

| 项 | 值 |
|---|---|
| 版本 | **v7.25.0** |
| tag 对象（双端同一对象） | `20ffd319`（annotated tag） |
| tag 指向的提交 | `707d9826`（**VERSION 与 tag 同提交** —— `VERSION` 纯 7 字节 `v7.25.0`） |
| 双镜像 main | GitHub SSH-443 与 CNB HTTPS **同为 `707d9826`**（`git ls-remote` 核对） |
| 发布流水线 | **run `43392504235` = success**（check-config / Validate Data Flow / Build and Push Images / Deploy to Production 全 success） |
| 本次改动 | 无数据库迁移、无接口契约变更、无依赖变更 |

**流水线上的门禁（这次真的在验）**

| 门禁 | 结果 |
|---|---|
| API 契约门禁 | `Changed router files: 1` → `本次验证: 1 个文件` → **`F 真静默: 0`**（不是空转：本次改了 `product_center.py`） |
| 前端 API 方法门禁 | `已定义API方法数: 278` / `缺失方法调用数: 0` / `[OK] 所有API方法调用都存在！` |
| 其他发布门禁 | 生产迁移契约 / 数据库字段 / 库存账龄流水线 / 镜像依赖 pin / 容器启动 smoke —— 全 success |
| CI 三线（main） | Validate Data Flow ✓ / CI Pipeline ✓ / Docker Build and Push ✓ |

**部署后独立验收**（不依赖流水线自述，agent 自己打的接口）

| 项 | 结果 |
|---|---|
| `/api/healthz/ready` | **HTTP 200**，`version=**v7.25.0**`，`database=connected`（PostgreSQL），`dashboard=ready`，`runtime_mode=production` |
| 首页 | **HTTP 200** |
| 生产容器 | 7 个全 **healthy**；`backend_api` / `celery_worker` / `celery_beat` = `backend:v7.25.0`，`frontend` = `frontend:v7.25.0` |
| 部署批次 | `bootstrap_postgresql_dashboard_20261113_163211.log` + `rebuild_views_20261113_163211.log`；日志确认 `Skipping database migrations (RUN_MIGRATIONS=0)`（与"本版无迁移"一致） |
| **路由无损**（C1 的生产侧证据） | 生产 `/api/openapi.json` 部署前后**完全一致**：**510 路径 / 625 操作 / 625 个 operation_id 全唯一 / 0 重复** ⇒ 去掉重复挂载**没有丢任何接口** |
| **新排序真的在线上** | 部署后的后端容器里 `_spu_option_order` 出现 **3** 处 ⇒ 新代码已生效；生产库按「当前挂货数 desc、编码 asc」实测的头部：`XH-ELEC-GF` 38、`XH-TOYS-YSC` 37、`XH-ELEC-DM` 28、`XH-TOYS-GMGD` 26、`XH-TOYS-ZD` 26、`XH-TOYS-GD` 24、`XH-TOYS-MYTK` 20、`XH-FASHION-006` 18、`XH-FASHION-KLM002` 16、`XH-TOYS-DK` 16 |

⚠️ **本次发布仍留了两件事给 Walter 拍板**（代码侧已做完止血，见 §五）：
轮换那 15 个店铺账号的密码、删除生产机上的旧密钥副本。
`git filter-repo` 历史清理**不做**（会作废全部已发布 tag）。

## [v7.24.0] - 2026-11-13 - API 契约门禁：它至今没看过一行真实路由代码

> **本版本不含数据库迁移**（无新迁移、无存量数据改动、无接口变更）。
> 改动只落在**守护层**（发布门禁 + 守护测试 + 文档），
> 业务代码仅补了两处**失败原因日志**（**行为一字未改**）。

### 一、发布流水线上的「API 契约体检」一直在空转

**现象**：v7.23.0 改了 `backend/domains/business/routers/product_center.py`，
门禁却报「本次发布没有改动 router 文件，跳过验证」并**绿灯放行**。

**根因**（两层）：

1. **扫描范围停在旧门牌号层**。路由代码有两层：
   - `backend/domains/<业务域>/routers/*.py` —— **82 个真正定义路由的实现**（真源）；
   - `backend/routers/*.py` —— **76 个兼容垫片**（旧导入路径的别名层）。

   实测这 76 个垫片里**零路由定义**（无 `APIRouter(` / `@router.` / `include_router`）
   ⇒ 它们不是第二份真源，只是一层别名，**不构成双维护**。
   而脚本的扫描范围**正好停在垫片层**，过滤条件又是 `startswith("backend/routers/")`
   ⇒ `--changed-files` 模式（发布门禁用的就是这个）**一个真实路由都匹配不到**。

2. **告警口径靠正则猜**。用「正则找 `try:` + 按缩进猜块尾」判定异常块：
   一个 `try:` 配多个 `except:` 会重复计数，`try:` 出现在字符串/注释里会误命中，
   块尾靠 `content.find('\n    ')` 猜 ⇒ 缩进一变就切错。
   报出的「518 条缺错误日志」**这个数字本身不可信**。

⇒ 这道门禁**至今一次都没拦下过任何东西，也没看过任何一行真实接口代码**。

### 二、修好之后（CI 日志实锤，非本地推断）

| 项 | 改前 | 改后 |
|---|---|---|
| 全仓体检文件数 | 76（全是空垫片） | **158**（候选）⇒ 其中 **80** 个真定义路由 |
| 改动的域内路由 | **0**（报「跳过验证」） | **≥ 1**（真去验） |
| 异常块总数 | — | **886** |
| 告警条数 | 571（含 518 条噪音） | **65**（真静默 47 + 缺 `recovery_suggestion` 18） |
| 报告行数 | 1700+ | **35** |
| 错误数 / 退出码 | 0 / 0 | **0 / 0**（**不卡任何一次发版**） |

异常处理按 **AST 精确分桶**（六桶**互斥**，命中即停）：

| 桶 | 数量 | 说明 |
|---|---|---|
| A 记了错误日志 | 433 | 合规 |
| D 显式 raise | 180 | 错误带着 cause 走，不是缺陷 |
| B 只记其它级别日志 | 126 | 合规 |
| C 结构化 `error_response` | 55 | **这是正确写法** |
| E 有意降级 | 42 | 设计如此 |
| **F 真静默** | **47** | **真正该看的**（不记、不抛、不返回、不跳过） |

⇒ 旧口径噪音比 **518 : 47 ≈ 11 : 1**。

**读文件用 `utf-8-sig`**：仓库里有 74 个路由文件带 UTF-8 BOM，
而 `ast.parse` 对以 U+FEFF 开头的字符串直接抛 SyntaxError
⇒ 用 `utf-8` 读会让这些文件被**静默跳过**（本次统计就因此少算了 12 个文件）。
改用 `utf-8-sig` 后实测**解析失败 0 个**。

### 三、两批提交（范围与口径必须同批）

| 批次 | 提交 | 内容 |
|---|---|---|
| 第一批 | `795cc6d7` | 扫描范围修到真源 + AST 六桶口径 + 聚合报告 + **守护测试 17 例** + 流水线旧前缀计数 + 规范文档 3 处 + 发布清单自查项 |
| 第二批 | `cc51a1c7` | 3 个守卫失效 except 块补失败原因日志（**零行为变更**） |
| 文档 | `de0659c9` / `ad69df02` | 方案文档与状态索引 |

**守护测试是这次的重点**（`backend/tests/test_api_contract_gate_scope.py`，17 例）：
扫描范围（含那 12 个带 BOM 的文件）、旧垫片也在范围内、非路由文件不得被误纳管、
路径归一化（绝对路径 / Windows 反斜杠 / `./` 前缀）、六桶互斥且相加等于 except 块总数、
真静默数被钉死、报告不刷屏。

**TDD 记录**：先写测试 → 亲眼看它以**正确的原因**红
（核心用例报 `assert 0 == 1` = 域内路由匹配不到）→ 再写实现 → 转绿。

### 四、口径重新核准：上一轮口头说的「58 处」不可复现

上一轮统计用的临时脚本**没有入库** ⇒ 口径不可复现
（穷举 8 组谓词变体 × 六个桶维度，**无一命中 58**）。
处置原则是**人工复核 > 拟合数字**：挑出两处差异块人工判定（都是「有意降级」），
据此把 E 桶定成「except 块里只要有任何控制流决策就不算静默」，重新核准为 **50 处**；
第二批补完日志后是 **47 处 / 27 个文件**。

⇒ **数字与口径都写进守护测试**（含 2 条语义锚点 + 2 条守卫锚点）。
这正是律 1「真源只能一个，而且必须写在纸上」的由来。

### 五、业务概念零变化

商品（SPU）状态集、「可绑定」口径、款/货拆分模型、归属三状态、
各域业务概念、所有对外接口的地址与返回结构、数据库结构 —— **全部原样**。
变的只有两件工程事实：**谁来体检**（范围与口径），以及
**新代码写在哪条路径**（规范文档指向真相点，旧门牌号仍可用但不推荐）。

### 六、顺带修掉的两个真问题

* `product_center.py` 的 `_count_sku_business_references`（**2 个** except 块）：
  引用计数失败就静默报 0 ⇒ **补了失败原因日志**。
  （注：下游明写「业务引用计数**不阻断软删**」，真正会放行的是尚未实现的 M5.2 硬删门槛。）
* `collection_schedule.py` 的 `health_check()`：DB 探测失败把原因整个丢掉
  ⇒ **补了失败原因日志**（状态仍如实设为 `error`）。

两处**行为一字未改**：仍回滚事务、仍报 0、仍设 `db_status=error`。

### 七、发布与部署后验收（2026-11-13）

- tag `v7.24.0`（tag 对象 `802a08ab`）**双端同一对象**，均指向发版提交 `0e6ec9c8`；
  推送顺序：先 CNB（惰性、建立 parity）→ 再 GitHub（触发部署），**未在 GitHub 侧回填**。
- 发版提交 CI 三线全绿（CI Pipeline / Validate Data Flow / Docker Build and Push）；
  本地 `scripts/verify_release_local.py --skip-build` **exit=0**；
  `VERSION` 为纯 7 字节 `v7.24.0`（无 BOM、无换行），与 tag 同一提交。
- 部署流水线 run `43372513282` **success**，且 v7.24.0 **恰好 1 个 run**。
- **迁移**：本版无新迁移 ⇒ `migration_status=up_to_date`，
  `current_revision == head_revision == current_schema_20261228_bridge_spu_sku_binding_status_constraint`，
  `missing_tables=[]`、`missing_columns=[]`，**schema 门禁通过**。
- 部署期 Phase 2.7 视图重建 40+ 个定义全部就位；Phase 3a / 3a' 库存层重建均 `[OK]`。
- **生产验收（HTTP 直观测）**：`/api/healthz/ready` → 200、`version=v7.24.0`、
  `database=connected`、`dashboard=ready`；首页 200。
- **★ 门禁在真实发布里第一次真的验到了东西**（本次发布的决定性证据）：

  ```
  [INFO] Changed router files: 2
  开始验证API契约（仅验证 13 个改动文件）...
  扫描候选: 158 个文件（仓库内可能的路由位置）
  本次验证: 2 个文件（其中定义路由的: 2 个）
  F 真静默（不记、不抛、不返回、不跳过）: 0
  ```

  改动前同一位置会打印「Changed router files: 0」+「跳过验证」并绿灯放行；
  现在打印 **2**，并**真的去验了那 2 个域内路由文件**。
  而真静默显示 **0** ⇒ 第二批给这 2 个文件补的失败原因日志**已被门禁确认生效**。

### 八、已知未落地项（已排期，不在本版）

| 项 | 说明 |
|---|---|
| 47 处真静默 | 分批清理（跨 4 域 27 文件，pre-launch 要求拆） |
| 74 个带 BOM 的路由文件 | 单独一批清理（本版已用 `utf-8-sig` 兜住，不阻塞） |
| fail-closed（计数失败即拒删） | 需先定义「引用数未知」状态，建议随 M5.2 硬删一起做 |
| 端点清单/权限/菜单三处合一 | 架构演进级，需产品决策，暂不立项 |

## [v7.23.0] - 2026-11-12 - 商品中心「款 / 货 / 归属」概念收敛 · V2 债全部结清

> **本版本含一次数据库迁移**
> （`current_schema_20261228_bridge_spu_sku_binding_status_constraint`，
> **只加约束**、**一行存量数据未改**）。
>
> - 存量行全部满足新约束（实测 1118 行 `active` + 3 行 `inactive`，0 行越界）；
> - 迁移前 **fail-closed** 校验存量行 ⇒ 有脏数据就报错回滚，不悄悄放过；
> - 另有一条同批次的迁移 `current_schema_20261227_dim_spu_lifecycle_constraints`
>   （`core.dim_spu` 两条 CHECK，20261227）。

### 一、运营报的「输入编码却查不到」从来不是分页问题

**现象**：SKU 资料页的「所属 SPU」筛选框输入编码后只显示「无匹配数据」，回车不生效。

**根因不是「翻页」，是概念问题**：「可选的款」被做成了「SPU 管理 tab 那一页」的**分页表格数据**
（`/api/spus` 默认 page=1、page_size=20），而 `dim_spu` 实测 **286 条**
⇒ 第 36 个 SPU（`XH-FASHION-001`）**永远不在候选集里**。

**修法不是「把分页调大」，是把「值的域」从「实体列表」里拆出来**：

| 端点 | 口径 | 用途 |
|---|---|---|
| `GET /api/spus/options` | 浏览口径：在售（`active IS TRUE`） | 工具栏「所属 SPU」**筛选**（查询条件，敲什么都能查） |
| `GET /api/spus/assignable-options` | 可绑定口径：`biz_status ∈ {candidate, testing, promoted}` | SKU 行**赋值 / 换款**（外键，不许造出挂不上的款） |

口径**固化在后端**，不暴露给调用方自由拼装 ⇒ 前端无法组合出「已删除但状态还是候选」。

### 二、「这个款还在不在」曾有两个真相来源，现在只有一个

`dim_spu.active`（布尔）与 `dim_spu.biz_status`（经营成熟度）编码的是同一件事，
而两者的**写入约定不一致** ⇒ 能造出 `active=false + biz_status='candidate'` 这种自相矛盾的行，
且 `dim_spu` 上**当时没有任何 CHECK 约束**。

**建模 A**（Walter 拍板）：`active=false` 必然是 `biz_status='retired'`；
但 `retired` 可以不删（逻辑淘汰，历史仍要留）。
⇒ 不变量 `active=false ⟹ biz_status='retired'`
⇒ 「可绑定」= `biz_status` 不是 `retired` ⇒ **判定只需一个条件**。

配套：`SpuBulkItem` / `SpuUpdateRequest` **不再接受 `active`** ——
`active` 只能由删除 / 恢复三个专用端点写（前端整行回写带来的 `active` 被 Pydantic 忽略）。

### 三、归属关系不再是「一个字段」

`core.bridge_spu_sku` 是**带生效区间**的关联（`effective_from` / `effective_to` / `binding_status`），
但列表只投影了「今天的落点」一个字符串 ⇒ 运营看不到「这个货是什么时候挂到这个款上的」。

⇒ SKU 行给出「当前归属（自 YYYY-MM-DD）」；
⇒ **款 / 货的响应模型拆开**：`ProductCenterItem` → `SpuItem`（`spu` 是标识，必填）
  / `SkuItem`（`spu` 是引用，可空，无 `active`），
  `ProductCenterListResponse` / `BulkMutationResponse` 同样一分为二，
  **旧的三个模型一律删除**（留着就是留后门）。

### 四、归属关系现在**双向可达**

SKU 资料页里存量行的 SPU 列以前是**只读**的，改归属只能从「SPU 管理」tab 的抽屉**单向**进入。
⇒ 存量行的 SPU 单元格改为可编辑，改动走**已有的** `bulk_save_skus` 通道
（不另开写入路径 —— 归属有生效区间、有归档、有审计，另写一条必然漏掉一半）。

**顺带修掉两个真实缺陷**：

* 写入路径曾在**归属没换**时也校验「这个款还能不能挂货」
  ⇒ 一个挂在**已淘汰款**下的 SKU，运营只想改个重量，保存却收到 422「不能绑定新 SKU」
  （与他做的事毫无关系，且无从绕过）⇒ 改成**只有真的换款**才校验；
* 同日换款曾被硬拒（`starts_on <= binding.effective_from`）⇒ 改成**只有改到过去**才拒绝。

### 五、两个真源 + 全仓不再手抄（律 1）

| 真源 | 管什么 |
|---|---|
| `backend/services/product_spu_lifecycle.py` | SPU **自身**的状态与「能不能挂货」 |
| `backend/services/product_spu_binding.py` | SKU ↔ SPU **归属关系**的状态与投影 |

「什么关系算当前有效」这个判定原本被**手抄在 13 个文件**里
（路由 20 处 + 4 个业务服务 + 种子脚本 + 测试与冒烟脚本）
⇒ 全部改为引用真源，并加**全仓扫描**守护测试：再手抄一份，测试立刻变红。

归属状态的三个语义各自独立：`active`（当前有效）/ `inactive`（软删封存，**可**复活）/
`historical`（换款归档，**不可**复活）⇒ 真源补齐三值 + DB CHECK 约束兜底，
杜绝第四个值静默写进库。
ORM 的 `uq_bridge_spu_sku_current` **部分索引谓词**也一并改为从真源渲染 ——
「一个 SKU 只有一条当前归属」这条规则同样不该在 ORM 里再抄一遍。
守护测试用 `tokenize` 精确扫**生产代码**里写死的状态（注释 / 文档字符串 / raw SQL 片段不误报）。

### 六、typecheck 门禁**从来没有真正跑过**

`scripts/run_typecheck.py`（`make typecheck` 走它）的目标里写着
`backend/routers/dashboard_api.py`，而那个文件**早已不存在**
⇒ mypy 每次都报错 ⇒ 这道门禁形同虚设。

**代价**：本轮实测踩过一次 —— 漏导入 `archived_binding_condition`
⇒ `restore_spu` / `restore_sku` 运行到那行才 `NameError`，
而**全量后端测试照样全绿**（那两条路径没有执行用例）。

⇒ 指向改成 `dashboard_api_postgresql.py`，并把商品中心的运行时面纳入门禁；
   新增 `backend/tests/test_runtime_surface_integrity.py`：
   守着**门禁目标必须存在**，并**静态**断言路由不引用未定义的全局名。

### 七、验证口径

| 项 | 结果 |
|---|---|
| 后端全量 | **4554 passed / 7 skipped / 0 failed** |
| 前端全量 | **195 passed** |
| lint / mypy / 前端构建 | 全部通过（顺带修掉路由里 3 处既有 mypy 告警） |
| 迁移 | `20261227` + `20261228` 均 upgrade → 验证 → downgrade → upgrade 往返通过 |
| DB 行为 | 非法 `binding_status` 被 CHECK 拒绝；三条 CHECK 均生效 |
| 真实换款 | 旧关系归档为 `historical` + 新关系生效 + 当前归属唯一 + 生效日正确投影（已还原现场） |

### 八、仍未做（**产品演进**，不是技术债）

「款 → 货」的**页面层级重排**（以款为聚合根的层级视图）——
触及面远超一个功能缺陷，按 pre-launch 约束不该混进 launch 期改动。
**这是一件产品决策，需要先定 IA，再动手。**

### 九、发版实测与部署后验收（v7.23.0，2026-11-12 23:51 → 次日 00:16 CST）

| 项 | 结果 |
|---|---|
| tag | `v7.23.0`，注解 tag 对象 `97b7731d`，**GitHub 与 CNB 双端同一对象** |
| main | `2685ffd8`，双镜像同一 SHA（`ls-remote` 复核） |
| 发版流水线 | `deploy-production.yml` run `43252281527` 全绿：check-config → 发布门禁 → 镜像构建推送 → 远端部署 |
| 远端迁移 | `current_revision = head = current_schema_20261228_bridge_spu_sku_binding_status_constraint`；`missing_tables: []`、`missing_columns: []`；schema 门禁通过 |
| 镜像 | `Backend=v7.23.0` / `Frontend=v7.23.0`（CNB 主源拉取成功） |
| 部署后健康端点 | `https://www.xihong.site/api/healthz/ready` → HTTP 200，`version=v7.23.0`，`database=connected`，`dashboard=ready` |
| 新端点已上线 | 生产 OpenAPI 含 `/api/spus/options` 与 `/api/spus/assignable-options`；线上前端 chunk 含 `listSpuOptions` / `listSpuAssignableOptions` |
| 库存层重建 | `[OK] Inventory age full rebuild completed` + `[OK] Inventory state full rebuild completed`；`mart.inventory_state.last_succeeded_at = 2026-11-12T16:16:01Z`（晚于部署开始） |
| 监控存在性 | `missing_targets` 为空，无 `object_exists=false` 的目标 |
| 批次数 | `deploy-production.yml` **只新增 1 个 run** —— CNB 侧推 tag 是惰性的，没有触发第二次部署 |
| 容器 | backend-api / celery-worker / celery-beat / frontend / nginx 全部 Started，日志中无 `Restarting` / `VersionMismatch` / 回溯 |

**发版前被门禁拦下的三处**（都不是业务缺陷，但都会真实伤害线上）：

1. **black 格式门禁**（`CI Pipeline` → `Code formatting check`）：CI 只对**本次变更过**的 Python 文件跑 black，
   本批 26 个文件里有 16 个没过 ⇒ 已按仓库标准（`line-length=88`）格式化，+165/-68，纯格式无语义变更。
2. **`VERSION` 被写成双 BOM**（`Run root contract tests` 步）：`backend/main.py::_load_app_version()` 用
   `encoding="utf-8"` 读它（不是 `utf-8-sig`），`strip()` 也去不掉 `U+FEFF`
   ⇒ 线上 `/healthz/ready` 会报出 `'\ufeff\ufeffv7.23.0'` 这种坏版本号。
   已恢复成仓库规范形态（纯 7 字节 `vX.Y.Z`，与 v7.22.0 的 git blob 一致）。
3. **一个 `U+FFFD` 坏字节**：我自己在 `test_product_spu_lifecycle_ssot_contract.py` 的提示文案里打错了一个「生」字。
   `verify_utf8_source_hygiene.py` 抓得到，但 **CI 不跑这个脚本** ⇒ 靠本地门禁拦住。

## [v7.22.0] - 2026-11-11 - 采集失败的真实原因不再被盖掉 + 状态清单收敛到真源

> **本版本含一次数据库迁移**（`current_schema_20261226_task_center_status_constraint`，
> **只放宽**任务中心的状态 `CHECK` 约束 ⇒ **不改任何一行的业务归属**）。
>
> - 历史数据依旧**一行未改**（不回填、不重推）；
> - 语义层计数口径**未动**（`count(DISTINCT c.resolved_shop_id)`）；
> - ⚠️ 另按用户 2026-11-11 决策**清理**了日/周粒度事实行（整体废弃重采，不是逐行订正）。

### 一、采集失败的真实原因不再被「事务回滚」噪音盖掉

**现象**：9 家 shopee 采集失败，后台显示的失败原因是

```
This Session's transaction has been rolled back due to a previous exception during flush
```

而不是「平台要求滑块验证码，等人工处理」。

**根因**：`task_center_tasks` 表的状态 `CHECK` 约束里是**手抄**的一份状态清单，
漏了 `verification_required` / `verification_submitted` / `manual_intervention_required`
⇒ 采集走到「等人工处理」时写任务中心被 PostgreSQL 直接拒绝（`CheckViolationError`）
⇒ SQLAlchemy 事务回滚 ⇒ 上层兜底捕获到的异常变成「事务回滚」噪音
⇒ **真实原因丢失**，前端的人工处理入口也拿不到正确状态。

实测证据：任务 691 / 692 的 `error_message` 全文里含
`CheckViolationError ... violates check constraint "chk_task_center_tasks_status"`
与 `DETAIL: Failing row contains (2103, ..., manual_intervention_required, ...)`。

**修法不是「再补一次手抄」**：根因是「状态清单被复制成 6 份，其中一份漂了」
⇒ 真源 `backend/services/collection_task_status.py` 本就自称 SSOT，
但它只定义了状态**分组**，**没定义「任务中心能写哪些状态」**
⇒ 这次让**所有派生点都从真源派生**（ORM 约束 / 配置运行服务 / 调度路由 / 任务映射 /
前端两个视图由守卫测试断言一致）。

顺带补上真源**自己**缺的一个状态：`interrupted`
（服务重启回收时真实写进 `core.collection_tasks` 的终态，原先真源里根本没有）。

### 二、测试不再往正式数据目录写假文件

**现象**：`data/raw/2026/` 里混着 **176 个假文件**（内容 `fake-export`，**11 字节**，
全部没有入库记录）⇒ 排查数据问题时差点误判成「订单采了没入库」。

**根因**：采集执行器用 `get_data_raw_dir()` 决定落盘目录，而它读环境变量 `DATA_DIR`。
`backend/tests/conftest.py` 已给**数据库 / Redis / Celery** 加了护栏，**唯独漏了文件系统**。

⇒ 本版本补上根 `tests/conftest.py` 的文件系统护栏。⚠️ **护栏本身踩了两个坑**，
都已在代码注释与方案文档里写明：

1. 仓库根 `.env` 的 `DATA_DIR=./data` 会在 **import 期**被
   `load_project_env(override=True)` 覆盖回正式目录
   ⇒ 只在 conftest 顶层设一次环境变量**护不住**；
2. `get_data_dir()` 带 `@lru_cache` ⇒ 第一次调用就把旧值**冻住**。

⇒ 护栏改为**每个用例前**重新钉一次环境变量 + `cache_clear()` 掉目录缓存。

### 三、日/周粒度：整体废弃重采（用户 2026-11-11 决策）

⇒ **先改声明再执行**：`modules/core/shop_identity_ssot.py` 新增
`DISPOSABLE_GRANULARITIES = ('daily', 'weekly')` 例外声明。
月粒度 / 快照粒度**完全不动**（经营口径基准，错了要人工判断）。

| | 本地 | 云端 |
|---|---|---|
| 日/周行（已删） | **2211** | **2641** |
| 备份 | `%TEMP%\mcode_granularity_backup_20261111\LOCAL_*.jsonl`（完整行数据，可逐行恢复） | `CLOUD_*.jsonl` |

⚠️ 连带：3 个 semantic 物化视图读日/周事实表 ⇒ 删了不重刷 = 白删。
重刷后**两端** `fact_orders_atomic_mv` / `fact_analytics_atomic_mv` /
`fact_products_atomic_mv` 的 daily/weekly 残留**归零**，正本只剩 monthly。

### 四、顺带修掉的既有 lint

`collection_schedule.py` 两处 `CollectionConfig.is_active == True` 是基线就有的 E712
⇒ CI 会对本 PR 改到的文件跑 ruff ⇒ 改成 `is_(True)`
（该列 `nullable=False` 的 Boolean ⇒ `= true` 与 `IS true` 对每一行都完全等价）。

### 五、验证口径

| 项 | 结果 |
|---|---|
| 根 `tests/` | 745 passed / 5 skipped / **0 failed**（基线 738 ⇒ +7 条守卫） |
| `backend/tests/` | 5688 passed / 8 skipped / **0 failed**（基线 5664 ⇒ +24 条守卫） |
| 失败集 diff | 两端均 `NEW failures = 0` / `FIXED failures = 0` |
| `black==25.1.0` | 10 个改动文件全部 clean（用 CI 同环境 Python 3.11 容器复验过） |
| `ruff 0.17.3` | 全部通过 |
| 迁移真库演练 | 升级前写 `manual_intervention_required` **被拒**（复现 bug）⇒ 升级后 13 状态全可写、`bogus_status` 仍被拒 ⇒ 降级后约束**逐字恢复** |
| 护栏实测 | 修复前每次写 8 个文件 ⇒ 修复后 **0 个**（两端工作区均 0 新增） |

### 六、遗留（需人工，不在代码范围）

- 9 家 shopee 的**平台侧拦截登录**、tiktok 6 个账号的登录状态确认、妙手账号验证码回填
  —— 属风控范畴，**不自动重试**；
- 14 个采集配置 `schedule_enabled=false` ⇒ 调度器在跑但没注册采集任务（配置/运维决策）。

## [v7.21.0] - 2026-11-11 - 店铺身份「保未来」守护真的立起来 + 律 3 在存量库落地

> **本版本含一次数据库迁移**（`current_schema_20261225_rebuild_identity_candidates_copy`，
> **只重建一个物化副本的定义**，不改任何一行的业务归属）。
>
> - 历史数据依旧**一行未改**（不回填、不重推）；
> - 语义层计数口径**未动**（`count(DISTINCT c.resolved_shop_id)`）。

### 一、律 3 落地：候选集副本改为「从正本取数」

候选池的口径**只有正本一处**定义。它的物化加速副本**曾经**手抄了一份正本的计算逻辑，
两边靠人工保持一致 —— 一旦漂移，漂移是**静默**的：不报错、不告警，
看板只会表现为「某个店没人了」。

副本资产早就改成「只从正本取数」，但资产的刷新语义是「存在则 REFRESH / 不存在则 CREATE」——
`REFRESH` 只重算**数据**，不换**定义** ⇒ **存量库上的副本永远不会被换成新定义**。

生产实测（2026-11-11，只读探测）：

| 项 | 结果 |
|---|---|
| 副本定义 | 仍是**手抄版**（`core.shop_accounts` / `regexp_replace` 都在）⇒ **在自算** |
| 副本 / 正本行数 | 72 / 72，双向差集 **0 / 0** ⇒ *当前* 无功能影响 |
| 定义落后 | 副本比正本**少一条**口径（采集方代号不进候选池）⇒ 随时可能静默分叉 |

本版本用一次迁移把副本**重建**成「只从正本取数」，并加了**两道守护**：

1. **迁移自检**：重建后逐行比对副本与正本（不一致即抛错回滚），并校验副本定义
   **确实读正本、不得再有自算痕迹**；
2. **每小时巡检**：新增第五项「候选集副本口径健康」
   （`missing` / `drifted` / `diverged` / `ok`）⇒ 以后「改了正本副本不跟」会被**自动发现**，
   而不是靠「改口径的人记得重建副本」。

### 二、店铺身份「保未来」守护真的立起来

之前几个批次把**工具**造出来了，但**工具造好 ≠ 守卫生效**：
三个决定守卫生效与否的开关一个都没配，巡检在生产上永远 `skipped`，
隧道是一条**一次性** ssh 进程（上游静默约 90 秒后自己会死，且不会复活）。

本版本把这三件事补齐：

1. **三个开关真的配上**（本机与生产 `.env` 均已落地）

   | 开关 | 取值 | 为什么 |
   |---|---|---|
   | `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE` | `2026-12-01` | 云端 2026-11 的 unknown 占比高达 **56.69%**（那是事故现场）。分档按月 ⇒ 若配 2026-11-12，11 月整月会进「新问题」档、巡检**每小时都红**、告警当场作废；配 2026-12-01 ⇒ 2026-02~11 全归「已知历史遗留」不报警，12 月起才进守护区间 |
   | `SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD` | `0` | 默认 5% 会放过「新增月份只剩 1~2 行认不出」；设 0 后只要有 1 行就报（该月 0 行时比率 0，不报） |
   | `SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED` | `1`（开） | 复用批次 3.4 已有的站内信 / webhook / 钉钉三条通道；通知失败不影响同步 |

2. **隧道有看门狗了**：新增 `scripts/watch_cloud_sync_tunnel.ps1` ——
   探测 → 自愈（先清掉占着端口的僵死 ssh 进程，否则新进程会被 `ExitOnForwardFailure` 顶掉）
   → 留痕；并已注册成**每 2 分钟**跑一次的计划任务。它**只管隧道，不碰容器**。
   - **2026-11-12 修正**：计划任务动作改为 `conhost.exe --headless powershell.exe ...`。
     原写法在本机（默认终端宿主 = Windows Terminal）**每 2 分钟弹一次可见终端窗口**，
     用户无法区分「自家看门狗」与「被入侵」；`-WindowStyle Hidden` 挡不住（窗口由终端宿主创建）。
     改后实测 **0 个可见窗口**，隧道自愈与留痕行为完全不变。

3. **巡检的「看不见」变成留痕**：2026-11-07 事故的直接成因是**巡检永远 skipped**、
   而**没有任何一条记录**说明「我看不见」。现在云端不可达时会把结论写进
   **本地** `ops.pipeline_run_log`（云端那侧写不进去）；留痕失败**绝不掩盖**原异常，
   连接串口令**必须抹掉**。

### 三、顺带修掉的两个真问题

1. **巡检第五项的实现 bug**：`counts.one()` 被调用了两次，第二次抛
   `This result object is closed` ⇒ 真库实跑时该项恒为 `unknown`。
   已修；并把单测里的假 `Result` 改成**取过一次就关闭**，让同类 bug 在单测里就暴露。
2. **守护脚本开箱不可用**：两个只读验收脚本原来只读进程环境变量，直接在仓库根跑会报
   「DATABASE_URL 未配置」⇒ 改为在 import 数据库模块**之前**加载 `.env`
   （顺序很重要：数据库模块在 import 时就按 `DATABASE_URL` 建引擎）。

### 四、验证口径

- 本地开发库（PG 15.14）**真跑**迁移成功，迁移后副本定义已是
  `FROM semantic.shop_identity_resolution_candidates`，72/72 内容一致；
- 全新库迁移链契约 **10 passed**（自起 postgres:15 容器跑整条链到 head）；
- 全量回归 **6396 条 / 0 失败**，失败集 diff `NEW=0 / FIXED=0 / COMMON=0`；
- `black --check`（25.1.0，与 CI 同版本）/ `ruff check` 全绿；
- 新增契约守护 **31 条**（v7.20.1 的 7 条之外）。

### 五、遗留

- 用户侧待办：下一轮采集后核「**新增月份认不出 = 0**」
  —— ⚠️ 该指标**只能从 2026-12 起算**（11 月是事故现场，不是新增问题）。

## [v7.20.1] - 2026-11-11 - 矛盾行「能定位到行」+ 守卫契约与实现对齐（v7.20.0 的跟进热修）

> **零迁移、零数据改动**（只改代码与守护用例）。
>
> - v7.20.0 上线后的复核发现两处「**功能在、但用不起来**」的问题，本版本修掉；
> - 历史数据依旧**一行未改**（不回填、不重推）。

### 一、用户能感知到的修复

1. **手工重发入口现在真的能发出去了**（批次 4.3 的重发入口）

   - 之前：重发脚本按主键去读源行时，**只取了业务列、没取主键** ⇒ 真库自然不会把主键返回回来
     ⇒ 脚本把每一行都判成「源行已不存在」⇒ **一行也补发不出去**；
     而且它**不报错**，只是安静地跳过 ⇒ 人工看着像「源行没了」，实际是脚本自己认不出。
   - 另一处：同步的**生产路径**（源行 → 同步负载 → 身份闸门 → 矛盾行台账）会把源行主键**丢掉**
     ⇒ 台账里「源行主键」这一栏恒为空 ⇒ 就算脚本能定位，也定位不到行。
   - 现在：源行主键**一路带到底** ⇒ 台账里记下来的行，**现在真的可以按行精确定位并补发**。
   - ⇒ 批次 4.3 承诺的「被跳过的行不再消失、能手工重发」，到 v7.20.1 才真正兑现。

2. **云端登记信息读得到、但建索引那一步炸了时，不会再把整批数据卡住**（批次 3.7 双基准守卫）

   - 之前：云端两张表读到了，但「建反查索引」这一步抛异常时，异常会一路冒到同步任务
     ⇒ **整批数据不落云端**、任务判失败；
     而按设计，这时应该退回「只用本地登记信息」继续跑（行为与改造前完全一致）。
   - 现在：建索引失败也降级 ⇒ 退回本地单基准，同步照跑，
     只是这一轮不做跨端比较（并记一条「双基准不可用」事件）。

3. **口令脱敏更严**：口令里带**未编码的 `@`** 时，原先会剩下尾巴（`***@ss`）；现在整个抹掉。

4. **「部分行未落库」的说明补全**：兜底文案补上「或被双基准降级」（降级行并不是「矛盾」）。

### 二、内部修复（守护用例本身）

- 一条守护用例原本是**空转**的：它用的行内身份是「账号编码」，本地与云端本来就一样
  ⇒ 两边解释一致 ⇒ 压根不会去记事件 ⇒ 「记事件失败不阻塞同步」这条契约**一直没有测试保护**。
  已改成制造**真的不一致**（行内带平台编号），并断言事件记录器**确实被调用过**。
- 另补一条：事件记录器**整个**抛异常时也绝不阻塞同步（第二层兜底）。
- ⇒ 本版本新增 **7 条**守护用例、**改写 1 条**；每条都做过**负向验证**
  （把修复逐个回退 ⇒ 对应用例逐个变红）。

### 三、验证口径

- 两份守护测试全绿；
- 负向验证 **6 项**：修复逐个回退 ⇒ 对应用例**逐个变红**；
- 独立复核报告结论：**无阻断项**（10 个核实点里 8 项通过、2 项「应修」已在本版本修掉、
  4 项「建议」里 3 项已修）。

### 四、遗留（与 v7.20.0 相同）

- 律 3（候选名单副本物化视图）在**存量库**里仍是旧定义 ⇒ 需 DROP+CREATE 且下游被跟踪
  ⇒ 需专门维护窗口，本轮仍**不做**（已留档）。

## [v7.20.0] - 2026-11-11 - 店铺身份「保未来」四个批次全量上线 + 采集机台账已对齐 + 认人优先级收敛到一处

> **本版本含一次数据库迁移**（新增 `ops.shop_identity_conflict_rows` 台账表）。
>
> - 发布方式：打 tag `v7.20.0` → 触发官方 `deploy-production.yml` 流水线（`push: tags: v*`）→
>   构建镜像 → 部署生产；
> - 本版本的**业务主线**是「店铺身份保未来」：让**每一批新数据**都带着正确的店铺归属进库，
>   并且把「认不出」「卡住」「失败」「两端口径不一致」这四类问题**从哑的变成会报警的**；
> - **历史数据一行未改**（本轮不做任何历史回填、不重推 11 月）；
> - 采集机侧的**台账对齐已于 2026-11-11 实测执行完毕**（详见第五节）。

### 一、用户能感知到的修复

1. **店铺归属在两端口径不一致时，不再被默默推进到错的店下面**（批次 3.7，PR #15）

   - 之前：同步侧判断「这行属不属于某家店」**只看本地那一份店铺登记信息**（`core.shop_accounts` + `core.shop_account_aliases`）。
     但**云端也有一份登记信息**。两边不同步时（采集机本地台账与云端台账不一致），本地判「自洽」的行
     推到云端后，云端会用**云端**的登记去解释它 ⇒ 可能指向别的店 ⇒ **云端归属塌陷**（语义层落 `unknown`）。
   - 现在：推送前**再比一次**（云端登记信息 vs 本地登记信息）。
     - 两边一致 ⇒ **与改造前完全相同**，自洽行照常放行；
     - 两边不一致 ⇒ 该行**不再当自洽行直接放行**：不写云端，降级成**可观测事件**（记下来、可查、可计数）；
     - **云端连不上** ⇒ **退回本地单基准判定**（与改造前完全一致）+ 记一条「双基准不可用」事件。
   - ⇒ **云端连不上绝不会把同步搞挂**（三道闸：读云端登记全程吞异常、事件写入失败只打 warning、事件不参与写入事务）。
   - 业务含义：台账没对齐时，同步会**停在那张表**并明确报错（而不是把行按错的归属推进出去）。
     对齐本地台账后自动恢复；紧急止血可用环境变量 `SHOP_IDENTITY_DUAL_BASELINE_GUARD_ENABLED=0`。
   - 判定口径为什么这么定：比的是「**这行推到云端后会被算到谁头上**」，而不是逐字段比台账 ——
     逐字段比只能发现「编号登记错了」，发现不了「别名指错了 / 本地停用店云端还在」。
     两边用**同一份**认人实现（`shop_identity_reconciliation_service.row_identity_accounts`），
     索引由唯一台账声明 `modules/core/shop_identity_ssot.py` 派生 ⇒ 与「账号章优先」方向一致；
     **本地认不出（未归属）的行不做跨端比较** —— 没有可比对的基准，行为保持不变，
     不会把「待人工补主数据」的好数据当坏数据丢掉。
   - 守护：新增 **29 个用例**（`backend/tests/test_cloud_sync_dual_baseline_guard.py`）。

2. **被跳过的矛盾行不再消失：有台账了，也能手工重发**（批次 4.3，PR #16）

   - 之前（既有行为 P1-1）：同步的检查点推进到**最后一个落库行**，不是「最后一个连续自洽行」
     ⇒ 批次前部若有矛盾行，**那些行被跳过、永远不会被重发**（漏传）。
   - ⚠️ 但**不能**改成「停在第一个矛盾行」—— 那会让 `fact_shopee_products_daily` 永久卡在那 8 行之前
     （它们的归属永远不会被修），把「漏传」换成「堵死」。
   - 现在：**保持现有推进算法**（不制造永久卡死），额外把被跳过的矛盾行**逐行登记**进新表
     `ops.shop_identity_conflict_rows`，并标注「已知历史遗留 / 待人工处理」，
     另给**手工重发入口** `scripts/replay_shop_identity_conflict_rows.py`
     （**默认 `--dry-run`**，真执行必须显式 `--execute`；**默认不动「已知历史遗留」的行** —— 历史不修）。
   - 去重口径：`(源表, 业务日期, 行内定位, 原因码)` ⇒ 同一行再遇到只累加次数，不无限插行。
     **这一套同时修掉了批次 3.7 的「事件台账重复写」**，没有第二套口径。
   - 「已知历史遗留」判定复用批次 3.2 的 `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`
     ⇒ 未配置 ⇒ 一律归历史遗留 ⇒ **重发入口挑不出候选行**（脚本会提示）。
   - 本批次**一次真 PostgreSQL 验证**还揪出一个**假引擎测不出的 bug**：
     upsert 少绑了 `resolution_status`，假引擎不校验绑定参数所以单测是绿的，真库上整条 upsert 直接失败
     ⇒ 已修，并给测试替身补了绑定参数校验 + 加了回归用例。
     **教训**：DB 层逻辑光靠假引擎单测全绿**不等于** SQL 对。

3. **采集失败会主动报警，不再是哑的**（批次 3.4，PR #13）

   - 之前：采集失败只在日志里躺着，没人知道。
   - 现在：复用**现成的三条通道**（站内信 `create_notifications_for_admins` + webhook/钉钉
     `alert_service.send_resource_alert`；飞书投影与 `AlertRule` 不接 —— 后者只有 CRUD 无求值器）。
     **同一轮内的错误会聚类**（如「7 个店都挂在 `date option was not clicked`」），
     「等待验证码回填」**单独归类**，不与步骤失败混在一起。
   - 守护：新增 **20 个用例**。

4. **新鲜度告警不再永远红灯**（批次 3.3，PR #10）

   - 之前：阈值只有一套，「这条链现在还在不在采」不看 ⇒ 已下线的链一直报「不新鲜」。
   - 现在：阈值**按「这条链是否在当前采集范围内」分档**，范围来源**必须是采集器自己用的那一份**
     （`core.collection_configs.data_domains` / `core.collection_config_shop_scopes.data_domains`），
     **不另立第三份定义**；另加 `partial_success` 分级与通知出口。

5. **卡住的任务会被回收，而且留痕**（批次 3.5，PR #6）

   - 之前：只回收看板四族（封闭白名单）⇒ 任何**新增**的 run 族的僵尸行永远停在 `running`，
     监控表越积越多、盖住真正的失败。
   - 现在：改为**全族**（`status='running'` 且超阈值 ⇒ 一律回收），阈值 45 分钟（> 所有刷新队列任务的
     硬超时 30 分钟，不会误杀正在跑的长任务），并把被回收的 `run_id` / `pipeline_name` / 滞留分钟数
     **写进 `error_message`** ⇒ 不必回放日志就能读出「这条为什么变成 failed」。
   - 守护：新增 `backend/tests/test_refresh_queue_stale_run_reaping.py`。

6. **报表「认不出」的比例按月份分档**（批次 3.2，PR #7）

   - 之前：只报一个总比例 ⇒ 历史遗留和新增问题混在一起，看不出是「老账」还是「新账」。
   - 现在：按 `metric_date` 分档 —— 对齐生效日之前的历史月份归「已知历史遗留」**不报警**，
     之后超阈值才报。这是「历史不修」策略的**必要配套**。

7. **看板清单跑一次就一定收敛**（批次 3.6，PR #8）

   - 之前：跑一次和跑两次结果不一样（指纹写回的是上一次的实算值，且 CLI 早返回打断了顺序链）。
   - 现在：CLI 改成顺序链（核心 bootstrap 算指纹并回写 → 刷新物化资产 → 再回写指纹），
     并断言「写入的 applied == 本次算出的 expected」。

8. **采集机上的孤儿记账行可以先预览再清理**（批次 4.1，PR #12）

   - `scripts/bootstrap_postgresql_dashboard.py --prune-orphan-asset-state`，
     **默认 `--dry-run`** 先给「会删什么」的预览；**只删记账行**，不碰任何物化对象 / 视图 / 模块定义。

### 二、口径收敛（SSOT）

9. **「哪个身份信号最可信」从三个地方收敛到一处**（PR #9）

   - 之前：优先级写在**三个地方**（权威文件的散文、代码里的常量、两份 SQL 的优先级数字），
     而且**代码那份与权威文件的结论相反** —— 这是已确认的 bug。
   - 现在：新增 `modules/core/shop_identity_ssot.py` 作为**唯一台账声明**，
     Python 侧的 `SIGNAL_PRIORITY` 改为从它导出，SQL 侧加守护测试断言三者一致。
     （仓库已有先例：`COLLECTION_SOURCE_IDS` 的「唯一执行点」+ 两侧不漂移守护测试。）

10. **派生层口径收回：物化副本改为从正本取数**（律 3，PR #11）

    - 之前：候选名单的**正本与副本各写了一遍同样的 4 路 UNION** ⇒ 同一套口径有两份定义，
      迟早打架。
    - 现在：副本资产改成 `SELECT <8 列显式清单> FROM semantic.shop_identity_resolution_candidates`
      （**不用 `SELECT *`**，避免列序隐式跟随）；全新库从 baseline 建出来就是对的。
    - ⚠️ **已知例外**：**存量库**（本地与云端）的副本**仍是旧定义** —— 改迁移文件不会重跑已应用的迁移，
      而 `REFRESH` 只刷数据不改定义。**今天没有功能影响**（两端正本与副本都 72 行、内容指纹完全一致），
      解除条件见 `docs/superpowers/plans/STATUS.md` 的「已知未落地项」。

11. **入库侧改为「账号章优先」，采集导出路径加了反向守护**（批次 1，PR #3）

    - 入库收敛信号优先级改为 `shop_account_id` 优先 —— 这是**唯一能让后续每批数据不再重复犯错**的动作；
    - 采集导出路径加**反向测试**：主数据取不到编号时，shopee 导出路径的编号**必须留空**，
      绝不能回退到 `cfg["cnsc_shop_id"]` / `account["cnsc_shop_id"]` / `account["platform_shop_id"]`。

### 三、验证

- **失败集 diff 口径**（`scripts/diff_pytest_junit.py`，按失败集判绿、不按计数）：
  以本轮开工前的 `52d01608` 为基线跑全量 → 与合并后 main 的全量做差集 ⇒ **NEW = 0**。
- CI：`CI Pipeline` 全部 job 绿（含 `fresh-db-drill` / `migration-pg-contract` / `security-scan`）。
- 迁移链：全新 PG 从 baseline 两段式跑到 head 通过；`migration-pg-contract` 真库契约通过。

### 四、遗留（明写，不粉饰）

1. **律 3 在存量库里还没落地**（候选名单副本的定义）—— 解除条件与安全路径见 `STATUS.md`。
2. **输出键口径仍是平台编号优先**（报表最终填的那一列），与「归属判定」已改成账号章优先相反 ——
   被看板显示名映射表的键依赖锁死，改它会让显示名整片落空。解除条件是先解耦那个键依赖。
3. **「双基准不可用」事件仍会跨轮重复**（每轮一条，不是每行一条）。
4. **矛盾行通知出口默认关**（`SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`）⇒ 上线后行为与之前完全一致；
   不显式打开就没有人收到矛盾行告警。
5. **CI 的 `test (3.11)` 只跑「本次改动到的测试文件」** ⇒ 改了生产代码但没改对应测试替身时，
   红了没人看见（本轮实测踩到：批次 3.5 改了结果消费方式，守护测试从绿变红且一直红着，
   已由 PR #14 修掉并补了回归）。详见 `STATUS.md` 的「新增三个 CI 坑」。

### 五、采集机侧已完成的实作（2026-11-11，隧道 15433 在线）

| 项 | 实测结果 |
|---|---|
| 登记信息逐条比对 | 52 个账号，**50 条完全一致**；2 条差异**只在 `updated_by`**（本地是对齐工具的落款、云端是系统回填）—— **设计如此**（修改人由工具统一写，不接受云端的对齐值）。编号 / 状态 / 店名 / 启用 / 角色**逐条相等** |
| 待对齐账号 | **0** ⇒ 编号对齐此前已执行完毕 |
| 错别名 | 本地原有 2 条、云端 0 条 ⇒ 删掉 1 条与自家编号重复的冗余别名后，**待删清单清零** |
| 双认领 | 本地 **0**、云端 **0** |
| 历史事实行 | `b_class.fact_*` **67 张表行数 0 变化**；台账主表与候选池指纹均未变 |
| 别名认领数 | 1 → **0** ⇒ 别名路不再认领任何经营店的平台编号 |

**还差一步（需要人工）**：配置 `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`
（分档巡检的报警分界线；不配则一律不报警，宁可漏报不误报），
并在**下一轮采集**之后核「新增月份认不出 = 0」。

## [v7.19.5] - 2026-11-10 - 采集白名单对齐实际资产 + 迁移链 PG 契约进 CI 门禁 + 网关日志轮转 + Celery 派发隔离 + 服务器资产有界化

> **本版本已发布。**
>
> - 发布方式：打 tag `v7.19.5` → 触发官方 `deploy-production.yml` 流水线（`push: tags: v*`）→
>   构建镜像 → 部署生产；发版后的独立只读验收结论见
>   `docs/reports/2026-11-10-v7.19.5-生产发版记录.md`；
> - 本版本**零迁移、零数据改动**（不含任何 `alembic` 迁移改动）；
> - 本版本合并了两批内容：① v7.19.4 之后的**采集白名单对齐 + CI 三轮扩围**（15 笔提交）；
>   ② 本轮新增的**网关日志轮转 + 服务器回滚资产有界化 + Celery 派发移出事件循环**；
> - 运行时行为变化只有两处（下面都写明了）：**Celery 派发不再阻塞 API 事件循环**、
>   **服务器侧日志与备份开始有上限**。其余是白名单清理、CI 门禁扩围与 lint 修复。

### 一、用户能感知到的修复

1. **采集组件白名单不再声称「仓库里并不存在的组件入口」**
   - 之前：canonical 组件白名单（`backend/domains/collection/routers/component_versions.py`）里列着
     **3 个仓库里根本不存在**的文件：`shopee/orders_export.py`、`shopee/finance_export.py`、
     `miaoshou/export.py` —— 订单导出早已随「各平台订单统一走妙手采集」迁到妙手侧按平台分文件。
   - 现在：幽灵条目已删除，并加了守护用例
     `backend/tests/test_collection_component_topology.py::test_canonical_component_files_all_exist_on_disk`
     ⇒ 白名单里每个文件都必须真实存在于 `modules/platforms/<platform>/components/`，
     组件目录再变而清单没跟，随时变红。
   - 影响面（实测，非推测）：这份清单目前只被 `tools/test_component.py` 当**磁盘文件过滤器**用；
     `_is_canonical_component_file()` 走的是文件名**规则**、不看这份按平台的清单
     ⇒ **不造成运行时故障**，此前只是误导人（以为 shopee 还有订单导出入口）。

2. **根 `tests/` 里依赖真实 PostgreSQL 的契约用例，全部进入 CI 常态门禁**
   - 这是 v7.19.4 发版记录第七节遗留项 ① 的收口：此前这批用例**只能在本地跑**
     （CI runner 没有 15432 端口的 PG），口径漂移会潜伏好几天才被发现。

3. **Redis 抖动不再把全站一起拖住**（本轮最实质的一项）
   - 现象：Celery 任务派发原本在 API 的 **async 事件循环**里**同步**执行。
     Redis 一旦不可达，`send_task` 会按「连接超时 × 重试次数」把阻塞时间放大，
     而这段阻塞**占着事件循环** ⇒ 同一进程的所有接口请求一起卡住。
   - **先证伪再动手**（生产实测，非推测）：在生产 backend 容器内直接量 Redis 与派发耗时 ——
     Redis `PING` 中位数 **0.07 ms**、broker 建连 **1.31 ms**、
     完整 `send_task(..., ignore_result=True)` 中位数 **0.52 ms**（首次 16.97 ms 是建连）。
     ⇒ 台账里「运营等 4 秒」的说法**不成立**；4.1 s 是 **Redis 不可达时**的退化阻塞，
     真正要治的是**退化路径的阻塞会冻住全站**，不是常态延迟。
   - 现在（两条对策同时上）：
     1. **退化预算收紧**：`celery_app.py` 的 `socket_connect_timeout` **3 s → 1 s**、
        发布重试次数 **2 → 1** ⇒ 最坏退化阻塞从 ~9 s 压到 ~2 s；
     2. **派发移出事件循环**：新增 `backend/utils/celery_dispatch.py::dispatch_task()`，
        用 `asyncio.to_thread` 把发布动作挪到工作线程 ⇒ **即使 Redis 完全不可达，
        API 事件循环也不会被卡住**（其它请求照常响应）。
   - 落点：7 个 async 派发点全部改走 `dispatch_task`
     （`data_sync.py` ×4、`field_mapping_ingest.py` ×1、`collection_tasks.py` ×1、
     `data_ingestion_service.py` ×1）。
   - 语义不变：派发失败**照常抛异常**，既有「派发失败就不置成功标记」的语义**原样保留**。
   - 守护：`backend/tests/test_celery_dispatch_event_loop_isolation.py`（5 例）——
     用 AST 钉死「async 上下文里不许裸调 `.delay()` / `.apply_async()`」，
     再用行为级用例证明「派发阻塞 1 秒期间，事件循环心跳仍能跑 ≥5 轮」。
   - **没做的部分（明说）**：worker 内部还有 2 处同步派发点
     （`cloud_sync_auto_recovery_service.py:302`、`tasks/data_processing.py:176`）——
     它们本身就在同步上下文里，不构成事件循环阻塞，本轮不动。

4. **数据预览表格的「路径规范化 / 合并单元格还原」此前是静默失效的**
   - 根因：`backend/domains/data_platform/routers/data_sync.py:701` 引用了一个
     **从未定义**的名字 `runtime_file_path`（ruff F821，全文件仅此一处出现）。
   - 后果：该行抛 `NameError` ⇒ 预览返回的表格**既没做路径规范化，也没还原合并单元格**，
     页面显示的是未经合并的原表 —— 而接口**不报错**，属于「看起来有、实际没生效」的隐性缺陷。
   - 现在：改为正确的 `file_path`（同一函数内已定义的实参）。
   - 附带说明：CI 的 black/ruff **只对本次改动到的文件执行**，而 `data_sync.py` 本次已被改动
     ⇒ 必须把这条基线 lint 一起对齐。同批还清掉了 `collection_tasks.py` 的
     F841（`platform_stats` 查询算完从未使用，`TaskStatsResponse` 里根本没有 platform 字段）
     与 E712（`is_active == True` → `.is_(True)`）。

5. **服务器磁盘不再只增不减**（网关日志 + 回滚资产）
   - 实测生产：`/opt/xihong_erp/logs/nginx/access.log` **301.5 MB**、`error.log` 21.2 MB、
     日志目录合计 **475 MB**，且**没有任何轮转** —— 那是**宿主机 bind mount**
     （→ 容器 `/var/log/nginx`），容器重建也不清零；
     夜间实测增长 **738 字节/分钟**。磁盘 178 G / 已用 41 G（**24%**）⇒
     不是「快涨满」的紧急事，**真问题是没有上限**。
   - 现在（两条都带硬保护）：
     - **网关文件日志开始轮转**（配置进仓库、随部署包上机、由部署脚本安装）；
     - **回滚 / 暂存资产有了保留策略**。
   - 两条的完整规格与边界见「二、场景变化」第 6、7 条。

### 二、场景变化

1. **「迁移链在真实 PostgreSQL 上的契约守护」成为 CI 常态门禁**
   - 新增独立 job `migration-pg-contract`：跑
     `tests/test_current_schema_migration_postgres_contract.py`（10 例）。
   - **不需要 postgres service container**：这个文件的每个用例**自起**临时 `postgres:15` 容器
     （随机空闲端口），并把连接串通过 `env={**os.environ, "DATABASE_URL": <临时库>}` 传给迁移子进程
     ⇒ 只要 runner 有 Docker 即可。
   - 单独开 job（与 `fresh-db-drill` 并行）而不是塞进 `test` job：这条要 Docker + 约 4 分钟，
     放进 `test` job 会拖慢每次提交的反馈。

2. **纠正一处长期存在的错误判断**（此前把 CI 门禁挡在了门外）
   - 此前 `ci.yml` 与技术债台账都写「`test_current_schema_migration_postgres_contract.py`
     需要 `127.0.0.1:15432` 上的本地 PG」—— **这个判断是错的**：它不 import `tests/db_test_config`，
     全文也不出现 15432。
   - 真正依赖 15432 的只有两个文件：
     `tests/test_collection_config_core_schema_migration_contract.py` 与
     `tests/test_follow_investment_finance_schema_contract.py`（它们才 import `db_test_config`）。
   - 实测佐证：把环境 `DATABASE_URL` 指向一个**不可达地址**后本地跑该文件，仍是 **10 passed / 196.5 s**
     ⇒ 它不依赖环境连接串，也不依赖现成数据库。

3. **第二轮扩：连现成 PG 的那两个契约用例也进了 CI**
   - 给 `migration-pg-contract` job 加一个 `postgres:15` service 容器，并用
     `TEST_DB_HOST/PORT/USER/PASSWORD/ADMIN_DB` 指过去。
   - **不需要改任何代码**：`tests/db_test_config.py` 本来就支持这组环境变量覆盖、缺省仍是 15432
     ⇒ 本地行为完全不变。
   - 至此，根 `tests/` 里**依赖真实 PostgreSQL 的三个文件全部进入 CI 常态门禁**。
   - 实测（Ubuntu runner）：**12 passed**，**零 skip、零环境性红**
     ⇒ 是真跑，不是「连不上就跳过」的假绿。

4. **第三轮扩：不碰数据库的那 30 个文件也进了 CI**（no-DB 门禁从 12 个文件扩到 42 个）
   - 怎么证明它们真的不碰数据库：把 `TEST_DB_PORT` 指向**不可达端口 1**（`db_test_config` 走这条），
     同时把 `DATABASE_URL` 指向**不可达地址**（迁移器走这条）⇒ 任何真连库行为都会立刻失败。
   - 这样的「无 PG 可达」环境下本地跑 = **225 passed / 37.2 s**、零 skip、零失败
     ⇒ 在 CI runner 上不会变成环境性红。
   - **本版第四轮扩：42 → 45 个** —— 把本轮的 3 个守护文件
     （Celery 派发隔离 5 例、既有派发韧性 10 例、部署资产契约 16 例）也并进常驻清单
     ⇒ 这三条护栏从此**每次 CI 都跑**，不再只在「相关文件被改动」时跑。

5. **两处 `ComponentVersion.is_stable == True` 改为 `.is_(True)`**
   - PostgreSQL 下 `IS true` 与 `= true` 的**筛选结果完全一致**（两者都排除 NULL 行）
     ⇒ 语义不变，同时不再触发 ruff E712。

6. **网关文件日志开始轮转**
   - 链路：配置进仓库（`nginx/logrotate-xihong.conf`）→ 随 `scripts/build_deploy_bundle.sh`
     的 tar 包落到生产机 `/opt/xihong_erp/nginx/` → 部署脚本安装。
   - 规格：`daily` + `rotate 7` + `maxsize 100M` + `missingok` + `notifempty` +
     `compress` + `delaycompress` + **`copytruncate`** + `create 0644`（不写 owner/group）。
   - 为什么必须 `copytruncate`：nginx 进程在**容器内**持有这两个文件的句柄，
     常规 rotate（改名 + 新建）会让容器继续往旧 inode 写 ⇒ 只能原地截断。
   - **实测出来的两个坑（都已处理）**：
     1. **`logrotate -d` 的退出码会假绿**：配置对 group/other 可写时，它打印
        `error: Ignoring <conf> ...` 但**退出码仍是 0** ⇒ 只判退出码会把「没装上」
        误判成「装上了」。脚本改成同时检查输出里有无 `error:` / `Ignoring `
        **和**正向证据 `reading config file`。
     2. **生产上 `/etc/logrotate.d` 装不上**：流水线是以 `deploy` 用户（uid 1002）跑的，
        `/etc/logrotate.d` 是 `root:root 755` ⇒ 写不进去；`sudo` 在非交互会话里要密码用不了。
        ⇒ 脚本做了**两级降级**：主路径仍按标准装 `/etc/logrotate.d/xihong-nginx`，
        装不上 / 被 logrotate 拒绝就自动降级到**用户级 cron**（每晚 03:17 跑
        `logrotate -s /opt/xihong_erp/logrotate.state /opt/xihong_erp/nginx/logrotate-xihong.conf`），
        **让轮转真的生效**，而不是装个摆设；哪天标准路径能生效，脚本会自动把兜底 cron 撤掉。
   - 兜底 cron 的安全约束（生产 `deploy` 的 crontab 里有 **acme.sh 证书续签**任务）：
     **只追加自己的标记块**、写回前备份、写回后**逐条校验「原有条目一条都不能少 + 新条目在」**、
     不满足就**还原**；并且**按块整体删除** —— 第一版只删两行标记、块里那条命令会残留
     ⇒ 每发一次版多一条重复任务，这个坑已由守护用例钉死。
   - 失败语义：轮转是**收尾工作、不是发版前提** ⇒ 任一步失败只 `[WARN]` 跳过，
     **绝不让发版失败**。
   - 实测（真实路径）：110 MB → 原文件变 0 字节 + 生成 `.1`、属主/权限不变；
     二次运行不重复转（`notifempty` 生效）。

7. **回滚 / 暂存资产有了保留策略**
   - 实测生产：`backups/` 下 **91 个条目 / 213 MB**（其中 85 个 `pre_deploy_*` 多为 32 K 空壳），
     根目录 `frontend_stale_20261110_025258` **313 MB** ⇒ 只增不减。
   - 规则（`KEEP_BACKUPS_COUNT` / `KEEP_OTHER_BACKUPS_COUNT` 可用环境变量覆盖）：

     | 资产 | 规则 |
     |---|---|
     | `backups/pre_deploy_*` | 保留最近 **3** 个 |
     | `backups/pre_manual_deploy_*` / `pre_maxconn_*` / `manual_*` | 各保留最近 **1** 个 |
     | `backups/` 下的独立 `*.dump` 文件 | **一律不删**（来源不明，可能是手工排查留下的现场） |
     | 根目录 `frontend_stale_*` | **全删**（回滚靠镜像，不靠源码树） |

   - 安全硬约束：
     1. `PRODUCTION_PATH` 为空或 `/` ⇒ **拒绝执行**；
     2. **只删目录**（`find -type d` + `*.dump` 显式排除，三重保护）；
     3. **本次发版刚创建的备份绝不删** —— 两条保护：① 脚本内记录的精确目录；
        ② 时间戳落在发版窗口 **±300 秒**内的（兜住流水线在跑脚本**之前**创建的那个
        `pre_deploy_*` —— 实测 v7.19.4 那次就产生了两个 `pre_deploy_*` 目录）；
     4. 目录名里时间戳解析不出来的 ⇒ **一律不删**（保守）；
     5. 每条删除 `|| true`；删不掉就打 `[WARN]` 且**不计入回收量**（不虚报）；
     6. **只在 `DEPLOYMENT_CUTOVER_COMPLETE=1` 之后调用** ⇒ 失败回滚路径上不删任何东西。
   - 保留数 3 的实际语义：每次发版会产生**两个** `pre_deploy_*` 目录（流水线的 compose 快照 +
     脚本的带 dump 备份）⇒ 保留 3 个 ≈ 保住**上一个版本的带 dump 备份**（对回滚真正有价值），
     没 dump 的 compose 快照会被裁掉。数字可用 `KEEP_BACKUPS_COUNT` 环境变量调整。

8. **两项产品决策被记成待办，本版不动代码**
   - 「采购 / 报表两个页面的归属」与「订单正式账本写入路径尚未实现」
     **不是技术缺陷，是产品口径未定** ⇒ 写成
     `docs/reports/2026-11-10-产品决策待办清单.md`（一句话问题 + 不回答的后果 +
     答案定了之后的动作），交产品拍板，**本版不猜、不改**。

### 三、为什么必须常态化

这里守着 20261215 回填「**跳过并记日志**」的语义。口径一旦漂移（例如有人把回填谓词放宽），
老库升级会重新卡在只读触发器上——而这类问题**只有跑在真 PG 上才暴露**
（2026-11-10 的那一次就是靠它抓出来的，而不是等发版炸生产）。

### 四、验证与生产影响

| 检查 | 结果 |
|---|---|
| `CI Pipeline` | **success**，8 个 job 全绿（run `42792941298`，head `34d73a32`） |
| `migration-pg-contract` | **12 passed、零 skip**（真跑，不是「连不上就跳过」的假绿） |
| `test (3.11)`（no-DB 门禁 **45** 个文件） | **380 passed / 10 skipped**；10 个 skip 来自**平台门控**（PowerShell 专有文件在 Ubuntu 跳过 + 需要真实账号的 e2e），不是环境性红。本版把 **3 个**派发/部署守护文件并入常驻清单（42 → 45，**+31 例**） |
| `Docker Build and Push` / `Validate Data Flow` | success |
| 本轮新增守护用例（本地全量） | **31 passed** —— Celery 派发隔离 5 + 既有派发韧性 10 + 部署资产契约 16 |
| `black --check` / `ruff check`（本次改动到的 8 个 .py） | **零差异** / `All checks passed!` |
| 部署脚本 `bash -n` 语法检查 | 通过（最终改动后重跑） |
| 生产数据影响 | **零迁移、零数据改动**（本次不含任何迁移改动） |

**生产侧验收（独立 SSH 只读实测，2026-11-10T10:05–10:10Z）**

| 检查 | 结果 |
|---|---|
| `Deploy to Production (Tag Release)` | **success**，10 m 8 s，全部步骤 ✓ |
| 容器 | **7/7 healthy**，镜像全为 **v7.19.5** |
| `/api/health` | `healthy`、`version=v7.19.5`、`database=connected`、`dashboard=ready`、路由 630、连接池 `size=30 / checked_out=1` |
| 库版本 | `current_schema_20261223_collection_source_identifiers` —— **未变** |
| 数据库连接 | **18 条恒定**、`idle in transaction` **0**；最老连接龄每次采样 **+20 s = 采样间隔** ⇒ 无泄漏 |
| 报错 | 切流后 backend / worker / beat / nginx / frontend **零 traceback** |
| 派发耗时 | 切流后 `send_task` 中位数 **0.477 ms**（发版前 0.52 ms）⇒ **无回归**；Redis `PING` 中位数 0.682 ms |
| 派发点 | 容器内 **7 个生产派发点**已全部 `await dispatch_task`，async 上下文无裸 `.delay()` / `.apply_async()` |
| 服务器资产 | `backups/` **91 → 9 条**、回收 **352 MB**（313 MB 陈旧前端树 + 39 MB 空备份壳）；`pre_deploy_*` 恰好留 3 个（含 v7.19.4 的带 dump 备份）；其它前缀各留 1；**2 个独立 `.dump` 字节数不变**；无关目录未误删 |
| 网关日志轮转 | 主路径 `/etc/logrotate.d` 因**部署身份无写权限**装不上（预期内）⇒ **用户级 cron 兜底已生效**，且**用户原有 acme.sh 证书续签任务完好**；配置文件已上机；首次轮转在当晚 03:17 |

> 完整验收明细见 `docs/reports/2026-11-10-v7.19.5-生产发版记录.md`。
>
> **已知剩余（1 条）**：部署镜像里 `celery_app.py` 的**文件头注释**仍写着旧的「3 秒 / 2 次」
> （本版只改了代码、漏改那段说明）—— **运行期行为完全正确**（容器内实测就是 1 秒 / 1 次），
> 已在 tag 之后于 `main` 修正；因 **tag 不可变**，v7.19.5 镜像中的注释保持原样，随下一版本带上。

> **首次发版 CI 抓到的真问题（已修）**：第一轮 CI 里 `test (3.11)` **红在两个既有
> fail-closed 守护用例**上 —— `backend/tests/test_remote_deploy_migration_contract.py`
> 与 `tests/test_prod_release_fail_closed_contracts.py`。它们用 `script.index(...)` 取
> **字面量的首次出现位置**，而本轮新增的**说明性注释**里出现了同样的标识符
> （`DEPLOYMENT_CUTOVER_COMPLETE=1`、`perform_pre_migration_backup`）⇒ 锚点被提前，
> 断言「健康检查/备份必须在前」因此误判为红。**不是新代码的行为问题。**
>
> 处理原则：**不动既有守卫**（守卫的语义与牙齿完全不变），改的是本轮自己新增的
> **注释措辞** ⇒ 两个守卫的锚点复位。复跑 45 文件门禁 = **388 passed / 2 skipped**
> （本地；CI runner 上 skip 数因平台门控不同而不同，用例总数一致 = 390）。
>
> 遗留（**本版不做**）：这两个守卫对「文件里首次出现某字面量」敏感 ⇒ 以后任何人
> 在脚本前部写注释提到这两个标识名，CI 都会误红。彻底修法是把锚点改成
> 「按行匹配赋值/调用」而不是「按字面量首次出现」，但那属于改既有 fail-closed
> 守卫，按发版期规则不在本版夹带 ⇒ 已单独记录为技术债。

> 上表 CI 行取自**发版代码本身**的那次 run（run `42792117622`，commit `0451943d`）；
> tag `v7.19.5` 所在的提交与它**只差本 CHANGELOG 的文字**，代码完全一致 ⇒ 数字可直接继承。
> **生产侧**的验收结论见 `docs/reports/2026-11-10-v7.19.5-生产发版记录.md`。

- 白名单清理只影响采集组件清单的**准确性**；`IS true` 与 `= true` 筛选结果一致
  ⇒ **运行期行为不变**。
- CI 门禁与文档改动**不影响生产运行时**。
- **运行期行为变化只有两处**：
  1. Celery 派发改走 `asyncio.to_thread`（**发布时机、参数、失败语义全部不变**，
     只是不再占用 API 事件循环）；
  2. 服务器侧开始有**日志轮转上限**与**备份保留上限**（只影响磁盘占用，不碰业务数据）。
- 数据预览表格的路径规范化 / 合并单元格还原此前**静默失效**，本版**恢复生效**
  —— 这是**修复**，不是行为变化。

## [v7.19.4] - 2026-11-10 - 空库能从零建起来 + 老库升级不再卡在触发器 + 测试目录不再静默腐烂

### 一、用户能感知到的修复

1. **全新环境从零建库：不再撞「账号不存在」**
   - 现象：`current_schema_20261116_add_tiktok_export_store_name_aliases` 是数据修复型迁移，
     它要求 6 个 TikTok 出口账号**已经存在**（fail-closed 前置检查）。
     空库上这些账号不存在 ⇒ 整条链在该步中止，实测报错是 6 条「账号不存在」。
   - 现在：提供**两段式引导**（`scripts/bootstrap_fresh_environment.py`）——
     先升到 20261116 的前一个节点 → 注入引导账号（主账号 + 6 个店铺账号）→ 再升到 head。
     真实环境用**运维清单**（真实凭据 + 真实显示名），占位值只允许一次性临时库使用。
   - 空库直接跑链会被**写路径守卫**挡下，并给出可执行的指引（读路径契约不变）。

2. **老库升级不再卡在「historical operation breakdowns are read-only」**
   - 现象：带 legacy operation 型父目标历史行的库，升级走到 `20261215` 时，
     只读触发器（`a_class.enforce_operation_breakdown_contract`）与该迁移的回填 UPDATE
     直接冲突 ⇒ 抛错、链断（老库升级路径**必然失败**）。
   - 口径（产品拍板，2026-11-10）：没有 `metric_catalog_version` 的 operation 型父目标下的
     历史档位行**本来就不该被补** `period_label` / `period_start` / `period_end`。
   - 现在：该迁移的回填范围**收窄**到「可改」的父目标，这批历史行**显式跳过**，
     跳过的行数**写进迁移日志**（不静默漏改，避免被误读成「数据漏改」）。
   - 影响面：只影响**尚未应用该迁移的库**（老库升级路径）；已应用该迁移的库（含生产）
     alembic 不会重跑 ⇒ 行为完全不变、历史数据零改动。

3. **模板 Data Hash 体检的两条用例按规格 D1 更新**
   - 规格 D1（2026-11-07 业务拍板）：指标类字段（`visitor_count` 等）**可以**参与
     `data_hash`（不推荐 + 带后果提示），由用户勾选决定。
   - 批次 E 落地 D1 时**漏改**了 `tests/unit/test_template_hash_hygiene_audit.py`，
     两条用例还在断言旧口径（「度量字段一律被剔除」）⇒ 长期红、没人跑这个目录。
   - 现在：按 D1 重写（工作台保留度量字段 + 标记不推荐 + 带 warning；
     只剩度量字段时闸门仍拦，但理由改成「缺 `product_id`」）。

### 二、场景变化

4. **CI 从此常态化跑两类此前没人跑的目录**
   - `tests/unit/`（139 例，约 3 秒，不碰数据库）；
   - 根 `tests/` 里**不依赖数据库**的契约/巡检用例（12 个文件，约 10 秒）；
   - 外加独立 job：**「空库从零建库」全链演练**（Docker + 临时 Postgres，约 7 分钟）。
   - 起因：CI 此前只跑「本次改动到的测试文件」⇒ 这两个目录的用例长期不跑，
     口径漂移导致的红能潜伏好几天才被发现（2026-11-10 实测：根 `tests/` 里有 33 条）。

5. **根 `tests/` 目录的 33 条过期红已清到 0**
   - 删掉失效文件 `tests/test_metabase_question_service.py`（被测服务已随 Metabase 退役删除）；
   - 按现行实现重写 19 条过期断言（执行器容错机制 / TaskService 现行 API /
     resume 接口鉴权覆盖 / ORM SSOT 分段 / 发版版本口径 / 镜像同步脚本 / 云同步载荷溯源）；
   - 修 3 条指向已删除采集组件的用例（订单导出已迁到 `miaoshou/orders_shopee_export`）。

### 三、已知遗留（不掩盖）

- **canonical 组件白名单与实际资产不同步**：`component_versions.py` 的白名单仍列着
  `shopee/orders_export.py` 与 `shopee/finance_export.py`，而这两个文件在仓库里不存在。
  白名单只是「允许注册的名字」，当前**无功能影响**，留作后续清理。
- 根 `tests/` 里依赖本地 PostgreSQL 的那部分契约用例**没有**进 CI
  （CI runner 没有 15432 端口的 PG），需要时另配服务容器。

## [v7.19.3] - 2026-11-10 - 仓码与采集方代号各收敛成单一真相点 + 迁移失败可诊断

### 一、用户能感知到的修复

1. **库存语义层不再把「采集方代号」当成店铺身份**（4,111 行）
   - 现象：`semantic.fact_inventory_snapshot` 的 4,111 行全部挂在伪店 `xihong` 上，
     `resolved_shop_account_id` 全为 NULL —— 采集机（妙手账号 `miaoshou_real_001`）
     被当成一家店注册进了 `core.dim_shops`。
   - 现在：未归属的行如实表达 `shop_id = 'unknown'`（不再冒充一家店），
     `resolved_shop_account_id` 保持 NULL。**b_class 事实表的 `shop_id` 列保持
     `xihong` 不动** —— 它是 upsert 冲突键，改值会插重复行。
2. **同步侧不再把采集方代号混进店铺身份候选集**
   - 以前这条规则写在 `orders_atomic.sql` 的**字面量**里，漏抄的链路（库存链）
     就会把代号当成店铺身份。现在规则收敛到候选池正本一处，
     所有链路（含未来新增的）自动继承。
3. **仓码归一只有一个实现**
   - 新建 `semantic.resolve_warehouse_code(仓名)`，建在 `core.dim_warehouse_name_aliases`
     之上；语义层、状态层、Metabase 模型与 Python 归一器共用同一函数
     （以前 Python 侧自己维护了一份字典逻辑）。
   - 实跑口径：语义层 4,111/4,111、`mart.inventory_state` 1,232/1,232、
     `mart.inventory_backlog_base` 512/512 仓码全部有值。
   - 顺带修了 bootstrap 漂移：`mart.inventory_state` 补回 `warehouse_code` 列与索引
     （该列原先只有迁移加过、SQL 资产没同步）。

### 二、机制上的变化

4. **采集方代号有了登记载体**（`core.collection_source_identifiers`）
   - 唯一执行点 = 候选池正本构建时剔除；判定函数
     `semantic.is_collection_source_identifier()` 内联在候选池资产开头
     （迁移 `20261112` 会直接执行该资产，函数必须与它同生共死）。
   - 登记表不存在时函数返回 FALSE（不剔除任何值）⇒ 老库 / 半迁移库照常建视图。
5. **仓名别名可以维护了**
   - 新增 `GET/POST/PUT/DELETE /api/warehouse-name-aliases`（`require_admin`），
     仓码须存在于 `core.dim_warehouses`，改动后自动重算 `mart.inventory_state.warehouse_code`。
6. **迁移失败不再是「一句没信息的话」**
   - `scripts/run_current_schema_migrations.py` 以前不捕获 alembic 子进程输出，
     失败只报 `upgrade head failed (1)`，真实原因（PG 报错 / 前置检查失败）
     只留在子进程 stderr 里。现在失败原因会带进异常消息（部署日志不丢）。

### 三、清理

7. 删除 `postgresql_dashboard_service.py` 里两个**全仓零调用**的 join 键函数
   （顺带确认了「库存↔销售按店 join 不上」的担忧并不成立）。

### 四、验证

- 采集链路指纹对比：orders / analytics / products / services 与候选池正本及副本
  **完全一致**（口径不回归）；inventory 的变化符合预期（`shop_id` 恒 `unknown`）。
- 同范围失败集 diff（`tests/` 全目录，两侧同样 634 个用例）：**NEW failures = 0**。
- 新增守护测试 57 项全绿（仓码 SSOT 18 + 仓名别名 API 8 + 云同步完整性 10 +
  接收日志诚实化 9 + 枚举归一 9 + 身份索引注入 3）。
- 迁移契约测试：补上 `20261116` 要求的数据前置后，该文件 4 passed / 6 failed →
  **9 passed / 1 failed**；同时修掉了「Windows GBK 解码把中文报错吞成
  `AssertionError: None`」这个让排查无从下手的诊断问题。

### 五、已知剩余（不粉饰）

- **1 个失败保留真红**（不加 xfail 掩盖）：触发器
  `20260810_operation_contract_isolation.py:188`（父目标 `metric_catalog_version IS NULL`
  ⇒ `target_breakdown` 只读）与迁移 `20261215_migrate_sales_targets_a.py:365-374`
  （正要去 UPDATE 这批历史行补 `period_label`）直接冲突，迁移里没有
  `DISABLE TRIGGER` 处理。**生产影子库演练与本地 dev 库都没有这类行**，
  风险不落在生产；这是测试故意造了生产没有的脏数据才暴露出来的健壮性缺口，
  留作发版后的独立立项。
- 仓库既有 `tests/unit/test_template_hash_hygiene_audit.py` 2 个失败
  （度量列未从去重字段里剔除）是另一个独立缺口，本批未动。

## [未发布] - 连接泄漏根治 + 慢查询根治 + 发版链加固

> 本节来自一次**生产只读调查**（2026-11-09）。调查结论是：生产库 80 个连接槽位
> 全部被占满且只增不减，业务随机 500。根因在代码里——「异步任务怎么收尾」
> 这件事没有唯一做法，有人只把连接池「标记作废」而不真正关闭连接。
> 本节把这件事彻底改掉，并顺手修掉沿路查出来的两个真 bug。

### 一、用户能感知到的修复

1. **生产数据库连接被"漏光"，接口随机 500**（本节最严重的一项）
   - 现象：生产库 80 个连接槽位全部占满，且**只增不减**（实测约 0.75 条/分钟）；
     最早一条连接已存活 8 小时 27 分钟；这些连接的最后一条 SQL 是 `COMMIT;`
     ——事务已提交，**连接本身没关**。
   - 原因（比「忘记关连接」更深一层）：asyncpg 的连接绑定在**创建它的事件循环**上，
     而同一个全局 async 引擎被三个**不同的**事件循环共用
     ——FastAPI 主循环、后台线程自建的循环、Celery 每个 task 新建的循环。
     循环 A 建的连接被循环 B 取出时 pre_ping 必然失败
     （`Event loop is closed` / `'NoneType' object has no attribute 'send'`），
     连接被丢弃；但因为原循环已结束，**close 同样失败** ⇒
     TCP 连接滞留在数据库服务端白占槽位。旧写法 `dispose(close=False)`
     只是把连接池「标记作废」，既不关连接，也堵不住这个跨循环复用。
   - 现在：**异步引擎按事件循环分发**——每个事件循环有自己的引擎和连接池，
     连接**永不跨循环复用**；短命循环（Celery task / 后台线程）在任务结束时
     由全仓库**唯一**的异步出口
     `backend/utils/async_task_runner.py::run_async_task()`
     在事件循环**还活着**的时候真正关闭它（`await engine.dispose()`），
     并把它从注册表摘掉——连接跟着循环一起走。
     9 处 Celery 调用点、云同步轮询、缓存失效入口全部改走这个出口。
   - 为什么不图省事改成 `NullPool`（它也能消除跨循环复用）：
     `NullPool` 没有连接池，每次会话都要重新握手 ——
     **生产容器实测 14.21 ms/次，而池化只要 1.79 ms/次（8 倍差距）**。
     按事件循环分发既根治泄漏，又保住连接复用，接口延迟不受影响。
   - 证据：
     - 新增**泄漏回归测试**（`backend/tests/test_async_engine_connection_leak.py`）：
       连跑 8 轮任务，断言 `pg_stat_activity` 连接数不增长；
       配套的「证伪自检」把旧写法原样搬进独立子进程跑，确认探测器确实有牙齿
       （旧写法实测：4 轮任务后连接数 0 → 4，只增不减，与生产症状一致）；
     - 新增门禁 `scripts/verify_async_loop_cleanup.py`：禁止裸 `asyncio.run(`、
       禁止 `dispose(close=False)`、禁止业务代码再调用只软丢弃的兜底函数、
       **并禁止「自建会话不关闭」**（R5，漏关一条会话就是漏一条连接）；
     - 顺带修掉两个把 workaround **固化成契约**的测试断言
       （`assert called["close"] is False`）——它们让谁都不敢改真正的根因；
     - 顺带堵掉 `backend/services/audit_service.py` 三处「自建会话从不关闭」
       （全仓 30 个调用点不传 `db=`，每次审计都漏一条会话）。

2. **两条迁移的「回滚之后再升级升不回去」被修掉**
   - `current_migrations/versions/20261221_collapse_duplicate_columns.py`
     - 现象：降级重建的列一律用 `TEXT`，而原列是 `double precision` / `varchar(32)`；
       再升级时 `UPDATE ... SET "work_hours" = "工作时长"` 类型不匹配直接报错 ——
       **回滚之后再也升不回去**（生产影子库实测复现）。
     - 现在：按**原始类型**重建，并新增「来源列与目标列类型不一致就拒绝执行」
       的 fail-closed 检查（`text → varchar` 会静默截断，必须挡在门外）。
   - `current_migrations/versions/20261215_migrate_sales_targets_a.py`
     - 现象：降级把隔离区里被跳过的 9 行放回业务表，却**没删隔离区里的副本**；
       来回跑一次隔离区就从 9 行涨到 18 行。
     - 现在：放回后清理隔离区副本；升级前也先清理同源旧记录 ⇒ 幂等。
   - 验证：在**生产备份还原出的影子库**上跑完整往返
     `20261211 → head → 20261214 → head`：
     `a_class.target_breakdown` 稳定 241 行、隔离区 18 → 0 → **9** 行、
     被隔离的 3 个店铺金额合计 990429.2 与跳过前完全一致。

3. **「未匹配店铺别名」接口慢到超时 → 改读物化视图**
   - 实测（本地同一段查询）：普通视图 **23.53 秒** → 物化视图 **0.30 秒**，
     两者结果**完全一致**。生产更严重：物化视图的创建脚本里记录过
     `SELECT count(*) FROM semantic.fact_orders_atomic` 要 **114.6 秒**。
   - 口径不变：物化视图正文就是普通视图正文（全字段透传），只改「什么时候算」，
     不改「算什么」。
   - 附带：别名改动后的刷新目标补上 `semantic.fact_orders_atomic_mv`
     ——否则用户刚认领完别名，列表里还挂着它。
   - ⚠ 这里推翻了一个此前的方案：原计划给 9 张事实表建「空店铺」部分索引。
     实测证明**它救不了这条查询**（过滤的是视图出口的裁决结果，是表达式，
     谓词下推不到事实表；而改用源表原始 `shop_id` 过滤又是**另一批数据**，
     口径会变）。因此该索引方案已撤销，改为上面这条真正有效的修法。

4. **订单入库「回成功」但正式账本一行都没有**
   - 现象：订单文件入库后，接口给不出可信结论，正式账本始终为空。
   - 原因（两层）：
     - 旧实现在循环里 `return`，等于**结束整个函数**并返回 `None`；
       调用方 `total_imported += imported` 抛 `TypeError`，被上层当成「文件处理失败」，
       真相被彻底掩盖；
     - 更深一层：`upsert_orders` 是 `async def` 却**没有 await** 内部的
       `upsert_orders_v2`，返回的是**协程对象**——这才是这条链路失败的真正根因。
   - 现在：返回 `OrdersImportResult`（int 子类），显式携带 `fact_imported`
     与原因说明；两个路由与 Celery 任务的响应里都有
     `orders_fact_imported` / `orders_fact_note`。
     **不抛错**——抛错会回滚暂存数据，运营连文件都传不进去。

5. **前端 10 个红项逐条定性并清零**
   - `frontend/scripts` 340 个用例 → **0 失败**（`frontend/tests` 184 个仍全绿）。
   - 其中 1 条是本轮令牌收敛带来的**有意的行为变更**（WebSocket 不再从
     localStorage 取令牌），断言随之更新，**不回退代码**。
   - 门禁升级：`scripts/ci_frontend_test_silence_gate.py` 从「只拦哑测试」
     升级为「**有失败即拦**」——红灯一旦成为常态就等于没有红灯。

6. **Redis 一抖，整个 API 一起挂起（16~17 秒）**
   - 现象：派发一个 Celery 后台任务时，接口**卡住十几秒**才返回；
     在 async 上下文里，这等于**整个事件循环被冻住**，所有并发请求一起挂起。
   - 根因（比「Redis 连不上」深一层）：`task.delay()` 并不只是「把消息发到
     broker」——Celery 在 `send_task()` 末尾会回调 `backend.on_task_call()`，
     Redis 结果后端在这里**同步订阅**该任务的 pubsub 通道。
     也就是说**每次派发任务都要额外连一次 Redis**，而且是**阻塞式**连接。
     Redis 不可达时，kombu 的重试还是**嵌套**的（外层 `reconnect_on_error`
     套内层 `ensure()`，各 20 次 × 1 秒）⇒ 实测单次 `delay()` **阻塞 16~17 秒**。
   - 现在做了三层：
     - **不需要结果的任务声明 `ignore_result=True`**（图片提取任务就是这种——
       它的返回值无人读取），从根上**跳过那次多余的 pubsub 订阅**：
       实测 **12.7 秒 → 4.1 秒**；
     - **派发侧的连接超时与重试次数全部设上限**（`backend/celery_app.py`）：
       建连最多 3 秒、发布重试最多 2 次。Celery 原生默认是
       `broker_connection_max_retries=100`、结果后端重试 20 次 × 1 秒。
       **Redis 正常时派发耗时完全不变**（实测 0.036 秒），只是「连不上」时
       立刻失败、立刻让位，而不是慢慢失败；
     - **测试护栏把 Celery 钉成内存 transport**（`memory://` /
       `cache+memory://`）⇒ 测试**永不连真实 Redis**，也永不再出现
       「跑到 44% 静默挂死、CPU 零增量」的现象。
   - 顺带修掉派发点的两个真 bug：`except (ImportError, Exception)` 让紧随其后
     的 `except Exception` 成了**死代码**；且派发**失败**时却把
     `image_extraction_started` 置 `True`，导致接口对外回「图片提取 processing」
     而任务其实根本没派出去。现在只有**真的派发成功**才置 `True`。
   - 顺带修掉一个**在干净环境必然失败**的测试：
     `test_utf8_editor_guardrails_are_declared` 要求 `.vscode/settings.json`
     存在，而那个文件被 `.gitignore` 排除、**从未进过版本库**（基线 commit
     `419b4436` 里也没有）⇒ 任何干净 checkout 跑它都必红。现在改为断言
     **受版本管理**的 `.editorconfig`（真正的仓库级护栏），
     VSCode 本地设置改为「存在时才校验」——并已做证伪自检：
     故意写错时测试确实会红，不是把断言放水。

### 二、机制上的变化：这些坑不会再悄悄坏回去

| 门禁 | 拦什么 | 触发时机 |
|---|---|---|
| `verify_sync_query_usage.py` | 异步上下文里的同步 `db.query()` | CI |
| `verify_access_token_extraction.py` | 绕过唯一令牌提取点 | CI |
| `verify_orm_schema_drift.py` | ORM 有、库里没有的列 | 发版前 + CI |
| `verify_async_loop_cleanup.py`（新） | 裸 `asyncio.run` / `dispose(close=False)` / 自建会话不关闭 | CI |
| `ci_frontend_test_silence_gate.py`（升级） | 前端测试静音或失败 | CI |
| `test_unmatched_alias_reads_materialized_view.py`（新） | 慢查询退回普通视图 | CI |
| `test_orders_import_status_honesty.py`（新） | 入库接口再返回 `None` 冒充成功 | CI |
| `test_async_engine_connection_leak.py`（新） | 连接数增长 | CI |
| `test_async_engine_pool_isolation.py`（新） | 引擎不再按事件循环分发 / 丢掉连接池 | CI |
| `test_migration_collapse_duplicate_columns.py`（新） | 迁移回滚后再升级升不回去 | CI |
| `test_celery_dispatch_resilience.py`（新） | 派发任务又把事件循环冻住 / 测试又连上真实 Redis | CI |

### 三、已知剩余

1. **生产库连接上限偏小**（`max_connections=80`）与**日志无轮转**
   （容器内 access.log 51MB / error.log 106MB）已在本节随仓库文件一并加固，
   但**上限调大只是给根治争取时间，不是修复本身**——真正的修复是上面第 1 条，
   而**修复要随发版才生效**：生产当前跑的还是旧代码，连接仍在泄漏。
2. **发版前无数据备份**：今天 12:49 的备份目录只有 compose 快照 + 容器清单，
   没有 pg_dump。已把备份接进发版链并要求 `pg_restore --list` 校验可恢复。
3. **生产演练脚本曾经 fail-open**：缺 env 时打印 `[SKIP]` 然后返回 0，
   等于「演练根本没跑也算通过」。本节改为缺 env 即非零退出。
4. **采购/报表两类页面仍在源码里，但已不在路由表**（提交 `42f6bfa6` 移除，
   早于本节）。本节未改动，也不擅自改路由——需要产品侧确认它们是
   「已下线」还是「误删」。
5. **订单正式账本（`b_class.fact_{platform}_orders_{granularity}`）的写入路径
   至今没有实现**，本节只做到「让状态可见」。补实现前，订单数据只进暂存区。
6. **3 个店铺的 9 行「月度目标」在本次迁移里无法落库**，已写入隔离区
   `core.data_quarantine`（`error_type='ORPHAN_SHOP_NOT_IN_DIM_SHOPS'`），
   原始值完整可查：
   - `Tiktok 2店` 3 行 / 目标金额合计 321589.6
   - `shopee新加坡3C店` 3 行 / 目标金额合计 329270.0
   - `虾皮巴西（东朗照明主体）` 3 行 / 目标金额合计 339569.6
   - 合计 990429.2
   原因：这 3 个店铺**从未登记在 `core.dim_shops` 维度表里**，
   外键 `fk_breakdown_shop` 不允许落库。已核实它们在
   `mart.shop_month_kpi`（19 店 / 193 行）里**一行都没有**，
   旧视图从业务表 LEFT JOIN 出去 ⇒ 这些目标从未出现在任何报表里，
   所以跳过**不丢任何可见数据**。
   迁移对这条边界是 fail-closed 的：**只要这些店铺有真实业务数据，就中止交人工**，
   绝不自动跳过。
7. **`scripts/run_current_schema_migrations.py:820` 的备份守卫默认仍关闭**
   （守卫走 docker 传输，而生产迁移在无 docker CLI 的容器内跑，默认打开会打挂
   生产迁移）。本节改由**发版脚本的必经备份步骤**覆盖生产路径，
   守卫本身留作后续项。
8. **Celery 派发仍是同步阻塞调用**：本节已把「Redis 不可达时」的阻塞从
   16~17 秒压到 4.1 秒（建连 + 2 次重试），并让图片提取这类**不需要结果**的
   任务完全跳过 pubsub 订阅；但**派发动作本身仍是同步的**——在 async 上下文里
   它会占住调用线程直到 broker 应答。彻底的做法是把派发改成「丢线程池」或
   「写本地队列再转投」，属于架构级改动，**本节不做**（风险大于收益）。
   需要结果的任务（如 `sync_single_file_task`，任务中心要读它的状态）
   仍必须保留结果后端，那条路就注定要连 Redis。

### 四、合并到 main 之后的补测与门禁收获

1. **迁移链补测到 `20261223`**（生产真库**未做任何变更**）
   - 生产真库仍在 `current_schema_20261211_semantic_analytics_tiktok_visitor`，
     本次发版要连续执行 `20261212 ~ 20261223` 共 12 段迁移。
     其中 `20261222` / `20261223` 是同批另一会话新增的，此前只在单会话范围内验证过，
     已在**生产备份还原出的影子库**上补齐往返：
   - 正向：`20261221 → 20261222 → 20261223` 通过。
     - `20261222`：`ops.cloud_sync_receive_log` 新增 `identity_conflict_rows` /
       `identity_unresolved_rows`（integer NOT NULL DEFAULT 0）；
     - `20261223`：新建 `core.collection_source_identifiers`，落 5 条登记载体
       （`xihong` / `miaoshou_real_001` / `unknown` / `none` / 空串）。
   - 降级：`20261223 → 20261222` 通过（登记表被正确删除）。
   - 再升级：回到 `20261223` 通过（表重建、种子行仍 5 行，**不重复**）⇒ 幂等。

2. **门禁在合并到 main 之后立刻抓到一处真问题**（这正是加门禁的意义）
   - 新增的 `backend/tasks/cloud_sync_integrity_tasks.py` 用了裸 `asyncio.run(`。
   - 这不只是写法问题：asyncpg 的连接绑定在**创建它的循环**上，循环一结束连接就
     再也关不掉，只能白占数据库连接槽位 —— **与上面第 1 条是同一个事故模式**。
   - 已改成全仓唯一出口 `run_async_task`（提交 `cce6da17`），并在事件循环存活期间
     真正关闭连接池。

3. **本批触及范围内的 black / ruff 已清干净**
   - CI 的 black / ruff 步骤只检查**本次 push 改动的 Python 文件**，
     而本批触及的 55 个文件里有 40 个不符合 black、23 处不符合 ruff
     （全部是仓库既有格式债，**不是本批引入**：基线 ruff 24 处 → 本批 23 处）。
   - 已按 `docs/guides/DEVELOPMENT_WORKFLOW.md` 的要求清干净，其中 7 处
     SQLAlchemy 布尔列比较由 `== True` 改为 `.is_(True)`
     —— **不能照 ruff 建议改成真值判断**，那会把 SQL 过滤条件整个丢掉。
   - 仓库另有 37 个历史文件不符合 black 25.1.0（属于更早批次的既有格式债，
     不在本批触及范围），不影响本次发版，但建议单独做一次「全仓 black 格式化」提交。

### 五、本批最终验证结果

* 后端全量测试：**5344 passed / 0 failed / 7 skipped**（合并前两轮 + 合并后一轮）；
* 发版门禁 6 道全绿：远端部署契约 / API 契约 / 前端 API 方法 / 数据库字段 /
  关键表外键 / 生产迁移契约；库存老化管线 31 passed；前端门禁 0 失败；
* async 事件循环门禁：扫描 1523 个文件通过；
* 影子库往返：`20261211 → head → 降级 → 再升级` 全链路通过；
* 合并到 main：0 冲突，双方改动均完整保留。

## [未发布] - 登录态与入库链路修复 + 结构门禁 + 死代码清理

> 承接上一节「全链路口径收敛」，本节处理**登录优化之后暴露出来的连锁问题**：
> 令牌搬进 httpOnly cookie 之后，几条老链路没跟着改，直接 500；
> 同时把「同一件事只有一份真相」从口号变成机器会拦的门禁。

### 一、用户能感知到的修复

1. **采集任务的实时进度通道连不上**
   - 现象：发起采集后，进度条长时间不动，控制台提示 `Token required`。
   - 原因：登录优化后令牌存进 httpOnly cookie，浏览器不再持有令牌；
     而采集的实时通道只认地址栏里的 `token` 参数 ⇒ 每次都被服务端拒绝。
   - 现在：采集实时通道与通知通道一致地接受 cookie。
     令牌提取逻辑从 **5 份副本收敛到 1 份**（`backend/dependencies/auth.py`），
     来源优先级统一为：握手参数 → httpOnly cookie → Authorization 头。

2. **字段映射入库、隔离区摘要、统一层统计三条链路同时 500**
   - 现象：`/api/field-mapping/quarantine-summary` 等接口直接报
     `'AsyncSession' object has no attribute 'query'`。
   - 原因：这些是**异步接口**，却调用了只认同步会话的旧入库函数。
     同一个入库函数同时被同步脚本和异步接口调用，两种会话模型混用必然错配。
   - 现在：入库服务（暂存 / 写入 / 隔离）统一为**异步唯一实现**，
     异步接口与 Celery 后台任务共用同一份逻辑，不再有两份副本。
     Celery 任务按仓库既有范式（新建事件循环前先丢弃旧连接池）执行。

3. **同一个函数在一个文件里定义了两次**
   - 隔离区摘要函数被定义了两遍，后定义的悄悄覆盖了先定义的，
     注释还写着「已删除重复定义」——实际没删。
   - 现在只保留一份，并加了门禁防止复发。

4. **已登录用户反而被按 IP 限流**
   - 限流器只从请求头取令牌，读不到就退化成按 IP 计数。
     登录优化后令牌在 cookie 里，所以**登录用户被当成游客限流**。
   - 现在统一走同一个令牌提取点，登录用户按用户维度限流。

5. **账号对齐在异步入库时静默失效**
   - 账号对齐服务的别名缓存用同步方式加载，塞进异步会话后异常被吞掉，
     缓存悄悄变成空 ⇒ 订单的 `aligned_account_id` 丢失。
   - 现在异步路径显式加载，并在加载失败时留下可查的日志。

6. **九个表的结构对不上，四个接口直接 500**
   - 现象：`/api/hr/attendance`、`/api/inventory/ledger`、
     `/api/inventory/opening-balances`、`/api/management/data-records` 报
     「列不存在」，页面拿不到考勤与库存数据。
   - 原因：代码结构（ORM）与数据库结构各是一份真相，谁也不校验对方。
     9 张表存在列名漂移（考勤表的列还是中文名「员工编号」「考勤日期」，
     订单战役表的 11 列全是中文名；字典表缺 8 列；
     库存表缺 `received_date`/`opening_age_days`；
     数据记录表与账号表的 ORM 写的是另一套字段名）。
   - 现在：9 张表的列结构全部对齐（迁移 `20261220` + `20261221`，
     幂等可重复执行），ORM 侧同步对齐，**这四个接口已全部恢复 200**。

7. **「未匹配店铺别名」接口查询超时**
   - 现象：接口一直转圈，最后 500。
   - 原因：查询条件写成 `COALESCE(shop_id,'') IN (...)`，让底层事实表
     **已有的 shop_id 索引失效**，视图 UNION ALL 多张事实表后全表扫描。
   - 现在：条件改写成索引可用形式（语义不变）。这条是慢查询，
     仍需进一步给视图层做优化，详见文末「已知剩余」。

### 二、这次立的规矩（从口号变成门禁）

同一件事只能有一份真相；需要副本时，副本必须**由真相派生**或**被门禁校验**。

| 门禁 | 拦什么 | 接线 |
| --- | --- | --- |
| `scripts/verify_sync_query_usage.py` | 异步上下文里出现同步 ORM 查询（`db.query(...)`） | CI `test` job，失败即拦 |
| `scripts/verify_access_token_extraction.py` | 除唯一真相点外，任何地方自行读 cookie / 请求头取令牌 | CI `test` job，失败即拦 |
| `scripts/verify_orm_schema_drift.py` | ORM 声明的列在数据库里不存在（代码一用就 500） | 发版总链 `verify_release_local.py`，体检不通过即中止发版 |
| `backend/tests/test_verify_*.py` | 门禁本身的行为（能检出、能放行、豁免必须写理由、缺 DB 不静默跳过） | 随 pytest 执行 |

这三个门禁都有对应的**契约测试**：门禁自己也会被测，出现误报或漏报会立刻暴露。


### 三、清掉的死代码（20 处同步查询 + 4 个整文件）

审查发现「同步 `db.query()` 50 处」并不是 50 个独立问题，而是**同一个问题的 50 个投影**：
仓库里会话模型有两份真相（同步 / 异步），业务函数只声明「我收一个 db」、
不声明「我要求哪一种 db」。按这个口径重新分类后：

- **真故障 12 处** → 已修复（异步化，见上文第 2 条）
- **死代码 20 处** → 已删除（`data_lineage_service`、`file_registration_service`
  的同步查询、`sync_security_service`、`operational_data_importer`、
  `bulk_importer`、`account_loader_service` 的同步分支、
  `audit_service` 的同步查询方法、`task_service` 的任务队列分支）
- **合法同步 18 处** → 保留（自建同步会话 + 线程池的一次性脚本、CLI 工具）

顺带删除 3 个历史手工测试脚本（异步函数里用同步查询，跑起来必崩）。

> 本节不涉及提成/工资口径，提成链路的金额与上一节完全一致。

### 四、已知剩余（不粉饰）

1. **`/api/shop-account-aliases/unmatched` 仍然超时**
   已把查询条件改成索引可用形式（消除了 `COALESCE(shop_id,'')` 让索引失效的问题），
   但这条查询要 UNION ALL 十几张事实表并做 JSONB 提取，实测仍需 13 秒以上，
   超过该路径的 DB 预算。彻底解决需要给视图层做物化或预聚合，
   属于性能改造，不适合与本批结构修复混在一起。

2. **前端仍有 10 个失败用例**（`frontend/scripts`），其中 1 个是本次修复的
   采集实时通道鉴权，3 个是功能已下线的历史用例，6 个是断言过时。
   它们不影响运行时行为，但会让前端 CI 变红，需单独一轮收敛。

3. **发版总链仍缺前端 `node --test` 与 Playwright smoke 两步**
   （`scripts/verify_release_local.py` 目前只跑后端校验）。


## [未发布] - 人员店铺归属 → 提成 → 工资/绩效 全链路口径收敛 + 技术债清理

> 一次端到端审查：把「这个月每个人该发多少提成」从「前端算一遍、后端算一遍、
> 页面再算一遍」收敛成**一条链、一个口径**；沿途发现的技术债一次清完。
>
> 涉及的月份样例为 **2026-10**（本地开发库）。

### 一、审查发现的业务问题

1. **门禁把「不参与考核」当成错误**
   总部 / 仓库 / 客服这类**本来就不参与提成考核**的人，会让整月结算被拦住。
   现在「不参与考核」「本月不参与」「亏损」都是**状态**而不是**错误**：
   不阻断结算，但必须在页面上说清楚**为什么这个店提成为 0**。

2. **亏损店的提成会倒扣**
   亏损是「不计提成」，不是「计提负数」。现在亏损店提成记 0，不再从别人口袋里扣。

3. **页面自己算钱，和工资单实发对不上**
   前端原先有一套自己的提成公式，与后端口径不同 ⇒ 页面上看到的金额
   和工资单实发金额差几分到几毛（2026-10 实测：页面 1002.56 / 后端 1002.55 /
   实发 979.46）。现在前端**不再算钱**，只显示后端给的结论，
   只有「改了还没保存」的临时编辑才在本地试算。

4. **月度结算单把三种系数混在一列里**
   「结算系数」一列里同时混着三种口径不同的数（店铺结算系数 / 个人分数档位系数 /
   绩效工资用的加权系数），运营拿它跟同行的提成对不上、也算不出来。
   现在拆成「分数档位系数」「绩效工资系数」「提成构成（逐店）」三列，
   每列的 tooltip 都写清自己的含义。

5. **逐店金额加起来不等于总额（1 分钱尾差）**
   每家店各自舍入后相加，比总额多 1 分（黄嘉矩 9.22 + 144.67 = 153.89，
   实发 153.88）。现在把尾差并到金额最大的那家店，**页面逐店加起来正好等于总额**，
   总额和工资单一个字都不动。

### 二、收敛后的唯一口径

```
利润基数   = 订单利润 − 其他经营成本 − 提成前人力成本
可分配利润 = max(利润基数, 0) × 可分配率
预计提成   = 可分配利润 × 归属提成比 × 结算系数（逐店）

结算系数（逐店） = min(店铺结算系数, 个人分数档位系数)
店铺结算系数     = min(排名档位系数, 该店分数档位系数)
```

档位表只有一张（`backend/services/performance_coefficient.py`），
提成和绩效工资共用同一个系数 ⇒ **页面看到的系数就是工资单拿到的系数**。

**两条口径决策（已写进代码常量与注释，不靠口头约定）：**

* **绩效工资不计入成本基数**。提成基数是「提成**前**利润」，绩效工资属于提成**之后**
  的支出；计进去等于同一笔钱扣两次（先压低基数、再算提成），分母越缩越小、
  金额波动被放大。
* **无归属人力成本按各店直接人力成本占比二次分摊进各店**。不摊的话这笔钱
  既不消失也不归属任何人，等于让所有店利润虚高、提成虚高。
  按 2026-10 测算：不分摊全月提成 875.94 元，分摊后 1092.16 元，
  **差额 216.22 元**（叶海川 / 叶大望 / 陈泽伟各 +57.36 元，黄嘉矩 +44.13 元）。

### 三、数据库 SSOT 收敛

* 删掉 4 张影子 / 派生表（`a_class.performance_config_a`、
  `c_class.performance_scores_c`、`c_class.shop_commissions` 等）；
* 3 张表的中文列归零；
* `a_class.sales_targets_a` 的 252 行迁入 `a_class.target_breakdown` 后删表；
* 人力成本分摊改按 `commission_ratio`（责任比例）分摊，不再按人头平均分；
* 利润基数唯一键改成 `(period_month, platform_code, shop_id)` ——
  **一个月一家店只有一行**，口径版本降级成这条快照的属性。

### 四、技术债清理

* **人力成本口径改中性名**：`LABOR_COST_V2` → `LABOR_COST_ALLOC_V1`
  （73 行原地改名，视图与列默认值同步）。
  以前叫 V2 是上线期过渡叫法，和历史遗留的 V1 行并存，看着像有两个口径在跑，
  实际业务上只有一个。
* **中文命名的约束清掉两个**：`operating_costs_店铺ID_年月_key`
  与 `uq_operating_costs_shop_month` 完全重复 ⇒ 直接删；
  `employees_员工编号_key` ⇒ 改名 `uq_employees_employee_code`。
  （`attendance_records` 那张表的中文列还没改名、整张表与 ORM 未对齐，
  属考勤模块单独立项，本次只提示不动。）
* **`target_breakdown` 两列「目标利润」加注释、不合并**：
  `target_profit_amount` = 目标毛利（管理员直接配置，不扣成本，只作参考）；
  `target_profit_basis_amount` = 目标结算利润基数（已扣成本，
  绩效利润维度用它跟实际利润基数比达成率）。两列含义不同，合并要数据迁移。
* **归属页列标题消歧**：「提成计算基数」→「结算基数（参考）」。
  对不参与考核的店，这一列是现场估算参考值，与结算快照口径可能不同；
  tooltip 里写清「无论参考值多少，实发提成一律按结算快照算」。
* **归档删除一次性运维脚本 11 个**（诊断 / 清理 / 迁移报告一类），
  含它们在 GitHub Actions 工作流、Dockerfile 与契约测试里的接线。
  其中 `scripts/verify_local_payroll_chain.py` 的逐人反算公式是**旧口径的复制品**
  （改名前会给出假 FAIL），一并删除 —— 口径一旦改，复制品必然漂移。
  `scripts/migrate_profit_basis_to_v2.py` **保留**：它挂在生产 dry-run 工作流上，
  已同步改成中性名。

### 五、验证结果

* 后端全量测试：**5272 passed / 7 skipped / 0 failed**；
* 前端单测：**184 passed / 0 failed**，`vite build` 通过；
* 迁移 head：`current_schema_20261219_annotate_target_profit_columns`；
* HTTP 端到端三方对账（走真实接口）：结算预览 = 月度结算单 = 工资单提成 = **875.95**，
  实发合计 **26167.88**，8 张工资单 confirmed，阻断项 0；
* 浏览器实点 3 个页面，页面数字与接口一致。

---

## [v7.13.7] - 2026-11-05 - 修掉「刷新时重建视图」这个长期空转的对策 + 本地启动失败根因 + openclaw 磁盘清理

> 本版本同时包含下方「同日另一批」小节的全部内容（提成→工资链路本地端到端验证与
> 「0 元提成」根因定位、生产内存收口、openclaw 内存排查）。

### 一、本地启动失败的真正根因：不是 celery，是一个从来没生效过的「对策」

用户现象：用 `local_console` 启动做「采集→同步→收入」复核验收，启动被拦停，报
`migration_backup_failed`（迁移前的库备份做不出来）。

完整链路：

1. 启动前要给本地库做一次 `pg_dump` 备份。备份做不出来就 fail-closed 拒绝迁移 ——
   这一步是对的（不能盲改库），但它只是**症状**。
2. 备份做不出来的原因：本地常驻的 celery 在刷看板数据，刷新过程要拿排他锁，
   `pg_dump` 排在后面等锁 → 一直等 → 备份超时 → 启动被拦停。
3. **真正的放大器（本次才发现）**：看板刷新时**一直在重建视图**。
   2026-10-26 那次线上事故的对策「刷新时跳过已存在的普通视图」**从来没生效过** ——
   根因是一个类型细节：`pg_class.relkind` 经 asyncpg 返回的是 **bytes**（`b'v'` / `b'm'`），
   代码却拿它跟字符串比 → 永远不相等 → 「是不是普通视图」永远判定失败 → 跳过逻辑从不触发。

   于是每次数据刷新都在做两件危险的事：
   - 普通视图 `CREATE OR REPLACE VIEW` → 拿 ACCESS EXCLUSIVE 排他锁 → 挡住所有并发读写；
   - 物化视图执行带 `DROP MATERIALIZED VIEW ... CASCADE` 的资产文件 → 连带删掉
     **10 个下游对象**再逐个重建（`semantic.fact_orders_monthly_atomic`、
     `mart.shop_month_kpi` / `platform_month_kpi`、`api.business_overview_*` 共 8 个）。

   锁窗口被拉得很长 → `pg_dump` 必然被堵 → 备份必然失败 → 启动必然被拦停。

### 二、本次做了三层（越靠前越直接）

- **直接**：启动前**逐个**停掉会写同一个库的 Docker 后端容器。
  原来是一条 `docker stop a b c`，只要有一个容器不存在，整条命令就失败 ⇒ 其余容器
  根本没被停 ⇒ celery 一直在跑。顺带修掉一个自己引入的坑：`2>&1` 会把 docker 的
  `No such container` 转成 PowerShell ErrorRecord，在 `$ErrorActionPreference=Stop`
  下直接把脚本打断 —— 改成只重定向 stdout、单独取 `$LASTEXITCODE`。
- **兜底**：`pg_dump` 自带服务端锁等待上限（`lock_timeout=60s`）与命令超时（300s），
  被锁住就明确报错退出，不再无限期挂住；失败信息**脱敏**（不泄露主机地址/库名/凭据）
  但保留可诊断的原因（修复前只有一句 "migration backup command failed"）。
- **治本**：数据刷新时
  - 普通视图**跳过重建**（恢复 2026-10-26 的对策）；
  - 物化视图**原地 REFRESH**，不再 `DROP ... CASCADE` 删下游、不再重建 10 个下游视图；
  - 索引照旧补齐（`REFRESH` 不会重建索引，资产文件里的 `CREATE INDEX IF NOT EXISTS`
    仍然执行，新增索引照样自动生效）。
  - 物化视图**不存在**时回落到跑资产文件创建（见下面「连带删掉」那个坑）。

### 三、「跳过重建」带来的定义新鲜度，由部署期兜底

跳过重建意味着「改了 `sql/` 里的视图定义不会自动生效」—— 这本来就是设计，
但必须有人负责落地，否则就是「改了口径但看板数字不动」的**静默漂移**。

- 部署脚本现在默认重建**全部**普通视图（`--all-plain-views`），清单由
  refresh registry + 库里实际存在的视图算出，**不写死**（写死一定会漏新加的视图）；
  物化视图**不在**其中 —— 它们由迁移负责建、由数据刷新负责原地 `REFRESH`，
  部署期重建要全量重算（生产实测单个月粒度 MV 就超过 120s `statement_timeout`，
  v7.13.0 首次发布就是这么失败的）。
- 部署后用脚本自己报告的重建清单（`REBUILT_TARGETS:`）做存在性复核，
  避免「部署显示成功、视图其实根本没重建」这种静默成功。
- dashboard bootstrap 的 **core 计划（= 定义计划）改为真的重建**：它跑完之后会把
  `asset_fingerprint_applied` 无条件写成 expected，core 计划若只是「跳过」，
  库里还留着旧定义而系统却以为已经是新的 ⇒ 静默漂移。

#### 补一个「连带删掉」的坑（生产 pg_depend 闭包实测才发现）

`sql/semantic/analytics_atomic.sql` 开头是
`DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE`，
而 `semantic.fact_analytics_atomic_mv` **正是它的下游**（生产实测闭包）⇒
重建这个普通视图会把那个物化视图**连带删掉**。

物化视图又**不在**部署期的重建清单里（重建要全量重算，生产实测单个月粒度 MV
就超过 120s `statement_timeout`）⇒ 重建结束后它就「凭空消失」了，
看板当场查不出来 —— 而部署会显示「成功」。

现在补了两层：

1. **重建脚本当场自愈**：每重建一个目标就检查一次「有没有物化视图被连带删掉」，
   有就**立刻**按资产文件建回来（那些资产文件自带「存在则 REFRESH /
   不存在则 CREATE」，重建代价很低：流量原子层只有 4,431 行）；
   建不回来就**明确失败**、不让半坏的库上线。部署脚本的复核清单也把它算进去。

   ⚠️ 必须「当场」而不是「最后」：本地实跑抓到过真实失败 ——
   `mart.shop_day_kpi` 的定义**要读** `semantic.fact_analytics_atomic_mv`，
   等到全部重建完再自愈就已经晚了，那一步会直接报
   `relation "semantic.fact_analytics_atomic_mv" does not exist`。
2. **数据刷新兜底**：物化视图不存在时**回落到跑资产文件**创建
   （只 `REFRESH` 会直接报 `relation does not exist`）。
   这条自愈能力本来就是资产文件设计出来的，不能因为改成「原地刷新」就丢掉。

### 四、openclaw 磁盘垃圾清理

- 删掉 `_trash/2026-10-24`（768MiB / 56388 个文件）、`tmp/plugin-captures`（118MiB）、
  旧版升级备份 `openclaw-2026.4.22.tgz`（321MiB）—— 保留升级前最新那份完整备份。
- 删掉 `agents/main/session-sqlite-import-archive`（661MiB / 1325 个文件）。
  **删除前逐项核对**：1325 个文件**全部**带 `.imported-<时间戳>` 标记（0 个未导入），
  且 openclaw 自己的代码里写明归档缺失时「No import is needed」（`archive is missing
  without a recorded prior restore`），会话正文已在 sqlite 里
  （`transcript_events` 9961 行 / `trajectory_runtime_events` 8849 行 /
  `session_transcript_fts` 2208 行），删完逐表行数分毫未变、`PRAGMA integrity_check`
  之外的全量行数与刷新前一致、服务 PID 未变、HTTP 200 全程无中断。
- 结果：`.openclaw` 从 **1.87G → 696M**，宿主机可用内存进一步回升。
  剩下的 696M 是**活数据**（备份 309M / npm 92M / sqlite 84M / workspace 68M /
  控制台静态资源 35M / 媒体 15M），不是垃圾。

### 五、本地验证

- 物化视图原地刷新（`recreate_views=False`）：**10 个下游对象一个不少**（修复前全部丢失），
  数据行数与校验和与刷新前**完全一致**，耗时 104.6s。
- 资产文件定义 vs 库里已存定义：行数 34085、校验和 `6a0e137146ae29ee3c82d03df1a92de9`
  **完全一致** ⇒ 原地 REFRESH 与「重建」产出等价。
- 本地实跑 `rebuild_views.py --all-plain-views`：**39 个普通视图全部重建成功、
  0 失败**（修复前会失败 1 个：`mart.shop_day_kpi` 报
  `relation "semantic.fact_analytics_atomic_mv" does not exist`），
  被 CASCADE 连带删掉的 `semantic.fact_analytics_atomic_mv` 被**当场自愈**建回，
  耗时 2.8 秒；重建前后「视图 + 物化视图」集合 196 → 196（一个都没少），
  关键视图行数分毫未变，**定义校验和重建前后完全一致**（说明重建是幂等的，
  库里定义已经与 `sql/` 资产文件对齐）。
- 新增/更新守护测试 24 例（bytes 形式的 relkind 识别、物化视图原地刷新、索引补齐、
  显式重建仍走资产文件、物化视图不存在时回落创建、core 计划必须真重建、
  重建后自愈被 CASCADE 删掉的物化视图、备份超时/脱敏、容器逐个停止）；
  另删除 1 例编码旧行为（「刷新时重建物化视图」）的契约测试。
- **广口径全量跑的失败集归属已用 A/B 对照钉死**：全量 4,936 例里的 183 个失败，
  在「改动前的干净 HEAD worktree」上跑同样这 73 个文件，失败集**逐条一致**
  （NEW=0 / FIXED=0 / ADDED=0）⇒ 那些失败全是**既有问题**，与本次改动无关。

---

## [同日另一批] - 2026-11-05 - 提成→工资链路本地端到端验证 + 生产「0 元提成」根因定位 + 生产内存收口 + openclaw 内存排查


> 本次**不改计算代码**（核对结论：计算代码是对的），只补验证工具与结论记录。
> 全部验证在**本地开发库**完成，未触碰生产数据。

#### 一、提成→工资链路：本地端到端跑通，四个恒等式全通过

本地库其实**一直有完整的 mock 数据**（员工-店铺归属 433 行、店铺可分配利润率 225 行、
店铺绩效评分 81 行）—— 生产才是空表。本地把 schema 迁到最新 head、
补齐缺失的看板视图后，用官方编排器 `V2MonthlyRefreshService.refresh_month` 跑通了
「提成计算 → 工资单生成 → 人力成本分摊 → 看板口径」全链路（2026-07）：

```
commission_upserts=5  performance_upserts=9  payroll_upserts=8
labor_cost_allocation_upserts=46  profit_basis_shop_count=16  calculation_passes=2
```

四个恒等式**全部通过**：

| # | 恒等式 | 结果 |
| --- | --- | --- |
| 1 | 员工提成金额 == 工资单里的提成 | PASS（逐人一致） |
| 2 | 分摊表提成合计 == 员工提成合计 | PASS |
| 3 | 看板口径 == 分摊表 shop 范围 V2 合计 | PASS（21,231.58） |
| 4 | 逐人反算 `Σ(max(利润基数,0) × 可分配利润率 × 个人比例) × 店铺绩效系数` | PASS（5 人差额**全为 0.00**） |

⇒ **计算公式本身没有问题，不需要改。**

#### 二、生产「2026-08 起提成为 0」的真正根因

- 不是「店铺可分配利润率表为空」—— 查证后发现该表为空时会**按 100% 分配**，
  不会归零（`:1033` `allocatable_by_shop.get(shop_key, 1.0)`）。
- 真正的断点是**员工的个人提成比例**：
  - 比例取值优先级 = 归属表 `commission_ratio` → 薪资结构 `commission_ratio` → 0；
  - 生产薪资结构里 7 人**除 1 人外 `commission_ratio` 全是 0**；
  - 2026-03/04/07 的提成非零（说明当时归属表里有真实比例），
    **2026-08 起归零** ⇒ 归属表里的个人比例在这期间被清空/清零。
- 而**现在**生产归属表整体 0 行 ⇒ 补数据后重算即可拿回正确金额。

#### 三、验证出代码其实已经修好了「无声归零」

本地实验（把某员工归属比例置空、让其回落到薪资结构的 0）：

```
ratio=0.000000  金额=0.00  状态=no_ratio
details.reason = "no commission ratio configured; set
  employee_shop_assignments.commission_ratio or salary_structures.commission_ratio"
```

⇒ **现代码会把「比例没配」标成 `no_ratio` 并写明原因**，不再无声归零。
生产那 5 条 `calculated` + 0 元的行，是**修复前旧代码算出来的历史遗留**
（`calculation_details` 全为 NULL ⇒ 审计列是后加的，没回填历史）。

另有一个实测结论：**归属被清空时系统不会写提成行**（`commission_upserts=0`，
旧行原样保留）⇒ 「0 元」只可能来自「比例取不到」，不可能来自「表为空」。

#### 四、本地要补的数据（已补齐并复验）

本地 mock 数据里 `EMP260009` 被登记成 `visitor` 身份且没有薪资结构
⇒ 算得出提成（957.59）却拿不到工资单 ⇒ 分摊表少一笔。
补齐（改 `employee_identity_type='employee'` + 补 `salary_structures`）后，
恒等式 2 由 FAIL 转 PASS。**这说明「有提成但没进工资单」是能在对账里被抓住的。**

#### 五、新增可复跑的验证脚本

- `scripts/verify_local_payroll_chain.py`：一条命令跑完
  「重算 → 打印四张表 → 校验四个恒等式 → 逐人反算」，不通过则退出码非 0。
- **硬保护**：只允许连 `127.0.0.1:15432`（本地开发库），
  且主动忽略 `CLOUD_DATABASE_URL`（它指向云库隧道）⇒ 不会误连云库/生产库。
- `--skip-refresh` 只对账不写库。

#### 六、openclaw 内存增长排查结论（只读，未改配置）

- 内存构成：**匿名内存 2.32 GiB（占 RSS 98%）+ 文件缓存 45 MiB**
  ⇒ 是 V8 JS 堆，不是文件页缓存。
- 90 秒连续采样：RSS 2,344,240 KB → 2,345,280 KB（+1 MB），swap 稳定
  ⇒ **当前没有持续泄漏**，是「稳态占用偏高」。
- 磁盘上却有 **约 1.87 GiB 垃圾**：
  `_trash/2026-10-24` 768 MiB（56388 个文件，升级时的旧运行时）、
  `agents/main/session-sqlite-import-archive` 661 MiB（已导入的中间产物）、
  `backups` 321 MiB、`tmp/plugin-captures` 118 MiB。
- 另有一处隐患：`state/openclaw.sqlite-wal` 卡在 64 MiB 上限
  ⇒ 有长读事务挡住 checkpoint。
- 已有的三层保护：4 GiB 硬上限（`oom_kill=0`，从未触发）+
  本次加的 3 GiB 软限（立即生效、服务零中断）+ 宿主机 4 GiB swap。

### 2026-11-05 - 生产内存收口（宿主机 7.4 GiB，openclaw 常驻 2.8 GiB）

> 本次只改**生产基础设施配置**，不动后端代码与镜像，无需发版。
> 改动同步落在 `docker-compose.prod.yml`，随下次发布自动带到生产（否则会被覆盖回旧值）。

#### 内存到底被谁吃了

- 宿主机物理内存 7.4 GiB，**swap 为 0**，且 openclaw 常驻 2.8 GiB。
  这 2.8 GiB **不是西虹 ERP 的组件**（openclaw gateway，Node 服务，
  监听 127.0.0.1:18789，运行 11 天）。
- 西虹 ERP 自身的占用其实很健康：PG 716 MiB、backend 868 MiB、
  celery worker 354 MiB、beat 166 MiB、其余容器合计不到 40 MiB。
- 真正的病灶在 **PG 的配置被配过头了**：
  - `shared_buffers=512MB` —— 整个库才 764 MB，缓冲区比库还大；
  - `work_mem=32MB` × `max_connections=100` ⇒ **理论峰值 3.2 GiB**，
    而 PG 容器上限只有 1.5 GiB ⇒ PG 已经被内核 OOMKill 过
    （连接被重置 → nginx 记 502 → 页面打不开）；
  - `effective_cache_size=4GB` —— 宿主机 buff/cache 实际只有 2.1 GiB，
    等于骗优化器说「内存够放」，让它挑「能全放内存」的激进计划。

#### 处置一：PG 参数收口（容器重建，约 20 秒）

| 参数 | 调整前 | 调整后 |
| --- | --- | --- |
| `work_mem` | 32MB | **8MB** |
| `shared_buffers` | 512MB | **256MB** |
| `effective_cache_size` | 4GB | **2GB** |
| `max_connections` | 100 | **80** |

- 理论峰值 3.2 GiB → **640 MiB**；实测 PG 常驻 **716 MiB → 356 MiB**（省 360 MiB）。
- `max_connections` 取 80 而不是更紧的数：实测常驻连接 48 个
  （backend 连接池 30+30 × 3 个 gunicorn worker 的预热上限是 90），
  压到 60 会有真实拒连风险；而真正的大头是 `work_mem`，它已经降了 75%。
- 这几个参数写在 compose 的 `command:` 里，**不是** `postgresql.conf` ——
  命令行 `-c` 优先级更高，改配置文件不生效。

#### 处置二：宿主机加 4 GiB swap（全局兜底）

- `/swapfile` 4 GiB，已 `swapon` 生效并写入 `/etc/fstab`（重启后自动挂载）。
- 意义不只是「多 4 GiB」：此前宿主机 **没有 swap** ⇒ 任何进程涨到极限，
  内核只能启动全局 OOM killer 随机杀进程（可能正好杀掉 PG 或 backend）。
  有了 swap，超限进程会先落盘变慢，**不会突然把整个服务打死**。

#### 处置三：openclaw 保住正常运行（不重启、不停服）

- 它已经有一道**生效中的硬上限** `MemoryMax=4G`（cgroup 层面确认
  `memory.max=4294967296`，`oom_kill` 计数为 0），所以它不会无限涨把宿主机吃干。
- 新增**软上限** `MemoryHigh=3G`：超过 3 GiB 时内核开始回收它的内存并施加压力，
  逼它主动让路，但**不会杀它**。
- 实施方式：直接写 cgroup `memory.high`（立即生效，**服务零中断**，
  PID 未变、端口 18789 正常、HTTP 200），同时落一份 systemd drop-in
  让它重启后仍然保留。
- 长期方向仍是把机器升到 16 GiB，或把 openclaw 迁到独立机器。

#### 重建后逐项核对（全绿）

- 容器：postgres 重建后 healthy，其余 6 个容器未重启、未受影响。
- 数据零漂移：11 张关键表行数逐项一致；
  B 成本月度基线四项金额逐项一致
  （gmv 2,650,053.02 / 采购 1,030,829.91 / 仓储费 304,689.88 / 平台总成本 686,401.84）；
  `core.alembic_version` 未变；看板资产数（物化视图 17 / 视图 39）未变。
- 接口：`/healthz/ready` = ready，`dashboard.status` = ready，609 个路由在册，
  连接池正常（size 30 / checked_out 1 / overflow -28）。
- nginx 访问日志无 502。

#### 守护

- `tests/test_verify_remote_deploy_contracts.py` 新增 3 条：
  PG 内存参数不能退回旧值、理论峰值必须留在容器上限内、
  PG 容器内存上限不得抬到超过宿主机能给量。
## [v7.13.6] - 2026-11-05 - 换绑平台店铺ID时保留旧值别名 + 修复部署阻断（函数型目标存在性核对）

> 本版本同时包含 v7.13.5 的全部内容（三条链路接入店铺身份解析、数值守卫、
> 停用店不再重采）。v7.13.5 的部署在最后的资产校验环节被拦下并自动回滚 ——
> 应用与生产数据均未受影响（已逐项核对：容器恢复、基线全绿、库存占位键已归零），
> 本次一并上线。

### 部署阻断修复：函数型目标被误判成「不存在」

- `semantic.shop_identity_resolver` 这个刷新目标建的是**函数**
  `semantic.resolve_shop_identity`。函数不在 `pg_class`，也不在
  `information_schema` 的表与视图清单里。
- 而资产盘点只查关系型对象 ⇒ 这个目标**永远**被判成 missing
  ⇒ 积压资产组被判 drift ⇒ **部署 bootstrap 失败、应用被回滚**。
  而那个函数其实好好地躺在库里。
- 两处一起修：资产盘点补查 `pg_proc`；逻辑目标名 ↔ 真实对象名改成**双向**映射
  （真实名存在 ⇒ 逻辑名也算存在）。
- `LOGICAL_TARGET_OBJECTS` 登记表移到 `refresh_registry`
  （`refresh_validation` 与 `dashboard_bootstrap` 都要用它，而前者已经 import 了
  后者 ⇒ 反向 import 会成环）。

### 同一类问题的四个入口，之前只堵了一个

- **改名（店名）早就堵住了**：改店名时旧名会转成 `former_name` 别名（活跃、非主名），
  所以旧数据仍能匹配到同一个店。
- **换绑平台店铺ID 漏了**：账号上的 `platform_shop_id` 改成新值后，
  **旧值直接消失**，没有留任何痕迹。
  而历史行（订单 / 商品 / 服务 / 库存）的店铺键就是**采集时的平台店铺ID**
  ⇒ 旧值不再命中任何候选 ⇒ 这家店的历史数据全部落进 `unknown`
  ⇒ **看板上这家店的历史直接消失**。
- 现在换绑时把旧值也留成别名（`alias_type='former_platform_shop_id'`，
  `source='platform_shop_id_rebind'`，活跃、非主名）。
  候选集里别名行与平台店铺ID行走同一套匹配
  ⇒ 旧值命中别名行 ⇒ 仍然解析回同一个账号 ⇒ **历史数据不搬家、不改写**。
- **补齐自动绑定路径**：除了运营在后台改，自动绑定（`record_runtime_discovery` /
  `record_manual_discovery`）和人工确认（`confirm_discovery`）也会覆盖
  `platform_shop_id` —— 这三个入口本版同样补上「旧值留别名」。
- 这条修复的价值在于：**不用把全系统的键值改写成账号ID**（那要动所有业务表、
  重建外键、改写生产数据），却达到了同一个业务目标。

### 别名写了还不够：候选集快照必须跟着刷新

- 原子层（orders / analytics / products / services / inventory）读的是
  `semantic.shop_identity_resolution_candidates_v2_mv` 的**快照**，
  不是实时算的候选集。
- 改名/换绑后的刷新目标里**只有候选集正本**（普通视图）和两个**月度**物化视图
  ⇒ 重建正本**不改变副本的内容** ⇒ 新别名在原子层永远不生效，
  这家店的历史仍然落进 `unknown`。
- 现在刷新目标里**显式带上物化副本**（副本只有 136 行，刷新是毫秒级）
  ⇒ 别名/换绑之后，所有链路的归属立刻重算。

### 发布流程补漏：视图重建清单漏了商品/服务两条链路

- **改了 `sql/` 里的视图定义，光部署是不会生效的** —— 数据刷新流程与 dashboard
  bootstrap 都会跳过「已存在的普通视图」（`recreate_views=False`），生产又关掉了
  启动自愈。所以部署脚本里有一份「必须显式重建」的清单。
- 那份清单的默认值此前**只有一条**（`api.business_overview_inventory_backlog_module`）
  ⇒ **商品/服务两条链路的视图从来不在重建范围内**
  ⇒ v7.13.5 的身份解析与数值守卫改完部署上去也不会生效，
  服务层读 `satisfaction` 必崩的 bug 同样修不掉。
  「发布记录写着已上线，但口径没变」就是这样来的。
- 现在默认清单覆盖全部语义层原子层视图（订单/分析/商品/服务/库存 + 两个月度层），
  并由 `SEMANTIC_ATOMIC_VIEW_TARGETS` 常量 + 守护测试锁住
  —— 以后新增语义层链路忘了加进清单，测试直接失败。

### 收尾决策：P4「清空 B 类历史 + 重采」取消执行

生产 dry-run 盘点后的结论与原设想相反 ⇒ **本次不执行清理**。

盘点证据（生产实测，只读）：

| 项 | 数值 |
|---|---|
| 清空会删除的事实行 | **79,937 行** |
| 采集文件总数 | 241（ingested 215 / failed 26） |
| 其中源文件仍在、可重采 | **10 个** |
| 源文件已丢失、重采不回来 | **187 个**（标记 `source_missing`） |
| 失败文件（不动） | 26 个 |
| 停用店文件（v7.13.5 起跳过） | 18 个 |
| 停用店残留数据 | 商品 311 行 + 服务 30 行，**金额合计 0.00** |
| 停用店在订单/库存链路 | **0 行** |

⇒ 代价是**永久丢失约 79,600 行正常店历史数据**，收益只是剔掉 341 行金额为 0 的数据。

更重要的是：**P4 想解决的问题已经被本版本解决了** ——
库存占位键 `xihong` 归零、商品/服务/库存三条链路的 `unknown` 桶全为 0、
店铺分组数一致、B 成本月度基线逐行不变（合计 2650053.02 / 1030829.91 / 304689.88 / 686401.84）。
也就是说，**「清历史 + 重采」这个手段本身已经失去必要性**。

保留项：`cleanup_database()` 接口与「停用店不参与重采」的逻辑照旧留在代码里，
将来确有整库重采需求时可直接用；本次只是**不执行**。

另记：`semantic.fact_orders_atomic` 里仍有 93 行落在 `unknown`（金额 8263.50，占比 0.31%），
告警码 `unmatched_shop_label`、候选数 = 0 ⇒ 这些店**在本系统里就没有账号**，
按「不猜、不抹原始标识」的设计保留原键，属已知且刻意的边界，不是缺陷。

### 工程

- 新增 `backend/tests/data_pipeline/test_function_target_existence.py`（6 例）守护部署阻断：
  盘点必须看得到函数、逻辑名必须做映射、函数真不在时仍然要报 drift。
- 新增 `backend/tests/test_shop_platform_id_rebind_alias.py`（9 例：换绑留别名 / 幂等 /
  没换绑不写 / 原来没有平台ID不写 / 三个自动绑定入口都留别名 /
  刷新目标含候选集副本 / 副本已登记且排在消费者之前）。
- 更新 `backend/tests/test_shop_rename_flow.py`：原文写着「重建候选视图，原子层自动是新归属」
  —— 这在原子层改读物化副本之后已经不成立，改正并补上副本依赖断言。
- 顺带收掉 `shop_rename_service.py`、`shop_account_aliases.py`、
  `platform_shop_discovery_service.py`、`test_shop_rename_flow.py` 上 9 处既有 E712
  （`== True` → `.is_(True)`）—— 这些文件这次被改动 ⇒ CI 会检查它们 ⇒ 不修就是新红灯。
  其中 `test_shop_rename_flow.py` 那处 `# noqa: E712` 写在**下一行**，对 ruff 无效。

## [v7.13.5] - 2026-11-05 - 商品/服务/库存三条链路接入店铺身份解析 + 停用店不再参与重采

### 库存看板「按店拆不开」的根因被修掉

- **根因不是缺数据，是键被写错了**。库存采集文件里每行都带真实店铺身份
  （`raw_data` 里的 `shop_id` / `store_name` / `shop_account_id` / `platform_code`），
  但写入事实表时**店铺键落成了占位值 `xihong`** ⇒ 生产上 4,111 行库存全部挂在
  一个虚拟店下面 ⇒ 库存健康、库存周转、滞销清单这些看板**按店拆不开**。
- 现在这 4,111 行**100% 能解析到店铺账号**（实测 `raw_data->>'shop_account_id'`
  命中率 4111/4111）⇒ 库存终于能按店归属。

### 键位统一：语义层 5 条链路里 3 条一直没做身份解析

- 语义层有 5 条链路（orders / analytics / products / services / inventory）。
  以前**只有 orders 与 analytics 做了身份解析**（而且那段逻辑在两个文件里各抄了一份），
  products / services / inventory **完全没解析**，直接把采集文件里的原始 shop_id 透传出去。
  ⇒ 同一个店在不同链路里是三种键：平台店铺ID / 业务店铺ID / 原始店名 / 占位键。
  - Shopee 商品/服务行用的是平台店铺ID（`1308200832`）；
  - TikTok 商品/服务行用的是「地区(店名)」这种原始店名（`Malaysia(Flora Mall)`）；
  - 库存行全是占位键 `xihong`。
- 新增共享解析入口 `sql/semantic/shop_identity_resolver.sql`
  （`semantic.resolve_shop_identity()`）：把「候选计数 + 区域两层消歧 + 取最优候选」
  收敛成**一份**，products / services / inventory 三条链路统一调用，
  口径与 `orders_atomic` 逐条对齐。
- **解析失败保留原始键，不抹成 `unknown`**：候选为 0 说明这个店在本系统里没有账号，
  抹成 unknown 等于把「看得见的原始标识」变成「看不出所以然」；
  只有**候选 > 1（有歧义）**才落 unknown —— 挑一个就是猜。
- **去重口径零变化**：去重分区仍用原始键（`source_shop_id`），行数与金额与改造前完全一致。

### 服务看板一读就崩：满意度列的数值转换没做合法性校验

- **现象**：语义层 `semantic.fact_services_atomic` 一读 `satisfaction` 就报
  `invalid input syntax for type numeric: "--"`，整条查询直接失败。
- **根因**：`b_class.fact_tiktok_services_agent_monthly` 有 **137 行满意度是 `'--'`**
  （平台导出里的「无数据」占位符）。原来的转换写法
  `NULLIF(REGEXP_REPLACE(x, '[^0-9.-]', '', 'g'), '')::numeric` 对 `'--'` 会得到 `'--'`
  —— 非空 ⇒ 走进 `::numeric` ⇒ 炸。
- **为什么一直没被发现**：PostgreSQL 的**列裁剪**会把坏列优化掉 ——
  `SELECT count(*)` 正常返回 469 行，一读数值列才报错。
  ⇒ **「count(*) 通过」不代表视图健康**（这条已经吃过三次亏）。
- analytics 层在 v7.13.2 已经补过正则合法性校验，但
  **products / services / inventory 三层都还没补** ⇒ 同样的坑还在。
- 现在这三层共 **30 处**数值转换全部补上校验
  （`^-?(?:\d+(?:\.\d*)?|\.\d+)$`，与 analytics 层逐字一致）：
  非法值一律落 **NULL 而不是 0** —— 「取不到」和「真的是零」必须可区分。

### 停用店不再参与重采

- 生产 52 个店铺账号里有 **33 个是停用状态**（32 个 Shopee + 1 个测试账号）。
  它们的历史采集文件还躺在 `public.catalog_files` 里（实测 18 行）。
- 以前清空事实数据时，这些文件会被**一起**重置成 `pending` ⇒ 重采去连那些已经停掉的店：
  一边白跑采集，一边又把停用店的数据灌回事实表。
- 现在清理重采时**跳过停用店的文件**（平台店铺ID / 业务店铺ID / 账号主键三种身份键都认）。

### 工程

- 新增 `backend/tests/data_pipeline/test_shop_identity_resolver.py`（口径守护：
  三条链路必须接入解析、必须保留原始键、新增列必须追加在末尾、资产不得含 DROP/CASCADE）。
- 新增 `backend/tests/test_data_sync_cleanup_disabled_shops.py`（停用店不重采 + 缺表优雅降级）。

## [v7.13.4] - 2026-11-05 - 员工薪资/提成/绩效链路打通 + 店铺显示名统一

### 薪资链路：口径不再各说各话

- **工资单「锁定」只有一个定义源**：新增 `backend/services/payroll_period_lock_service.py` 的
  `PAYROLL_LOCKED_STATUSES`（`approved` / `confirmed` / `paid`）。
  以前**四处各写各的**：锁定服务只认 confirmed+paid，而工资单界面和「我的收入」把
  `approved` 也显示成「已锁定」⇒ **界面显示已锁定、后台却允许整月重算**，
  重算会悄悄改掉用户以为锁住的工资单。现在全部引用同一份常量。
- **人力成本不再算两遍**：`finance.employee_labor_cost_allocations` 里同一行可能有
  历史 V1 与现行 V2 两个版本（V1→V2 是「原地改标签」的历史迁移，遇到受保护工资月会跳过
  ⇒ 那些月份仍是 V1；随后 `refresh_month` 又会新建 V2 行 ⇒ 同月双份）。
  以前 `mart.shop_month_labor_cost` 与几处直接查 base 表的读路径**都不过滤版本**
  ⇒ 看板「人力成本」最多虚高一倍；而利润基数侧（`profit_basis_service`）**是**按版本过滤的
  ⇒ 看板与利润基数两套口径。
  - 现在视图（迁移 `20261108`）与全部读路径（看板服务、费用管理、月结服务）统一**只认 V2**。
  - 看板「用投影人力成本还是手工人力费用」不再看 `system_config` 里那个**没人维护的开关**，
    改成**看数据本身**：这个月有 V2 投影行就用投影口径（扣掉手工人力费用、加上投影金额），
    没有就保留手工人力费用 —— 两种情况都不会重复计，也不会凭空少算。
- **换店/归属变更后的人力成本不再重复计入**：`LaborCostProjectionService.refresh_month`
  以前**只 upsert、从不删除** ⇒ 员工换店、归属比例调整、工资单被删之后，
  那些已经不成立的分摊行**永久留在表里**，而看板/利润基数是把整张表 SUM 起来用的。
  现在会清掉「这次算不出来但表里还在」的行；**已锁定（已结账）的行不删、直接报错** ——
  删了等于偷偷改已结账的钱。
- **「没提成」不再是没有记录**：以前员工如果**没配提成比例**，计算会直接跳过
  ⇒ 根本不产生提成记录 ⇒ 工资单提成恒 0，界面却看不出任何异常。
  - 现在照样落一条记录（金额 0）+ `calculation_status='no_ratio'`，
    并把**比例来源**写进新增的审计字段 `c_class.employee_commissions.calculation_details`
    （迁移 `20261109`）：是「店铺归属行填的」还是「薪资结构兜底的」，一目了然。
- **提成比例只有一个权威来源**：店铺归属行 `employee_shop_assignments.commission_ratio`；
  薪资结构 `salary_structures.commission_ratio` 明确降级为**员工级兜底**。
  这段「先取归属行、取不到再取薪资结构」的逻辑以前被**抄了三遍**（金额聚合/系数加权/店铺分摊），
  改一处必漏两处 ⇒ 收敛成 `_resolve_commission_ratio()` 一个方法。
- **提成比例上限校验不再被绕过**：NULL 与负数以前被 `or 0` 抹平，
  负数会让总和变小 ⇒ **绕过 100% 上限**。现在负数直接报错，NULL（这个店不给这个人算提成）
  在报错文案里单独说明。
- **绩效「配了不生效」被堵住**：`key_product_weight`（重点产品维度）**根本没实现**
  （打分时硬编码 0），但配置校验只查「四个权重加起来 = 100」⇒ 管理员把它调成 >0 也能保存成功，
  然后这个权重**永远不生效**。现在新建/修改配置时直接拒绝并说清楚原因。
  同时修掉 `c_class.performance_scores` 上写死的「30%/25%/25%/20%」注释
  （实际默认是 40/40/0/20，而且权重是可配置的）。

### 店铺显示名统一：全站不再直接甩键值给用户

- **主名 = 内部编号**（`internal_code`，如 `XHKJ11_SG`），**副显 = 店名**（`xhkj11.sg`）。
  平台上能看到的是店名，但**店名会改、别名也会改**；内部编号唯一且稳定 ——
  报表、截图、对账都以它为准。生产上 52 个店铺账号的 `internal_code` **覆盖率 100%**。
- `/api/reference/shop-directory` 现在返回 `internal_code` 与 `secondary_name`
  （以前只给 `display_name`，前端想按内部编号显示也拿不到）；
  顺带把它**每个店查一次别名**的 N+1 查询改成一次批量查。
- 新增 `frontend/src/composables/useShopDisplay.js`：**目录只请求一次**（模块级缓存），
  加载失败**不拖垮页面**（退回显示原始键值），口径只有一份。
- 新增 `frontend/src/components/common/ShopDisplayText.vue`：统一的「主名 + 副显」单元格。
- **接入 20 个文件**：A 类 15 个（原来直接渲染 `shop_id` 的表格：
  库存余额/告警/流水/期初/对账/总览、订单管理、按商品看销售、B 成本分析、
  费用管理、销售目标、目标执行工作台、收入审计、跟投收益、员工工资）
  + B 类 5 个（原来渲染 `shop_name` 的表格：销售看板、库存健康看板、产品质量看板、
  活动管理、目标人员管理）。
  另外把**下拉选项、删除确认弹窗、详情页**里裸露的 `shop_id` 换成显示名 ——
  确认弹窗里出现 `1308200825` 这种串，管理员根本不知道自己在删哪家的数据。
- **修掉「重复装饰导致原始店名失真」**：`decorateShopEntity` 会把 `shop_name` 覆写成显示名，
  再装饰一次时原始店名就被显示名顶替 ⇒ `canonical_name` 变成显示名。
  现在优先用 `raw_shop_name` / `canonical_name` 解析，并把装饰前的原始店名留在 `raw_shop_name`。
- **搜索文本补齐所有键值**：以前只放第一个非空 ID ⇒ 拿平台店铺ID 搜就搜不到
  （「看得见、搜不到」）。现在内部编号、别名、店名、平台店铺ID、店铺账号ID 全部进搜索文本。
- **员工归属接口的店铺名不再依赖派生表**：`/api/hr/employee-shop-assignments` 的 `shop_name`
  以前查 `core.dim_shops`（派生展示维度表，曾经长期 0 行 ⇒ 名称恒空），
  现在直查权威主数据 `core.shop_accounts`，键派生与语义层一致。
- 新增前端单测 `frontend/scripts/shopDisplay.test.mjs`（8 个用例：
  主名优先级、搜索文本、跨平台同名不串店、重复不失真等）。

### 工程

- 清掉两处「被同名覆盖的死代码」：
  `payroll_generation_service.py` 里 4 个被覆盖的旧版方法（带中文列 fallback 的旧实现）、
  `hr_commission.py` 里两个未被引用的 legacy loader，以及**重复注册的绩效模板路由**
  （同一路径注册了两次）。
- 清掉一条**悬空登记**：`mart.hr_shop_monthly_profit` 登记在刷新依赖表里，
  但这个视图**从来没有建过**（仓库无资产文件、生产库查不到、无任何代码引用）
  ⇒ 已删除，并把「登记的每个目标都必须能被资产文件重建」固化成断言，防止同类悬空登记再出现。
- 收口本次改动文件上的既有格式/lint 欠账（black / ruff），避免 CI 红灯。
- 新增迁移 `current_schema_20261108_align_labor_cost_allocation_version`、
  `current_schema_20261109_add_commission_calculation_audit`。

## [v7.13.3] - 2026-11-04 - 看板超时降级兜底 + 数据地基（dim_shops 对齐 / 改名占用预检 / 状态服务端派生）

### 可靠性：看板查询超时不再「空白页」

- **看板不再「超时即空白页」**：数据库语句超时时，后端不再直接返回 500，而是返回**上一次成功算出来的结果**，并在响应里明确标出「这份数据是截至什么时候的」。
  - 降级只发生在**超时**这一种故障上。语法错、权限不足、连接断开照常 500 —— 把它们伪装成「数据有点旧」会把真 bug 藏起来。
  - 超时**且**没有可用快照时，仍然返回 500 —— 不能凭空造数。
  - 客户端断开（`asyncio.CancelledError`）不算超时：那是用户走了或服务在停机，不该拿旧数据糊弄过去。
- **快照按端点分桶**（`<端点>:last_success`）：不同端点的查询参数可能完全一样（kpi 与 operational-metrics 都是 `granularity/period_key/platform_code/shop_id`），共用一个键会把 A 端点的数字当成 B 端点的发出去。
- **快照活 24 小时**（普通看板缓存只有 180 秒）：快照的用途正是「现在算不出来时还能给用户看点什么」，活得比普通缓存短就没意义了。
- 响应里新增 `meta.data_status="degraded"`、`meta.data_as_of`（那次成功结果的时间）、`meta.degraded_reason`，以及一条人话 warning；响应头 `X-Cache: DEGRADED`。前端业务概览页顶部弹出黄色提示条，明说「当前展示的是上一次成功的结果，不是最新数据」。
- 降级记录挂在 `request.state` 上而不是 ContextVar：bootstrap 端点用 `asyncio.gather` 并发跑 7 个模块，而 **Task 会复制一份 contextvars 上下文** —— 子任务里 `ContextVar.set()` 传不回父任务。

### 数据地基

- **`core.dim_shops` 全量对齐（生产此前是 0 行）**：看板的显示名 JOIN 读这张表，而它**一行都没有** ⇒ JOIN 永远落空，显示名只能靠 `core.shop_accounts.store_name` 兜底；绩效/提成/告警等 10 张业务表也以它为外键目标，等于全在裸奔。
  - 根因：这张表的唯一写入方从**旧模型** `core.platform_accounts` 同步，而旧模型早已被 `core.shop_accounts` 取代（生产：旧模型 11 行残留，新模型 52 行才是权威）；那个同步只在「建提成配置/建目标」时顺带被调用 ⇒ 从没跑过。
  - 修法：迁移 `20261107` 把 `core.dim_shops` 变成 **`core.shop_accounts` 的派生表**，键派生与语义层**逐字一致**（`resolved_shop_id = COALESCE(platform_shop_id, shop_account_id, id::text)`）—— 派生不一致 ⇒ JOIN 落空 ⇒ 这次修复等于没做。
  - **可重跑**：upsert + 清掉源里已不存在的派生行 ⇒ P3 改键后重跑一次即可全量对齐。清理**不带 CASCADE**：历史业务表有外键指向它，真有引用就让迁移失败（fail-closed），不会悄悄删数据。
  - 写入路径同步补齐：新建/编辑店铺账号立刻 upsert 维度行（并按需补平台维度），不再靠「碰巧走到某个接口」才写进去。
  - 安全边界：`dim_shops` 主键就是 `(platform_code, shop_id)` ⇒ 看板 JOIN 最多命中一行 ⇒ **不会把金额翻倍**。
- **改名新名的跨主账号占用预检**：店名是身份解析的**第 4 路匹配键**（`store_name_match`），语义层按 `(platform, 规范化店名)` 找候选、**不区分主账号** ⇒ 两个不同主账号的店铺用了同一个店名 ⇒ 候选数 = 2 ⇒ 原子层判为 `ambiguous_shop_label` ⇒ 这些行的 `shop_id` 落进 `'unknown'` ⇒ **这家店的钱在看板上直接消失**。原来的校验只覆盖「同一个主账号」，跨主账号撞车要到语义层才炸 —— 那时已经在算钱、已经算错了。现在提前拦在写入侧（409，人话说明占用方）。
  - 规范化口径与语义层一致（`normalize_alias_key`：剥平台前缀 → 小写 → 折叠分隔符），否则「看着不一样、匹配时一样」。
  - 区域语义与别名表唯一约束一致：同名 + **不同**区域 ⇒ 允许（区域消歧就是为了让同平台同名在不同区域并存）；一方区域为空（不限区域）⇒ 与另一方也为空才算冲突。
- **`platform_shop_id_status` 改为服务端派生**：它回答「这个平台店铺ID是什么来路、靠不靠谱」，必须与数据一致 —— 没有平台店铺ID却标成 `manual_confirmed` 就是在骗下游（看板身份健康度、采集对账都拿它当依据）。
  - 没有平台店铺ID ⇒ `missing`（客户端说什么都不作数）；
  - 平台店铺ID 变了（人工填的）⇒ `manual_confirmed`；
  - 平台店铺ID 没变 ⇒ **保留原状态**（`auto_bound` / `confirmed` 不被一次无关字段的编辑改写掉）。
  - 「变化了没有」按**派生结果**判定，不按客户端声称 ⇒ 派生结果没变就不触发归属重算（避免无谓的刷新风暴）。

### 工程

- 新增 `backend/utils/query_timeout.py`：沿异常链（`__cause__` / `__context__` / SQLAlchemy 的 `orig`）识别超时 —— asyncpg 的 `QueryCanceledError`、psycopg2 的 `QueryCanceled`、`sqlalchemy.exc.TimeoutError` 都能认，同时不会把普通异常误判成超时。
- 新增 `backend/tests/data_pipeline/test_dashboard_timeout_fallback.py`（10 个用例）与 `backend/tests/test_dim_shops_alignment.py`（11 个用例）。
- 顺手修掉 `shop_accounts.py` 里一处既有 ruff 违规（`is_active == True` → `.is_(True)`）：该文件这次被改动 ⇒ CI 会检查它 ⇒ 不修就是一条新红灯。


## [v7.13.2] - 2026-11-04 - 物化店铺身份候选集 + 修 analytics 数值转换脏数据

### 修复

- **`fact_analytics_atomic` 的数值转换会崩**（v7.13.1 发布时暴露）：清洗正则 `'[^0-9.-]'` 会**保留** `.` 与 `-`，所以脏值 `"-"` 清洗后仍是 `"-"`，`NULLIF` 挡不住 → `'.'::numeric` 直接抛 `invalid input syntax for type numeric`。
  - 这个缺陷平时被 PostgreSQL 的**列裁剪**掩盖了 —— `SELECT count(*)` 不计算这些列，所以查询看着正常；直到 `CREATE MATERIALIZED VIEW` 要物化**全部列**才炸出来。
  - 修法：给 analytics 层 12 处数值转换补上与 `orders_atomic.sql` **完全一致**的正则合法性校验（`^-?(?:\d+(?:\.\d*)?|\.\d+)$`，不合法 → NULL）。订单层本来就有，analytics 层漏了 ⇒ 现在两层对齐。
  - 口径影响：命中脏值的行，**原来整个查询报错**（什么都看不到），现在该字段为 NULL、其余字段正常 —— 是从「崩」变成「空」，不是改口径。

### 性能

- **根因**：`semantic.shop_identity_resolution_candidates` 这个候选集只有 **136 行**（52 个账号 + 21 条别名派生），却是**普通视图**；而订单/流量原子层是**每行**都要做一次身份解析（`LEFT JOIN LATERAL`）⇒ 每一行订单事实都把候选集重新展开、把 `regexp_replace` 之类的规范化表达式重算一遍、再排序一次。生产 `EXPLAIN ANALYZE` 实测全量重算 38,607 行要 **119 秒**，计划里 `shop_account_aliases`（只有 21 行的小表）被扫了 **148 万次**（38,607 行 × 38 次）—— 典型的 N+1：小表被当成逐行计算的表达式。
- **修法**：新增物化副本 `semantic.shop_identity_resolution_candidates_v2_mv`，原子层的两个**普通视图**（`fact_orders_atomic` / `fact_analytics_atomic`）改读它。
  - **正本（普通视图）一个字都没改** —— 它仍从 core 表现算（已用 git diff 逐字节核对），既有的断言全部继续有效。
  - 副本正文是**自包含的一份定义**（从 core 表现算），不是 `SELECT * FROM 正本`。原因：正本在不同环境里列数不同（生产 8 列、含区域消歧列；全新库 baseline 建的是 7 列旧版）⇒ 引用正本在全新库根本建不出副本。代价是两份定义，用契约测试（4 路 UNION 分支数、区域列）+ 迁移里的**内容指纹**守护防漂移。
  - ⇒ **口径零变化**：迁移建完副本立刻比对它与正本的**内容指纹**（行数 + 全量 md5），不一致直接抛错回滚 —— 「副本 == 正本」由机器证明，不靠人眼比对。生产实测 136 行逐字节一致。
  - **不动** `orders_monthly_atomic_mv` / `analytics_monthly_atomic_mv`：那是既有物化视图的完整定义（`DROP ... CASCADE` + `CREATE`），改了要在生产重建它们 ⇒ 有风险。它们继续读正本，既有行为不变。
  - 新增「建对象前置」机制（`ASSET_PREREQUISITES`）：目标资产的正文引用了别的对象时，那些对象必须先在 —— 副本不存在时建原子层视图会直接报 `relation does not exist`。
  - 顺手删掉 20260805 schema baseline 建的旧版候选集物化视图（只有 7 列、缺 `identity_shop_region`、没有任何对象引用它）；删除时**故意不带 CASCADE** —— 万一有依赖就让迁移失败（fail-closed），而不是悄悄删下游。
  - **实测效果**：全量重算从 113.5 秒降到 **9.2 秒（提速 12.3 倍）**；v7.13.1 物化层的「刷新要 115 秒」才真正降下来 —— 刷新窗口从分钟级回到秒级，不再出现「刷新时全员卡住」。

### 工程

- **迁移侧统一走原生 psycopg2 cursor**（与 schema baseline 同一范式）。SQLAlchemy 的 `exec_driver_sql` 在本仓库锁定的版本 + psycopg2 组合下会把空参数字典（`immutabledict`）交给 `cursor.execute`，而 psycopg2 只接受真正的 `dict`/序列 ⇒ 必然抛 `TypeError: immutabledict is not a sequence`。原生 cursor 走 PostgreSQL **简单查询协议**，多语句由数据库自己切分（`DO $$ ... $$` 不会被切坏）。
- **回滚路径修正**：物化视图的 `downgrade` 改成「先把消费方改回普通视图、再删物化视图」，并且**不再用 `DROP MATERIALIZED VIEW ... CASCADE`** —— CASCADE 会连带删掉 `mart.inventory_backlog_base_mv` 这类**不是 refresh registry 可重建目标**的对象，删了没人重建。
- `scripts/validate_migrations_fresh_db.py` 修掉一个**会吞掉真实报错**的 bug：Windows 下子进程输出按 GBK 解码，迁移一旦报中文/编码错会被当成「空输出」从而掩盖真因。
- **验证**：全新库 fail-closed 迁移门禁通过（迁移 + 数据同步关键列校验 + ORM Schema 一致性校验全绿）；后端大范围回归失败集 diff **新增失败 = 0**。


## [v7.13.1] - 2026-11-04 - 修复物化视图建表超时预算 + 收口 CI 格式与 lint 欠账

### 修复

- **v7.13.0 首次发布失败的根因修掉**：迁移 `20261105` 建物化视图时被 PostgreSQL 的 `statement_timeout`（生产 `2min`）掐断 —— 全量重算一遍原子视图实测就要 **114.6 秒**（`SELECT count(*) FROM semantic.fact_orders_atomic`，38,607 行），`CREATE` 还要把 38,607 行写进物化存储并建 4 个索引，必然超时。迁移现在把语句超时临时提到 **30 分钟**，结束后在 `finally` 里恢复原值 —— 迁移用的连接之后要归还连接池，不能带着 30 分钟超时去污染后续应用查询。
  - v7.13.0 那次失败是**整事务回滚**（alembic 把 `upgrade head` 当一个事务跑，20261104 的 DROP 也一并回滚），生产自动回滚到 v7.12.9，容器全部 healthy、API 200、**零残留** ⇒ 回滚机制本身是有效的，这次要修的是超时预算，不是回滚逻辑。
  - 顺带修正 `sql/semantic/orders_atomic_mv.sql` 里的错误注释：原先写「物化一次约 20 秒」，那是把**单次查询代价**当成了**物化代价**，实测是 114.6 秒。

### 工程

- **CI 红灯收口**：CI Pipeline 连续两版红（上一版 41774788661、本版 41853739109）都不是逻辑问题，是**存量欠账被本次改动触发**：
  - `black --check`：CI 只对**改动文件**跑检查，本次碰到 34 个文件、其中 26 个本来就不符合仓库锁定的 black 25.1.0 ⇒ 统一格式化（纯格式，无语义变化）。
  - `ruff check` 4 处 `F841`（赋值后未使用）：2 处 `params` 是重构遗留（早已改成显式 kwargs 传参）、1 处 `module` 是重复的字典查找（`_module_core_plan()` 内部已有同样的查找）、1 处 `current_count` 连带一次无用查询。
  - `Bandit` `B324`：`cache_service.py` 的缓存 key 哈希用了 MD5，命中 HIGH；这是**非安全用途**（只做短摘要，不用于签名/口令），按仓库既有先例显式标注 `usedforsecurity=False`。
  - 本地按 CI 同版本复现验证：black 25.1.0 ✓ / ruff 0.17.3 ✓ / bandit 1.9.4（total=0、matched=0）✓；后端失败集 diff **新增失败 = 0**。

## [v7.13.0] - 2026-11-04 - 下线滞销清理排名模块 + 重排超时预算 + 放宽数据库内存

### 退役

- **「滞销清理排名（月度）」整模块下线**（业务概览页）。这个模块不是慢，是**设计本身有问题**：它把「店铺级月度排名」和「SKU 级库龄/动销」两套口径揉在一张表里，排名口径依赖订单域全量重算，且语义层对不上店的行会落进 `unknown` 桶 —— 排名里会出现"某个不存在的店铺"。前端区块、API 封装、后端端点、服务方法、SQL 视图、刷新注册、缓存预热、事件监听、部署契约一并移除。
- 库存域的「SKU 级滞销清单」（`api.sku_clearance_ranking_module`，走 `mart.inventory_state`）是**另一套东西，保持不变**。
- 同模块的死代码一并清掉：`backend/services/clearance_ranking_service.py`（零活引用）、ORM 模型 `ClearanceRanking` 与死表 `c_class.clearance_rankings`（生产 0 行，唯一写入方就是上面那个 service）、Metabase 遗留 `sql/metabase_questions/clearance_ranking.sql`。**留着那张表等于留着一条"复活已退役模块"的写入路径。**
- 刷新管线模块键 `clearance_ranking` 更名为 `inventory_backlog`（它真正持有的是库存积压资产组），基表与全部下游仍在同一模块内 —— 「基表与它的全部下游必须同属一个模块」这条不变量没有被破坏。
- 迁移 `20261104_drop_clearance_ranking_module`：DROP 视图（不带 CASCADE）+ DROP 死表（fail-closed：非空则中止）+ 清理 `ops.dashboard_asset_state` / `ops.data_freshness_log` / `ops.data_lineage_registry` 里的僵尸行，避免新监控把已退役对象报成 missing。
- 部署期默认视图重建目标从 `api.clearance_ranking_module` 换成 `api.business_overview_inventory_backlog_module`。

### 性能

- **超时预算重排，504 变成可读的 500**：原来 nginx `proxy_read_timeout` = 60s 与后端 DB `statement_timeout` = 60s **完全相等**，DB 报错与 nginx 掐连接同时发生，nginx 永远先断 ⇒ 用户只看到 504 空白页，后端那条可读的"查询超时"永远送不到浏览器。现在是 **DB 60s < 前端 axios 120s < nginx 300s**（nginx 读/写超时 60s → 300s，前端 dashboard 超时 70s → 120s），DB 先失败、后端如实返回 500、nginx 如实转发。
- **原子层物化：业务概览与 B 成本页的 20 秒级慢查询根治**。根因是 `mart.shop_day_kpi` 读的 `semantic.fact_orders_atomic` 是**普通视图**，每次请求都要 9 张订单表全量 UNION + `ROW_NUMBER()` 去重 + 逐行 LATERAL 身份解析，且 PostgreSQL **无法把 `metric_date` 过滤下推到窗口函数之下**（EXPLAIN 实测：9 张表全部 Seq Scan，单日聚合约 20.2 秒）。
  - 新增两个物化视图 `semantic.fact_orders_atomic_mv` / `semantic.fact_analytics_atomic_mv`，正文就是对应普通视图的正文（`SELECT * FROM <普通视图>`）⇒ **口径零变化**：同一份定义、同一套去重、同一套身份解析、同一批行，物化只改变「什么时候算」。
  - **为什么不是"按粒度换源重建 MV"**：生产测绘显示订单事实共 38,607 行 = 月 36,624（GMV 93.79%）+ 周 1,506（3.86%）+ 日 477（2.35%），且去重窗口在生产上一次都没合并过（38,607 组 = 38,607 行）。纯月表源会少算 1,983 行订单（GMV 6.2%）⇒ B 成本金额漂移 ⇒ 换源方案已否决。
  - **为什么不用 `DROP MATERIALIZED VIEW ... CASCADE`**：CASCADE 会连带删掉 `mart.hr_shop_monthly_profit`、`mart.inventory_backlog_base_mv`（不是 registry 可重建目标）与 B 成本链（不在 bootstrap 计划里）⇒ 删了没人重建。改用「存在则 REFRESH（原地刷新）/ 不存在则 CREATE」：不删任何下游，也没有「视图短暂消失」的窗口；且 MV 正文引用的是普通视图，普通视图更新后 MV 刷新即跟进，不会漂移。
  - 6 个慢消费方改读物化视图：`mart.shop_day_kpi` / `shop_week_kpi` / `platform_day_kpi` / `platform_week_kpi` / `b_cost_shop_month` / `api.b_cost_analysis_order_detail_module`。
  - 迁移 `20261105_create_atomic_materialized_views`：建两个 MV + 4 个索引，并用 `sql/` 资产文件重建 6 个消费方视图（视图定义的 SSOT 仍是资产文件，迁移不抄第二份）。
  - 顺带修正 `api.business_overview_operational_metrics_module` 的依赖表：它的 SQL 资产里有一处 `LEFT JOIN mart.shop_day_kpi`，但依赖表里没写 → 可能拿到旧日粒度数据。
- 数据库容器内存上限 2G → 4G：线上实测上限只有 1.5GiB，而 `shared_buffers=512MB` + `work_mem=32MB×4` 并行 worker 在重分析查询时瞬时占用很高，历史上有过 OOMKilled（内核杀 PG → 连接重置 → nginx 记 502）。

### 验证

- 后端大范围回归（`backend/tests/data_pipeline` + 刷新队列 + `tests/`）与 HEAD 基线做**失败集 diff**：0 个新增失败；8 个清仓排名相关用例随模块下线一并移除。
- 前端哑测试门禁：静态路径检查 0 问题、运行时"没跑起来"0 问题，普通断言失败 8 个（与基线一致）。
- 生产只读实测：清仓排名 504 已从 nginx 错误日志消失；`store-analysis/shops` 现为 404（v7.12.9 已退役，非本次范围）。

## [v7.12.9] - 2026-11-04 - 退役 5 个失效模块 + 监控存在性校验 + 依赖单一真相源

### 退役

- 彻底清理 5 个已失效模块：店铺分析、店铺管理、财务报表、汇率管理、会计期间 —— 前端路由/菜单/权限/组件/API 封装、后端端点与 service、SQL 资产、权限目录条目一并删除。
- 删除 Metabase 时代的死 stub router `backend/routers/dashboard_api.py` 与 `backend/services/annual_cost_aggregate.py`。
- 清理 `annual_summary` 全部 service 方法、5 个 `api.annual_summary_*` / `api.store_analysis_*` SQL 资产与 `mart.shop_hour_traffic_kpi`。
- 权限目录从 59 项收敛到 54 项，系统角色默认权限同步收敛；`ensure_system_roles()` 启动时自动对齐已有角色，无需手工改生产库。
- 生产库清理 9 个僵尸目标的 14 条血缘边与 9 条新鲜度记录（先清理后上线，避免新监控把已退役对象报成 missing）。

### 依赖

- 新增 `requirements.lock.txt`（116 个包的完整传递依赖闭包，全部 `==` 钉死），根 `requirements.txt` 收敛为 51 项运行时直接依赖。
- 删除 `backend/requirements.txt` —— 它与根清单有 26 个包互相矛盾，正是 v7.12.7 依赖漂移的根源。
- 后端与采集镜像改为单步 `pip install -r requirements.lock.txt`，不再分两步互相覆盖。
- 镜像依赖门禁基线从 7 扩到 116 且从 lock 自动推导，新增「禁止浮动范围 / 必须单步安装 / 镜像内无锁外包」三项检查。

### 监控

- `/freshness` 新增 `object_exists`、`recorded_status`、`status="missing"` 与 `missing_targets`；`/lineage` 新增 `target_object_exists`、`source_object_exists` 与 `missing_objects` —— 不再只信「上次刷新时的结果」。
- 逻辑目标别名（`semantic.alias_registry` → `semantic.semantic_field_aliases`）登记在册，并用守护测试强制新逻辑目标必须登记，避免把活目标误报成 missing。

### 验证

- 后端全量回归 181 个失败用例 ID 逐个拿到 HEAD worktree 对照，0 个新增失败。
- 生产验收：5 个容器 0 重启、路由 619 → 612、权限目录 59 → 54、47 个监控目标 missing 为空、前端 bundle 无退役标识残留。

## [v7.12.8] - 2026-11-04 - 钉死 Celery 全链路依赖，修掉 kombu 漂移引发的 celery 崩溃循环

### 修复

- 根因：`kombu` 从 5.6.2 漂到 5.7.0，而 kombu 5.7.0 硬性要求 `redis-py>=6.1.0`，与钉死的 `redis==5.0.1` 冲突，导致 celery-worker / celery-beat 上线即抛 `kombu.exceptions.VersionMismatch` 并进入崩溃循环。pip 安装期不报错，只有运行时才炸。
- 把 Celery 全链路依赖（kombu / amqp / billiard / redis）全部钉死。
- 新增镜像依赖门禁：构建期比对镜像内实际版本与清单一致，让这类运行时不兼容在 CI 就暴露。
- CI 增加 celery 冒烟作业。

### 决策

- 按业务拍板「只修根因、不回退」执行，未回退版本。

## [v7.12.7] - 2026-11-03 - 巡店会话复用收尾 —— profile 唯一载体彻底落地

### 重构

- 废弃会话文件体系，登录态只保留持久化 profile 一个载体；删除旁路 profile 分支与店铺级遗留路径。
- 正式采集统一走持久化 profile，顺序路径不再读写会话文件；并行快照改为纯内存。
- 账号会话锁改为跨进程实现并对齐 profile 生命周期，父子进程共用同一把 Redis 锁。
- 打通账号级代理链路：代理进入浏览器与 context，凭据不再泄漏到日志与组件配置。
- 删除遗留采集中心老程序（app.py / handlers.py）。

### 清理

- 磁盘清理 2.13 GB；同步收敛会话诊断字段与外围遗留物告警语义。

### 文档

- 补生产 compose 事实源与 Redis 认证形态；记录 GitHub HTTPS 不通时走 SSH-443 的镜像同步解法。
- 落地可复用的 pytest 失败集合 diff 工具与基线快照导出。

## [v7.12.6] - 2026-11-02 - 巡店会话复用 + 店铺身份/别名治理（含语义层区域分流）

### 店铺身份

- 别名表加区域维度，店铺账号新增内部标准名 `internal_code` 及账号管理页编辑入口。
- 改名走联动流程，老数据不断、新数据不串；未匹配别名面板补出现次数与认领提示。
- 多候选不再静默归一，落 unknown + 告警码；写侧与查侧规范化统一，认领了不再匹配不上。

### 巡店与会话

- 打开窗口时按账号推导 work tag，人工路径不再共用平台级 session；slugify 保留非 ASCII 身份，做到一账号一巡店窗口。
- 会话新鲜度只认 `saved_at`，30 天过期机制恢复有效；让巡店读取路径与会话写入路径完全一致。

### 入库

- 补齐 `catalog_files` 店铺账号身份，`data_hash` 去重作用域改用稳定身份编号，避免改名后重复入账。

### 语义层

- 区域参与身份匹配，同名品牌店按站点分流；修复第一批语义层改造遗留的 6 条测试回归。

## [v7.12.5] - 2026-11-01 - 把「近30天销量（库存采集）」加到真正在用的积压明细表

### 新增

- 在业务概览真正在用的「高积压风险产品」积压明细表加上「近30天销量（库存采集）」列。

## [v7.12.4] - 2026-11-01 - 把「近30天销量」露到接口与页面

### 新增

- SKU 级滞销清单接口与页面新增「近30天销量」字段，并明确标注它是库存数据域口径（不是销售域口径）。

## [v7.12.3] - 2026-10-31 - 滞销清单近30天动销换源 + 数据库设计校验 API 500 修复

### 修复

- 滞销清单「近30天动销」恒为 0：根因是跨系统对账本身不成立（平台拿「数据来源」比「销售渠道」、两侧 SKU 口径不对称、大小写未归一），改为直接用妙手清单自带的窗口销量（库存数据域口径）。
- 修好 `/api/database-design/*` 全线 500。
- 贴单费未配置时按 0 计，不再让整条利润链算不出来。
- 迁移演练用例改用隔离容器，不再在 CI 上撞本地库。

## [v7.12.2] - 2026-10-31 - SKU 大小写归一 + 库存状态层生产触发路径补齐

### 修复

- 库存侧与订单侧同一件商品 SKU 只有大小写不同就配不上（实测 6 个 SKU、库龄 47~60 天、全部 ≥30 天本来都该进榜）整件漏在榜外；两侧 `sku_key` 统一套 `LOWER()` 归一。
- 库存状态层在生产从不出数的根因定位：「有写入方」不等于「会被写入」，状态层缺稳定触发路径。修法为部署补重建 + 刷新判据从「事件带 `data_domain=inventory`」改成「本次刷新目标含库存事实」。

### 测试

- 修正两条过期的部署契约断言；前端 `manualChunksCycle` 测试在无构建产物时显式跳过（修掉 CI 门禁自己抓出的第 5 个哑测试）。

## [v7.12.1] - 2026-10-31 - 生产视图重建接入部署流程 + 采集同步四批根源性修复

### 部署

- 生产环境原本不会重建改过的视图（`AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP=false`，且刷新与 bootstrap 都跳过已存在的普通视图）。现在由部署脚本 Phase 2.7 / 2.7b 自动重建，失败即中止部署并回滚，不再需要人工去服务器上跑。

### 采集同步

- 四批根源性修复：模板契约、状态语义、统一读表头、变体接管、traffic 收敛。
- 契约晋升：模板升级后被旧契约钉死的文件自动放行。
- 「无模板」落终态，终止 8 个文件的无限重试闭环。
- 兜底入队签名缺陷修复（缺必填参数导致兜底链路 100% 失效）+ 测试库隔离护栏 + 代码新鲜度全树校验。
- 保存发布状态机、家族校验口径与契约失效显式化；域限定列名识别 + 工作台自动归一，打通「源文件变动 → 工作台更新 → 正常同步」。
- 修复模板工作台用视图子集覆盖全量绑定，导致去重字段被静默丢弃。

### 看板

- 滞销榜恒 0 行修复；修正 DB 超时预算倒置并治理 clearance-ranking 慢查询。

## [v7.12.0] - 2026-10-26 - 发版前阻断项修复 + 商品中心 SKU 定价底线 + 库存库龄管道恢复

### 定价

- 新增商品中心 SKU 定价底线（最低售价）与定价纪律规则表：纯计算服务、成本线/纪律线/降级链/档位匹配、迁移与 ORM 骨架、SKU 列表注入定价底线字段、前端定价设置抽屉与利润测算护栏。
- 达人佣金计入利润试算（与最低售价同一口径），利润版本留痕；参考售价表头改黑。
- 最低售价覆盖值未保存时提示「保存后生效」，避免被误读为未生效。

### 库存库龄

- 恢复库存库龄管道（断点定位 + 验收标准），新增 SKU 级滞销排名读模型与服务端点（真库龄口径）。
- 滞销判据换血成「距上次进货天数」；修好库龄刷新从未入队的断链（`DATA_INGESTED` 事件改为 await 入队）。
- 妙手库存字段映射模板 v3（28 列）。
- 库龄看板页新增 SKU 级滞销清单页签；滞销清单视图去掉 8.8 秒的 `backlog_base` 取数路径。

### 采集

- 妙手库存域采集整改：筛选组件按真实页面结构重写、仓库范围筛选定位器按取证修正、日期面板交互修正（收日期必须用 Tab）、维度下拉限定范围。
- B1 增量筛选组件 + B3 水位线与断档补采，水位线增量窗口接进采集执行链；采集后自动 upsert 状态层。
- 采集组件 lint 引擎抽公共模块 + CLI + CI 告警模式；执行器向组件注入 logger 与步骤回调，库存域按阶段上报事件并在失败时留截图。

### 修复

- 数据同步三层收口：收尾不再把正常请求打成 500、就绪判定加缓存与超时保护；并发共享数据库会话导致概览接口 500 的修复 + 两道自动化守卫。
- 数据刷新不再重建普通视图，死锁按可重试处理。
- 补上业务概览积压卡的缓存失效；修本地启动暴露的资产链 DROP 顺序、date_range 契约与漏注册视图问题。
- 发布阻断项：迁移回归、两处 NameError、重复路由、门禁对齐。

### 测试

- 补 data_hash 幂等性的端到端契约测试；堵住另外两个「往真实库写测试用户 + 假通过」的文件。

## [v7.11.25] - 2026-10-17 - 进货价导入脚本与对账工具落地

### 新增

- 新增进货价导入脚本骨架与 xlsx 解析器，用于解析进货价表。
- 新增 `reconcile()` 对账函数与 `fetch_db_sku_keys()` 拉取库内 SKU 主键的辅助函数。
- 新增脚本 CLI 入口、校验查询与报告输出能力。

### 数据

- 新增基于备份与事务的 `apply_update` 更新流程，落库前先生成备份并在事务中执行。

## [v7.11.24] - 2026-09-18 - 前端 nginx 的 IPv6 监听指令移入 server 块

### 修复

- 把 `listen [::]:80;` 从 nginx 配置顶层移入 `server` 块内部。
- 修复前端镜像中该指令作用域不合法导致 nginx 无法正常启动的问题。

## [v7.11.23] - 2026-09-18 - 前端镜像固定 nginx 版本并短路 IPv6 入口

### 修复

- 前端基础镜像的 nginx 版本固定为 `nginx:1.27-alpine`，不再跟随浮动版本。
- 前端容器入口脚本在处理 IPv6 监听时直接短路，跳过原有的 IPv6 分支逻辑。

## [v7.11.22] - 2026-09-18 - 前端健康检查改用 curl

### 修复

- 前端容器健康检查命令由 `wget` 改为 `curl`。
- 避免镜像内缺少 `wget` 导致健康检查持续判定失败。

## [v7.11.21] - 2026-09-18 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:321321`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.20] - 2026-09-18 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:32132`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.19] - 2026-09-17 - 清理根目录临时调试报告并发布后端优化

### 修复

- 移除根目录下遗留的临时调试报告文件。
- 后端完成一轮优化改进。

## [v7.11.18] - 2026-09-17 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:3213`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.17] - 2026-09-17 - 权限模块优化

### 优化

- 对权限相关逻辑做了一轮优化。
- 本版本区间内仅包含这一项权限相关提交，无其他可归纳的功能改动。

## [v7.11.16] - 2026-09-16 - 商品中心物流商规则支持编辑删除

### 新增

- 商品中心的物流商规则支持编辑与删除操作。
- 物流商规则列表按仓库维度排序，加载过程写入日志。

### 修复

- `loadRules` 请求失败时把错误信息透出到前端界面。
- `loadRules` 请求失败时补充表格加载状态处理，并回显鉴权状态便于定位失败原因。

## [v7.11.15] - 2026-09-16 - 前端界面优化

### 优化

- 对前端界面做整体优化，改进页面展示与交互效果。
- 本版本区间内仅包含这一项前端优化提交。

## [v7.11.14] - 2026-09-16 - 商品中心利润工作台与妙手进货库存导出落地

### 新增

- 商品中心新增直营量与利润草稿、人民币仓储参考成本计价、平台 SKU 利润工作台与站点 SKU 经营利润流程。
- 新增妙手进货导出标准 V2 组件 `MiaoshouPurchaseExport` 与妙手库存导出标准 V2 组件 `MiaoshouInventoryExport`，配套 `purchase_config` / `inventory_config` 选择器与 `TargetPage.PURCHASE` 目标页导航分支。

### 修复

- 妙手进货导出改用 `page.expect_download` 捕获下载、移除 `_close_progress_dialog`，并等待进度对话框与搜索结果可见后再操作，状态页签改为通过 URL 参数切换。
- 妙手日期选择器接入 `PurchaseSelectors` 并把触发兜底扩展到进货页标签，进货导出 `preset_map` 补齐英文键以对齐订单与库存导出。
- 采集模块把进货数据域接入快捷采集与配置面板，并在配置模板与店铺能力中启用，未知能力域回填默认值并同步测试断言。
- 商品中心统一人民币成本契约，拒绝未换算的外币采购成本，关闭计费与审计缺口，并消解默认物流规则的选择歧义。

### 数据

- 商品中心主数据与历史利润写入纳入审计，SPU SKU 绑定变更、仓库写入、分类变更全部留痕并对重算成本预估设门禁；利润工作台支持分页并保留规则历史，分类体系调整后重新拉直 current schema 迁移链。

### 文档

- 补记进货导出进度等待、日期选择器兜底与进货前端启用方案的规格与分支历史，并整理分支评审遗留问题。

### 部署

- 发布流程在 PowerShell 下不再因 `git fetch` 进度输出而中断。

## [v7.11.13] - 2026-09-11 - Git 镜像同步治理与商品中心采购物流流程补齐

### 新增

- 商品中心采购物流流程补齐，支持物流商规则与多采购单批次。

### 修复

- Git 镜像同步默认走 GitHub SSH 通道，同时保留 HTTPS 镜像的默认配置不被覆盖。
- 镜像同步捕获 `git fetch` 进度输出，不再因进度信息中断同步。
- 物流批次分摊保留分摊血缘信息。

### 部署

- 治理 GitHub 与 CNB 主分支的镜像同步流程，并补齐对应的契约测试。

### 数据

- 八月重置补充前置校验：重置期间静默写入、无薪资覆盖时阻止重置、管理员身份改由公开角色接口校验，并统一生产店铺佣金月份列口径。
- 清空八月月度业务输入，同时下线周度滞销排名。

## [v7.11.12] - 2026-09-10 - 滞销排名视图契约变更后自动重建

### 修复

- 滞销排名视图在契约发生变更后触发重建，使视图定义与新契约保持一致。

## [v7.11.11] - 2026-09-10 - 商品中心与月度滞销分析接入飞书投影

### 新增

- 新增商品中心与月度滞销分析功能。
- 完成商品成本与飞书投影的收尾实现。

### 修复

- 本地启动流程与 current schema 对齐。
- 加固商品投影与物流契约，并保留库存语义视图的兼容性。
- 记录飞书投影的每一次投递尝试，便于排查投递失败。

### 重构

- 布尔条件改用 SQLAlchemy 谓词表达式实现。

## [v7.11.10] - 2026-09-05 - 费用与月度人事配置流程对齐、八月重置前置校验补齐

### 修复

- 对齐费用流程与月度人事配置流程。
- 八月重置期间静默写入，无薪资覆盖时阻止重置。
- 八月重置的管理员身份改由公开角色接口校验，并补齐八月 V2 重置前置检查。

### 数据

- 清空八月月度业务输入，统一生产店铺佣金月份列口径。

## [v7.11.9] - 2026-08-28 - 清空八月月度业务输入

### 数据

- 清空八月月度业务输入。

## [v7.11.8] - 2026-08-28 - 无薪资覆盖时阻止八月重置

### 修复

- 八月重置前增加薪资覆盖校验，未覆盖时阻止重置执行。

## [v7.11.7] - 2026-08-28 - 重置管理员身份改由公开角色接口校验

### 修复

- 重置操作的管理员身份改由公开角色接口校验。

## [v7.11.6] - 2026-08-28 - 八月 V2 重置前置检查与佣金月份列口径修正

### 修复

- 店铺佣金改用生产环境的月份列口径。
- 支持八月 V2 重置的前置检查流程。

## [v7.11.5] - 2026-08-28 - V2 月度刷新与八月重置自动化

### 新增

- 自动化 V2 月度刷新与八月重置流程。
- 新增生产环境的 V2 dry-run 工作流。

### 部署

- V2 dry-run 改为在已部署的后端容器内执行。

## [v7.11.4] - 2026-08-27 - V2 利润口径拆分迁移到 current schema

### 修复

- 在 current schema 中补齐 V2 利润口径拆分的迁移。

## [v7.11.3] - 2026-08-27 - V2 迁移执行器纳入生产镜像

### 部署

- 将 V2 迁移执行脚本打包进生产镜像。

## [v7.11.2] - 2026-08-27 - 部署备份改为在远端 shell 执行

### 部署

- 部署流程中的备份命令改为在远端 shell 中执行。

## [v7.11.1] - 2026-08-27 - V2 利润口径迁移护栏与人力成本口径统一

### 新增

- 新增受保护的 V2 利润口径迁移 dry-run，迁移不完整时阻断执行。
- 新增带审计的受保护历史重开阶段。
- 人力成本策略改为仅支持 V2，并在人力模块展示固定的 V2 利润口径。

### 修复

- 收入计算中保留 V2 人力分摊状态，校验 V2 人力分摊完整性，并串行化迁移 dry-run 的金额处理。
- 工资刷新统一收敛到 V2 利润口径。
- 店铺状态筛选口径对齐，停用店铺的恢复入口可被发现，切换状态时保留店铺身份信息。

## [v7.11.0] - 2026-08-23 - 个人绩效目标工作台与运营绩效整数化评分落地

### 新增

- 新增个人绩效目标契约与个人绩效目标工作台，配套受控个人绩效服务、工作台 API 与受控目标录入审计。
- 新增运营绩效的整数化评分与自动整数数据契约，支持结构化运营绩效录入，并从受控目录推导运营规则。

### 修复

- 受控个人范围成为判定权威，范围未确认前阻断受控收入发放，部分受控绩效收入按门禁放行。
- 受控个人绩效并发加锁加固，月度绩效依赖串行化，工资确认不再自锁。
- 个人绩效的降级、遗留写入、审计状态与历史月份均加保护，禁止破坏性降级并限制遗留读取。
- 运营绩效结算强制要求运营项完成，无效运营规则阻断完成，评分快照与店铺身份在运营条目中保留。

### 数据

- 新增仅面向门店的运营目录 v3，并保护运营目录版本历史。

### 测试

- 补充受控个人结果降级、个人目标迁移往返、绩效锁定与运营结算收入等测试，并更新 current schema 头契约测试。

### 文档

- 编写个人绩效目标工作台的设计文档，明确自动运营绩效评分与运营店铺范围口径。

## [v7.10.3] - 2026-08-17 - 迁移备份辅助脚本纳入后端镜像

### 部署

- 将迁移备份辅助脚本打包进后端镜像。

## [v7.10.2] - 2026-08-17 - 月度运营绩效工作台落地与本地重建流程加固

### 新增

- 实现月度运营绩效工作台，并完成绩效模块的整体优化。
- 本地采集迁移启动流程加固，增强重建过程的诊断信息。

### 修复

- 本地重建直接加载本地重建环境，校验并拒绝非法重建 URL，校验重建目标身份，展示受保护的重建计划，并收敛仪表盘就绪检查范围。
- 本地重建保留连接凭证，本地管理引导的配置与目标范围被隔离并受限。
- 本地控制台启动恢复正式采集控制台启动，简化开发态启动流程并保证离线可用。
- 迁移备份脚本输出按 UTF-8 解码，避免中文乱码导致解析失败。

## [v7.10.1] - 2026-08-10 - 发版 CI 门禁打通与运营数据迁移隔离加固

### 修复

- 打通 v7.10.1 发版 CI 门禁，同时保持发布 compose 校验过程输出安静。
- 隔离 v7.10.1 的遗留运营目标，隔离环境下的运营发布迁移进一步加固。
- 数据库中冻结遗留运营记录，切换期间共享基础设施网络，回滚时保留遗留运营写入。

### 测试

- 部署网络集成测试改为按需开启，默认不进入常规门禁。

## [v7.10.0] - 2026-08-10 - 月度运营绩效工作台设计与 current schema 迁移链建立

### 新增

- 新增月度运营绩效工作台。
- 新增店铺订单指标预占能力。

### 修复

- 发版前置检查加入 current schema 校验。
- 支持仅个人参与的绩效结算。
- 已结算工资的绩效重算加锁，避免结算后被改写。

### 重构

- 建立 current schema 的迁移链。

### 文档

- 完成运营绩效工作台的设计文档，补充结算设计的安全护栏。

## [v7.9.3] - 2026-08-06 - 本地控制台输出保持可见

### 修复

- 修复本地控制台输出不可见的问题。

## [v7.9.2] - 2026-08-05 - 工资结算锁定与成本佣金输入冻结

### 新增

- 完成工资结算锁定。
- 工资成本与佣金输入在结算后被锁定不可修改。

### 修复

- 迁移测试改用临时可用端口，解决端口占用问题。
- 复制月度店铺指派数据，避免月度切换时丢失归属关系。

## [v7.9.1] - 2026-08-05 - 基于工资投影人力成本与本地运维控制台

### 新增

- 新增本地运维控制台。
- 人力成本改为基于工资数据投影计算。

## [v7.9.0] - 2026-08-04 - 员工目标统一为店铺共享责任

### 新增

- 员工目标口径统一为店铺维度的共享责任。

## [v7.8.11] - 2026-08-04 - 月度绩效统一百分制并对齐结算利润口径

### 新增

- 月度绩效统一为 100 分制刻度，绩效口径与结算利润口径对齐。

### 修复

- 发布时初始化云同步接收端。
- 可选的绩效配置迁移增加护栏，避免配置缺失时迁移失败。

### 文档

- 补充绩效收入计算方式的说明文档。

## [v7.8.10] - 2026-08-03 - 回填历史目标分配比例

### 数据

- 回填历史月度目标的分配比例数据。

## [v7.8.9] - 2026-08-03 - 员工目标分配契约与月度绩效结算补全

### 新增

- 新增员工目标分配契约。
- 统一账号边界与员工目标口径。

### 修复

- 补全月度绩效结算流程。

## [v7.8.8] - 2026-07-07 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:321231`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.8.7] - 2026-07-07 - 采集动态时间窗口与本地 PWCLI 检查面板

### 新增

- 采集支持动态时间窗口，并新增批量时间策略控制项。
- 新增本地 PWCLI 检查面板。

### 修复

- 修复 Shopee 月度订单金额被覆盖的问题。
- 妙手自定义日期区间输入框交互稳定化，动态时间窗口按自定义区间方式执行。

### 优化

- PWCLI 会话保存时机改由用户自行决定。

### 文档

- 明确 PWCLI 面板的保存流程。

## [v7.8.6] - 2026-06-29 - CNB 镜像同步流程简化与生产启动加固

### 部署

- 简化 CNB 的 Git 同步流程。
- 加固生产环境启动流程与 CNB 镜像同步。

## [v7.8.5] - 2026-06-29 - 生产部署迁移门禁加固

### 部署

- 加固生产部署的迁移门禁，发版前必须通过迁移校验。
- 本版本区间内没有额外功能提交，属于迁移门禁加固的发布版本。

## [v7.8.2] - 2026-06-29 - 生产部署迁移门禁加固

### 部署

- 加固生产部署的迁移门禁，发版前必须通过迁移校验。

## [v7.8.1] - 2026-06-29 - 云同步自动恢复与生命周期监控加固

### 新增

- 自动化云同步恢复流程。
- 加固云同步的生命周期管理与监控能力。

### 修复

- 云同步完成后的自动刷新逻辑加固。

### 部署

- 更新本地配置、依赖与部署文档。

## [v7.5.7] - 2026-06-24 - 订单类模板治理非破坏性放宽

### 修复

- 订单类模板的治理规则放宽，容许不破坏既有结构的变更。

### 发布

- 本版本区间内另含一条说明为占位文本的提交（`feat:321321`）。

## [v7.5.6] - 2026-06-23 - 模板哈希键按语义绑定归一与自动刷新优化

### 修复

- 模板哈希键按语义绑定归一化，避免同一语义的键产生不同哈希值。

### 优化

- 自动刷新与自动任务流程得到优化。

## [v7.5.2] - 2026-06-19 - 上线部署版本

### 部署

- 完成本版本的上线部署。
- 本版本区间内没有功能提交，属于纯部署发布版本。

## [v7.5.1] - 2026-06-19 - 店铺身份标准化与语义哈希治理、云同步自恢复

### 新增

- 店铺身份采集流程标准化。
- 远端同步能力可用，并支持恢复卡死的云同步任务。
- 云同步 SSH 隧道可自动启动。
- 新增语义契约模板治理与语义哈希策略治理，动态模板哈希选项一并修正。

### 修复

- 统一人力佣金与利润底线口径。
- 采集任务启动方式标准化。

### 部署

- 完成本版本的上线部署。

## [v7.2.9] - 2026-06-11 - 业务概览模块布局紧凑化与模板更新工作台收尾

### 优化

- 业务概览模块布局改为紧凑排布。
- 业务概览排名趋势展示优化。
- 前端界面与排版整体优化。

### 修复

- 模板更新工作台与仪表盘交互细节收尾修正。

## [v7.2.8] - 2026-06-10 - 上传功能修复

### 修复

- 修复上传链路的问题。
- 本版本区间内仅包含这一项上传相关改动。

## [v7.2.7] - 2026-06-09 - 自动入库任务治理加固与伴随日期身份哈希自动化

### 新增

- 自动化计算伴随日期的身份哈希。

### 修复

- 加固自动入库任务的治理能力。
- 约束模板语义哈希参与计算的字段范围。
- 加固自动入库重建流程的恢复能力。

### 部署

- 完成上线准备与落地优化。

## [v7.2.2] - 2026-06-09 - Shopee 店铺身份采集流程加固

### 修复

- 加固 Shopee 店铺身份采集流程。

### 重构

- 统一格式化 v7.2.1 的数据入库改动代码。

## [v7.2.1] - 2026-06-09 - B 类产品月报入库日期异常修复

### 修复

- 修复 Shopee products monthly 自动入库在线程池内丢失文件日期、模板日期规则和表头绑定上下文的问题。
- 阻断 B 类入库在无可靠业务日期时使用处理当天作为 `metric_date` 静默写入。
- 对带 `catalog_files.date_from/date_to` 的入库结果增加业务日期范围校验，防止 4/5 月文件写入 6 月业务日期。
- 修正 Shopee products monthly 的模板规则来源和 UPSERT 更新字段，使月报按文件月份入库并可正确更新。
- 修复 `sales_targets_a` 平台列迁移，兼容 fresh DB 的 `shop_id/year_month` 列和生产库旧中文列。

### 数据

- 清理并重入库 14 个 2026-06-08 处理的 Shopee products monthly 异常文件，近期异常日期扫描归零。

## [Unreleased] - 组件版本管理模块重构 (optimize-component-version-management)

### 组件版本管理

- 组件版本测试执行一致性：测试时执行 `version.file_path` 对应实现，adapter 支持 override 注入
- 生产执行器按 file_path 加载：`_load_component_with_version` 使用 `load_python_component_from_path`，`_execute_python_component` 当 component dict 含 `_python_component_class` 时直接使用该类
- 删除规则放宽：可删除条件调整为 `!is_testing && !is_active`，稳定版禁用后也可删除
- 验证码步骤 unconditional 暂停：图形验证码步骤到达即等待 1s → 截图 → raise VerificationRequiredError
- 实际执行文件展示：版本列表增加 file_path 列
- 录制保存创建新版本：component_name 由 platform+component_type+data_domain+sub_domain 推导；版本号应用层语义解析递增；新版本默认非稳定
- 前端 export 保存传 data_domain/sub_domain

### 新增

- `backend/services/component_name_utils.py`：component_name 标准化、版本号解析
- `ComponentLoader.load_python_component_from_path`：按 file_path 加载，模块名唯一避免 sys.modules 污染

---

## [v4.20.0] - 2026-01-08 - 系统管理模块 API 完整实现

### 核心功能

#### 1. 系统日志与审计日志增强

- ✅ 系统日志 API（`GET /api/system/logs`）
  - 支持按级别、模块、用户、时间范围筛选
  - 分页查询（最大 100 条/页）
  - 日志详情查看（`GET /api/system/logs/{log_id}`）
  - 日志导出（Excel/CSV 格式）
  - 清空日志功能（管理员权限）
- ✅ 审计日志增强
  - 增强筛选功能（操作类型、资源类型、用户、IP 地址、时间范围）
  - 审计日志详情查看（包含变更前后对比）
  - 审计日志导出功能

#### 2. 安全设置 API

- ✅ 密码策略管理（`GET/PUT /api/security/password-policy`）
  - 最小长度、复杂度要求、过期时间、历史密码检查
  - 动态配置，实时生效
- ✅ 登录限制配置（`GET/PUT /api/security/login-restrictions`）
  - 最大失败尝试次数、账户锁定时长
  - IP 白名单管理（`GET/POST/DELETE /api/security/ip-whitelist`）
  - 动态配置，替换硬编码常量
- ✅ 会话管理配置（`GET/PUT /api/security/session-config`）
  - 会话超时时间、并发会话限制
  - 支持动态配置会话超时（集成到 auth_service）
- ✅ 2FA 配置（`GET/PUT /api/security/2fa-config`）
  - 启用/禁用 2FA、强制要求 2FA

#### 3. 数据备份与恢复 API

- ✅ 数据备份功能（`POST /api/backup/create`）
  - 支持数据库备份、文件备份、完整备份
  - Docker 环境适配（使用 pg_dump、tar、zip）
  - 备份记录管理（`GET /api/backup/list`）
  - 备份下载（`GET /api/backup/{backup_id}/download`）
- ✅ 数据恢复功能（`POST /api/backup/{backup_id}/restore`）
  - 多重安全防护（维护窗口检查、多管理员确认、强制确认）
  - 备份验证、恢复前自动备份
  - 恢复状态跟踪
- ✅ 自动备份配置（`GET/PUT /api/backup/auto-config`）
  - 备份频率、保留策略、备份时间窗口

#### 4. 系统维护 API

- ✅ 缓存清理（`GET/POST /api/maintenance/cache/*`）
  - Redis 缓存状态查询
  - 按类型清理缓存（全部、用户会话、数据缓存）
  - Docker 环境适配（redis:6379）
- ✅ 数据清理（`GET/POST /api/maintenance/data/*`）
  - 系统日志清理、临时文件清理
  - 数据状态查询
  - 安全措施（管理员权限、确认机制）
- ✅ 系统升级（`GET/POST /api/maintenance/upgrade/*`）
  - 升级检查、升级执行
  - 多重确认、自动备份
  - P3 功能，不推荐使用（建议通过 CI/CD 完成）

#### 5. 通知配置 API

- ✅ SMTP 配置（`GET/PUT /api/notification-config/smtp`）
  - SMTP 服务器配置（服务器、端口、TLS、用户名、密码）
  - 密码加密存储
  - 连接测试、测试邮件发送
- ✅ 通知模板管理（`CRUD /api/notification-config/templates`）
  - 模板类型（系统通知、告警通知、审批通知）
  - 模板变量支持
  - 模板激活/停用
- ✅ 告警规则管理（`CRUD /api/notification-config/alert-rules`）
  - 告警级别（critical、warning、info）
  - 告警条件（JSON 格式）
  - 通知方式（email、sms、in_app）
  - 通知对象配置

#### 6. 系统配置增强 API

- ✅ 系统基础配置（`GET/PUT /api/system/config`）
  - 系统名称、版本、时区、语言、货币
  - 配置持久化存储（SystemConfig 表）
- ✅ 数据库配置（`GET/PUT /api/system/database/config`）
  - 数据库连接信息查看（敏感字段加密）
  - 数据库配置更新（保存为 pending 状态）
  - 数据库连接测试（`POST /api/system/database/test-connection`）
  - Docker 环境适配（从容器环境变量读取）

#### 7. 权限管理增强 API

- ✅ 权限树 API（`GET /api/permissions/tree`）
  - 按模块分组的权限树结构
  - 支持层级展示
- ✅ 权限列表 API（`GET /api/system/permissions`）
  - 系统预定义权限列表（60+权限）
  - 支持按分类筛选
  - 权限树结构（`GET /api/system/permissions/tree`）

### 技术改进

#### 架构合规性

- ✅ 100% SSOT 合规（所有 ORM 模型在`modules/core/db/schema.py`定义）
- ✅ Contract-First 开发（所有 API 先定义 Pydantic 模型，后实现业务逻辑）
- ✅ 异步架构统一（所有服务类仅支持 AsyncSession）
- ✅ 路由前缀统一（`/api/system/*`、`/api/security/*`等）

#### 数据模型

- ✅ 新增表：`system_logs`、`security_config`、`backup_records`、`smtp_config`、`notification_templates`、`alert_rules`、`system_config`
- ✅ 数据库迁移脚本（手动执行，避免 Alembic 编码问题）

#### 安全措施

- ✅ 所有管理 API 需要管理员权限（`require_admin`）
- ✅ 敏感数据加密存储（密码、SMTP 密码）
- ✅ 限流保护（`role_based_rate_limit`）
- ✅ 输入验证（Pydantic 模型验证）
- ✅ 审计日志记录（所有配置变更）

#### Docker 环境适配

- ✅ 数据库备份使用`pg_dump`连接`postgres:5432`
- ✅ 文件备份使用容器内部路径（`/app/data`、`/app/downloads`、`/app/logs`）
- ✅ Redis 连接使用`redis:6379`
- ✅ 数据库配置从容器环境变量读取

### 前端集成

- ✅ 创建`frontend/src/api/system.js`，包含所有系统管理 API 客户端函数
- ✅ 支持系统日志、安全设置、备份恢复、系统维护、通知配置、系统配置、权限管理等所有 API

### 文档更新

- ✅ 更新`CHANGELOG.md`
- ✅ API 文档自动生成（OpenAPI/Swagger）

### 已知限制

- ⚠️ 数据恢复实际逻辑需要 Celery 异步任务支持（基础框架已完成）
- ⚠️ 自动备份配置需要集成到 Celery 定时任务
- ⚠️ 系统升级功能标记为 P3（不推荐使用），建议通过 CI/CD 完成
- ⚠️ 通知模板变量替换需要在使用时实现
- ⚠️ 告警规则触发逻辑需要监控系统支持

---

## [v4.19.0] - 2026-01-05 - 用户注册审批与账户管理

### 核心功能

#### 1. 用户注册与审批流程

- ✅ 新增用户注册功能（`POST /api/auth/register`）
  - 支持用户名、邮箱、密码、姓名等信息注册
  - 密码强度验证（至少 8 位，包含字母和数字）
  - 统一错误消息（防止用户名/邮箱枚举攻击）
  - 注册频率限制（5 次/分钟）
- ✅ 用户状态管理
  - pending（待审批）：注册成功，等待管理员审批
  - active（已激活）：审批通过，可以正常使用
  - rejected（已拒绝）：审批被拒绝
  - suspended（已暂停）：账户被管理员暂停
- ✅ 数据库触发器自动同步`status`和`is_active`字段
- ✅ 用户审批记录表（`user_approval_logs`）记录所有审批操作

#### 2. 管理员审批功能

- ✅ 待审批用户列表（`GET /api/users/pending`）
- ✅ 批准用户（`POST /api/users/{user_id}/approve`）
  - 自动分配默认角色（operator）
  - 记录审批日志
- ✅ 拒绝用户（`POST /api/users/{user_id}/reject`）
  - 必须填写拒绝原因
  - 记录拒绝日志
- ✅ 用户审批页面（`/admin/users/pending`）

#### 3. 密码管理

- ✅ 密码重置功能（`POST /api/users/{user_id}/reset-password`）
  - 管理员可以重置用户密码
  - 支持指定新密码或生成临时密码
  - 重置后清除账户锁定状态
- ✅ 账户锁定机制
  - 5 次登录失败后锁定账户 30 分钟
  - 管理员可以手动解锁账户（`POST /api/users/{user_id}/unlock`）
  - 登录失败次数记录（`failed_login_attempts`）

#### 4. 会话管理

- ✅ 会话记录表（`user_sessions`）
  - 记录用户登录会话信息（设备、IP、登录时间、最后活跃时间）
  - 支持会话过期时间管理
- ✅ 会话管理 API
  - 获取活跃会话列表（`GET /api/users/me/sessions`）
  - 撤销指定会话（`DELETE /api/users/me/sessions/{session_id}`）
  - 撤销所有其他会话（`DELETE /api/users/me/sessions`）
- ✅ 会话管理页面（`/settings/sessions`）
  - 显示活跃会话列表
  - 当前设备标识
  - 登出此设备/登出所有其他设备

#### 5. 系统通知机制

- ✅ 通知数据模型（`Notification`表）
  - 通知类型：user_registered, user_approved, user_rejected, password_reset, account_locked, account_unlocked, user_suspended, system_alert
  - 支持未读/已读状态管理
  - 支持关联用户信息
  - **新增优先级字段**（high/medium/low）
- ✅ 通知 API
  - 获取通知列表（`GET /api/notifications`）- 支持分页、过滤和优先级排序
  - 获取分组通知列表（`GET /api/notifications/grouped`）- 按类型分组统计
  - 获取未读数量（`GET /api/notifications/unread-count`）
  - 标记已读（`PUT /api/notifications/{id}/read`）
  - 标记全部已读（`PUT /api/notifications/read-all`）
  - 删除通知（`DELETE /api/notifications/{id}`）
  - **新增快速操作 API**（`POST /api/notifications/{id}/action`）
- ✅ 自动通知触发
  - 新用户注册时通知所有管理员（高优先级）
  - 用户审批通过时通知用户
  - 用户审批拒绝时通知用户
  - 密码重置时通知用户
  - 账户锁定/解锁时通知用户
  - 账户被暂停时通知用户
- ✅ **WebSocket 实时通知**
  - JWT 认证的 WebSocket 连接（`/api/ws`）
  - 实时推送通知到用户
  - 心跳机制和自动重连
  - 连接数限制和速率限制
  - 降级到 HTTP 轮询
- ✅ **浏览器原生通知**
  - 通知权限管理
  - 桌面通知显示（可配置）
  - 通知偏好设置（`/settings/notifications`）
  - 内容验证和 XSS 防护
- ✅ **通知快速操作**
  - 从通知面板直接批准/拒绝用户
  - 完整权限验证和审计日志
- ✅ **通知分组和优先级**
  - 按类型分组显示通知
  - 高优先级通知特殊样式
  - 优先级筛选功能
- ✅ 前端通知组件
  - 顶部栏通知图标（带未读数量徽章）
  - 通知下拉面板（最近 10 条通知，带快速操作按钮）
  - WebSocket 实时更新未读数量
  - 通知列表页面（支持过滤、分页、批量操作、分组视图）

#### 6. 前端实现

- ✅ 登录页面（`/login`）
  - 支持用户名/密码登录
  - 账户状态检查（pending/rejected/suspended/inactive）
  - 账户锁定提示
  - Open Redirect 防护
- ✅ 注册页面（`/register`）
  - 用户注册表单
  - 密码强度提示
  - 注册成功提示
- ✅ 路由守卫
  - 登录状态检查
  - 权限验证
  - 公开路由处理

### 数据库变更

#### 新增字段（`dim_users`表）

- `status` (VARCHAR): 用户状态（pending/active/rejected/suspended/deleted）
- `approved_at` (TIMESTAMP): 审批时间
- `approved_by` (BIGINT): 审批人 ID（外键）
- `rejection_reason` (TEXT): 拒绝原因
- `failed_login_attempts` (INTEGER): 登录失败次数
- `locked_until` (TIMESTAMP): 账户锁定截止时间

#### 新增表

- `user_approval_logs`: 用户审批记录表
- `user_sessions`: 用户会话表
- `notifications`: 系统通知表

#### 数据库触发器

- 自动同步`status`和`is_active`字段

### API 变更

#### 新增端点

- `POST /api/auth/register` - 用户注册
- `GET /api/users/pending` - 获取待审批用户列表
- `POST /api/users/{user_id}/approve` - 批准用户
- `POST /api/users/{user_id}/reject` - 拒绝用户
- `POST /api/users/{user_id}/reset-password` - 重置用户密码
- `POST /api/users/{user_id}/unlock` - 解锁用户账户
- `GET /api/users/me/sessions` - 获取活跃会话列表
- `DELETE /api/users/me/sessions/{session_id}` - 撤销指定会话
- `DELETE /api/users/me/sessions` - 撤销所有其他会话
- `GET /api/notifications` - 获取通知列表
- `GET /api/notifications/unread-count` - 获取未读通知数量
- `GET /api/notifications/{id}` - 获取单个通知详情
- `PUT /api/notifications/{id}/read` - 标记单个通知为已读
- `PUT /api/notifications/read-all` - 标记全部通知为已读
- `DELETE /api/notifications/{id}` - 删除单个通知
- `DELETE /api/notifications` - 删除所有已读通知

#### 修改端点

- `POST /api/auth/login` - 增强用户状态检查、账户锁定检查、会话创建
- `POST /api/auth/refresh` - 更新会话`last_active_at`

### 错误代码

新增错误代码（4005-4010）：

- `4005`: AUTH_ACCOUNT_PENDING - 账号待审批
- `4006`: AUTH_ACCOUNT_REJECTED - 账号已拒绝
- `4007`: AUTH_ACCOUNT_SUSPENDED - 账号已暂停
- `4008`: AUTH_ACCOUNT_INACTIVE - 账号未激活
- `4009`: AUTH_ACCOUNT_LOCKED - 账号已锁定
- `4010`: AUTH_ACCOUNT_NOT_LOCKED - 账号未锁定

### 安全增强

- ✅ 统一错误消息（防止用户名/邮箱枚举攻击）
- ✅ 注册 API 限流（5 次/分钟）
- ✅ 账户锁定机制（5 次失败锁定 30 分钟）
- ✅ Open Redirect 防护（前端验证 redirect 参数）
- ✅ 会话管理（支持查看和撤销活跃会话）

### 测试

- ✅ 安全测试（限流、枚举攻击、权限绕过、Open Redirect、CSRF）
- ✅ 单元测试（注册 API、审批 API、登录 API）
- ✅ 集成测试（完整注册-审批-登录流程）

### 文档

- ✅ 用户注册指南（`docs/guides/USER_REGISTRATION_GUIDE.md`）
- ✅ 管理员审批指南（`docs/guides/ADMIN_APPROVAL_GUIDE.md`）
- ✅ 测试总结（`backend/tests/TEST_SUMMARY.md`）
- ✅ 测试指南（`backend/tests/README_TESTING.md`）

### 迁移说明

1. **数据库迁移**

   - 运行迁移脚本添加新字段和表
   - 确保`operator`角色存在
   - 创建数据库触发器

2. **现有用户处理**

   - 现有用户状态自动设置为"active"
   - `is_active`字段自动同步

3. **管理员账号创建**
   - 使用`scripts/create_admin_user.py`创建管理员账号
   - 默认管理员：用户名`xihong`，密码`~!Qq1`1`

### 已知问题

无

### 后续计划

- Phase 5: 通知机制（可选）
  - 新用户注册时通知管理员
  - 审批结果通知用户

---

## [v4.8.0] - 2025-12-29 - 数据采集模块异步化改造与 Python 组件集成

### 核心改造

#### 1. Python 组件异步化

- 将 38 个平台组件从同步转为异步 (`def run` -> `async def run`)
- Shopee 平台: 17 个组件 (login, navigation, orders_export, products_export 等)
- TikTok 平台: 12 个组件 (login, navigation, date_picker, shop_selector 等)
- Miaoshou 平台: 9 个组件 (login, navigation, export, overlay_guard 等)

#### 2. Python 组件适配层

- 新增 `modules/apps/collection_center/python_component_adapter.py`
- `PythonComponentAdapter` 类提供统一的组件调用接口
- 支持 `login()`, `navigate()`, `export()`, `call_component()` 方法
- 自动密码解密 (`EncryptionService.decrypt_password()`)

#### 3. Executor V2 重构

- 添加 `use_python_components = True` 配置开关
- 新增 `_execute_python_component()` 方法
- 新增 `_execute_with_python_components()` 完整执行流程
- 支持直接调用 Python 组件，跳过 YAML 解析

#### 4. 组件加载器增强

- 新增 `load_python_component()` 方法
- 新增 `validate_python_component()` 方法
- 新增 `list_python_components()` 方法
- 支持通过 inspect 模块读取组件元数据

#### 5. 录制工具优化

- 移除 Codegen 模式支持
- 统一使用 Inspector 模式 (`page.pause()` + Trace)
- 移除 `_launch_playwright_codegen_subprocess()` 函数

#### 6. TraceParser 增强

- 新增 `generate_python_skeleton()` 方法
- 支持从 Trace 文件生成 Python 组件骨架代码
- 新增 `generate_component_from_trace()` 便捷函数

### 数据同步对齐（v4.8.0 新增）

#### 7. 文件命名标准化

- 使用 `StandardFileName.generate()` 生成标准文件名
- 格式: `{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.xlsx`
- 与数据同步模块完全对齐

#### 8. 文件存储路径标准化

- 采集完成后移动文件到 `data/raw/YYYY/` 目录
- 数据同步模块仅扫描此目录
- 自动删除临时文件

#### 9. 伴生文件格式标准化

- 使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件
- 伴生文件与数据文件在同一目录
- 包含 `business_metadata` 和 `collection_info` 完整元数据

#### 10. 文件注册自动化

- 采集完成后自动调用 `register_single_file()` 注册到 `catalog_files` 表
- 添加注册失败的错误处理和日志

#### 11. Python 组件测试工具更新

- 更新 `tools/test_component.py` 支持 Python 组件加载和测试
- 更新 `tools/run_component_test.py` 支持 `.py` 文件路径
- 更新 `backend/routers/component_versions.py` 支持 Python 组件测试
- 新增 `test_python_component()` 和 `_test_python_component_with_browser()` 方法

### 组件管理功能完善（v4.8.0 第二阶段）

#### 12. YAML 组件清理

- 新增 `scripts/cleanup_yaml_components.py` 清理脚本
- 支持将 YAML 文件移动到 `backups/yaml_components_YYYYMMDD/`
- 支持禁用 ComponentVersion 表中的 YAML 记录
- 支持 `--dry-run` 预览模式

#### 13. Python 组件批量注册

- 新增 `scripts/register_python_components.py` 批量注册脚本
- 扫描 `modules/platforms/` 下所有 Python 组件
- 自动读取组件元数据并注册到 ComponentVersion 表
- 支持 `--platform` 和 `--dry-run` 参数

#### 14. 批量注册 API

- 新增 `POST /component-versions/batch-register-python` API 端点
- 返回注册统计和详细结果
- 支持指定平台过滤

#### 15. 组件录制工具保存逻辑更新

- `RecorderSaveRequest` 模型支持 `python_code` 和 `data_domain`
- 保存 Python 组件到 `modules/platforms/{platform}/components/`
- Python 代码语法验证（`ast.parse`）
- 更新覆盖逻辑：文件路径相同时更新现有版本

#### 16. 前端组件管理功能

- 添加"批量注册 Python 组件"按钮
- 版本列表显示组件类型（Python/YAML）
- 新增 `batchRegisterPythonComponents` API 方法

#### 17. 稳定版本唯一性保证

- 增强 `promote_to_stable()` 方法
- 自动取消相同 component_name 的其他稳定版本
- 自动取消相同 file_path 的其他稳定版本

### Windows 兼容性

#### 日志 Emoji 替换

- 创建 `scripts/verify_no_emoji.py` 验证脚本
- 替换 `modules/platforms/` 下所有 emoji 为 ASCII 符号
- 标准替换: [OK], [FAIL], [WARN], [SCAN]

### 新增文件

- `modules/apps/collection_center/python_component_adapter.py` - Python 组件适配层
- `scripts/async_component_transformer.py` - 异步改造辅助脚本
- `scripts/verify_no_emoji.py` - Emoji 验证脚本
- `scripts/cleanup_yaml_components.py` - YAML 组件清理脚本
- `scripts/register_python_components.py` - Python 组件批量注册脚本
- `docs/guides/PYTHON_COMPONENT_TEMPLATE.md` - Python 组件编写模板

### 修改文件

- `modules/apps/collection_center/executor_v2.py` - 添加 Python 组件支持 + 文件处理对齐
- `modules/apps/collection_center/component_loader.py` - 添加 Python 组件加载
- `backend/routers/component_recorder.py` - 移除 Codegen 模式 + Python 组件保存
- `backend/routers/component_versions.py` - 支持 Python 组件测试 + 批量注册 API
- `backend/services/component_version_service.py` - 增强稳定版本唯一性保证
- `backend/utils/trace_parser.py` - 添加 Python 骨架生成
- `tools/test_component.py` - 支持 Python 组件测试
- `tools/run_component_test.py` - 支持 Python 组件路径
- `frontend/src/views/ComponentVersions.vue` - 批量注册按钮 + 组件类型显示
- `frontend/src/api/index.js` - 批量注册 API 方法
- `modules/platforms/*/components/*.py` - 异步化 + emoji 替换

### 验收标准 (已完成)

1. [OK] 所有 38 个 Python 组件成功转为异步版本
2. [OK] executor_v2 支持 Python 组件执行
3. [OK] 登录组件使用统一的密码解密逻辑
4. [OK] Windows 控制台无 UnicodeEncodeError (核心组件)
5. [OK] 组件加载器支持 Python 组件加载
6. [OK] 录制工具仅支持 Inspector 模式
7. [OK] Python 组件支持调用子组件
8. [OK] Trace 解析器生成 Python 代码骨架
9. [OK] 文件命名使用 StandardFileName.generate()
10. [OK] 采集文件保存到 data/raw/YYYY/ 目录
11. [OK] 伴生文件使用 .meta.json 格式
12. [OK] 文件自动注册到 catalog_files 表
13. [OK] Python 组件测试工具可正常使用
14. [OK] 架构验证脚本通过

---

## [v4.16.0] - 2025-12-08 - 数据库架构统一和端口配置优化

### 🚨 重大修复

#### 1. 解决双数据库数据分散问题

- ⭐⭐⭐ **问题根因**：本地 PostgreSQL 18 和 Docker PostgreSQL 15 同时运行，数据分散在两个数据库
- ⭐⭐⭐ **数据迁移**：将本地 PostgreSQL 的所有数据（72.63MB）迁移到 Docker PostgreSQL
- ⭐⭐⭐ **端口统一**：使用 15432 端口（避开 Windows 保留端口 5433-5832）
- ⭐⭐⭐ **服务禁用**：永久禁用本地 PostgreSQL 服务，防止端口冲突

#### 2. 配置文件更新

- ✅ `.env` - POSTGRES_PORT=15432, DATABASE_URL 更新
- ✅ `env.example` - 端口配置示例更新为 15432
- ✅ `backend/utils/config.py` - 默认端口改为 15432
- ✅ `docker/postgres/init-tables.py` - 默认连接 URL 更新

#### 3. .env 文件编码修复

- ✅ 修复 UnicodeDecodeError 编码问题
- ✅ 确保 .env 文件使用 UTF-8 编码

### 📊 数据库状态（迁移后）

| Schema  | 表数量 | 说明                                |
| ------- | ------ | ----------------------------------- |
| a_class | 7      | A 类配置数据                        |
| b_class | 28     | B 类业务数据（含 26 个 fact\_\*表） |
| c_class | 4      | C 类计算数据                        |
| core    | 18     | 核心系统表                          |
| public  | 106    | 公共表                              |

### 🔧 连接配置

| 组件        | 主机                 | 端口  |
| ----------- | -------------------- | ----- |
| Python 后端 | localhost            | 15432 |
| Metabase    | host.docker.internal | 15432 |
| pgAdmin     | postgres             | 5432  |

### 📄 新增文档

- `docs/DATABASE_MIGRATION_COMPLETE.md` - 迁移完成报告
- `docs/DATABASE_ARCHITECTURE_PROPOSAL.md` - 架构提案和预防措施

### ⚠️ 注意事项

- 本地 PostgreSQL 服务已永久禁用（StartupType=Disabled）
- 云端部署时可根据需要调整 POSTGRES_PORT
- 所有组件必须连接到同一个 Docker PostgreSQL 实例

---

## [v4.15.0] - 2025-12-05 - 优化数据同步以适应实际工作场景 ⭐

### 🎯 核心优化

#### 1. 货币代码变体识别

### 🎯 核心优化

#### 1. 货币代码变体识别

- ⭐ **智能表头变化检测**：识别货币代码变体（如 BRL、COP、SGD），将其视为同一字段的不同变体
- ⭐ **字段名归一化**：在表头变化检测前，将货币变体字段归一化为基础字段名（移除货币代码）
- ⭐ **货币代码提取**：从字段名中提取货币代码，存储到`currency_code`系统字段（String(3)）
- ⭐ **数据存储优化**：
  - `raw_data` JSONB 中字段名归一化（不含货币代码）
  - `currency_code`字段存储货币代码
  - `header_columns`保留原始字段名（含货币代码）
- ⭐ **智能匹配策略**：
  - 如果只有货币代码差异，视为匹配（不触发变化检测）
  - 如果还有其他字段变化，正常触发变化检测

#### 2. 库存数据 UPSERT 策略

- ⭐ **UPSERT 策略**：对于库存数据域，使用 UPSERT（INSERT ... ON CONFLICT ... UPDATE）而非 INSERT ... ON CONFLICT DO NOTHING
- ⭐ **更新字段配置**：定义哪些字段在冲突时应该更新
  - 更新字段：`raw_data`, `ingest_timestamp`, `file_id`, `header_columns`, `currency_code`
  - 保留字段：`metric_date`, `platform_code`, `shop_id`, `data_domain`, `granularity`, `data_hash`
- ⭐ **数据域特定策略**：
  - `inventory`域：使用 UPSERT（更新而非插入）
  - 其他域（orders/products/traffic/services/analytics）：使用 INSERT（跳过重复）

### 📊 数据库变更

- ✅ 所有 `fact_raw_data_*` 表新增 `currency_code` 字段（VARCHAR(3), nullable=True, index=True）

### 🔧 技术实现

#### 新增文件

- `backend/services/currency_extractor.py` - 货币代码提取和字段名归一化服务

#### 修改文件

- `backend/services/template_matcher.py` - 表头变化检测（货币变体识别）
- `backend/services/data_ingestion_service.py` - 数据入库时提取和存储货币代码
- `backend/services/raw_data_importer.py` - UPSERT 实现和 currency_code 字段存储
- `backend/services/deduplication_fields_config.py` - 策略和更新字段配置

### ✅ 测试

- ✅ 货币变体识别测试（16 个测试用例全部通过）
- ✅ 表头变化检测测试（2 个测试用例全部通过）
- ✅ 去重策略配置测试（7 个测试用例全部通过）
- ✅ 性能测试（字段名归一化和货币代码提取性能影响<0.5%）

### 📈 性能影响

- **写入性能影响**：<0.5%（几乎可忽略）
- **查询性能提升**：10-100 倍（按货币筛选可以使用索引）

### 📝 文档

- ✅ 新增文档：`docs/V4_15_0_DATA_SYNC_OPTIMIZATION.md` - 完整的功能说明和使用指南
- ✅ 新增文档：`docs/V4_15_0_EMPTY_FILE_HANDLING.md` - 空文件处理策略说明

### 🐛 Bug 修复

#### 空文件处理优化

- ⭐ **提前检测空文件**：在读取文件后立即检测（第 239 行），避免后续不必要的处理
- ⭐ **成功标记**：空文件返回`success=True`，避免用户混淆（之前返回`success=False`导致前端显示"失败"）
- ⭐ **重复处理防护**：检查`[空文件标识]`，避免重复处理空文件
- ⭐ **状态管理优化**：区分空文件和重复数据，提供更准确的状态信息
- ⭐ **性能提升**：减少不必要的计算和数据库操作（规范化、数据清洗等）

### 🎯 成功标准

1. ✅ 货币代码变体不再触发表头变化检测（如果只有货币差异）
2. ✅ 货币代码正确提取并存储到`currency_code`字段
3. ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
4. ✅ 库存数据更新而非重复插入（同一商品+仓库只有一条记录）
5. ✅ 其他数据域保持现有行为（orders/products 使用 INSERT 策略）
6. ✅ 向后兼容现有模板和数据
7. ✅ 性能不受影响（写入性能影响<0.5%，查询性能提升 10-100 倍）

---

## [v4.14.2] - 2025-11-27 - 重构 DSS 架构下的必填字段验证设计 ⭐

### 🔄 架构重构

#### 核心变更

- ⭐ **移除所有必填字段验证**：不再要求 product_id、platform_sku 等标准字段名
- ⭐ **只验证数据格式**：日期、数字等格式验证（如果字段存在且不为空）
- ⭐ **支持中英文字段名**：验证器同时支持中英文字段名（如"产品 ID"、"商品编号"等）
- ⭐ **允许空值**：PostgreSQL 支持 NULL 值，允许字段为空

#### 设计原则

1. 表头字段完全参考源文件的实际表头行
2. PostgreSQL 只做数据存储（JSONB 格式，保留原始中文表头）
3. 目标：把正确不重复的数据入库到 PostgreSQL 即可
4. 去重通过 data_hash 实现，不依赖业务字段名

#### 修改的文件

- `backend/services/enhanced_data_validator.py` - 重构`validate_inventory`函数
- `backend/services/data_validator.py` - 重构所有验证函数（orders、products、traffic、services、analytics）

#### 影响

- ✅ 数据不再因为缺少标准字段名而被隔离
- ✅ 支持任意格式的表头字段名（中文、英文、混合）
- ✅ 数据入库更加灵活，符合 DSS 架构设计原则
- ✅ 去重机制通过 data_hash 实现，不依赖业务字段名

### 📝 相关文件

- `backend/services/enhanced_data_validator.py` - 库存数据验证器（已重构）
- `backend/services/data_validator.py` - 其他数据域验证器（已重构）

---

## [v4.14.1] - 2025-11-27 - 删除字段映射审核模块，完全迁移到数据同步 ⭐

### 🗑️ 清理工作

#### 1. 删除字段映射审核模块

- ✅ **删除菜单项**: `frontend/src/config/menuGroups.js` - 移除 `/field-mapping` 菜单项
- ✅ **删除路由**: `frontend/src/router/index.js` - 移除 `/field-mapping` 路由定义
- ✅ **归档组件**: `FieldMappingEnhanced.vue` → `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue`
- ✅ **清理引用**:
  - `frontend/src/App.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/Header.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleHeader.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleSidebar.vue` - 删除字段映射审核菜单项
- ✅ **修复跳转**: `frontend/src/views/DataBrowser.vue` - 将"跳转到字段映射审核"改为"跳转到数据同步-模板管理"
- ✅ **清理权限**: `frontend/src/stores/user.js` - 移除 `field-mapping` 权限
- ✅ **更新注释**: `frontend/src/api/index.js` - 更新废弃 API 注释

#### 2. 迁移说明

- ✅ **替代方案**: 所有字段映射审核功能已完全迁移到"数据同步-模板管理"模块
- ✅ **数据浏览器**: 字段映射跳转现在指向 `/data-sync/templates`
- ✅ **保留功能**: 字段映射辞典 API 和模板管理 API 仍然保留，供数据同步功能使用

### 📝 相关文件

- `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue` - 归档的字段映射审核组件
- `frontend/src/config/menuGroups.js` - 已删除字段映射审核菜单项
- `frontend/src/router/index.js` - 已删除字段映射审核路由
- `frontend/src/views/DataBrowser.vue` - 已更新跳转逻辑

---

## [v4.14.0] - 2025-02-01 - 清理 Superset 相关文件，迁移到 Metabase ⭐

### 🗑️ 清理工作

#### 1. 归档 Superset 相关文件

- ✅ **归档**: 35 个 Superset 相关文件已移动到`backups/20250201_superset_cleanup/`
  - Docker 配置: `docker-compose.superset.yml`, `superset_config.py`
  - 文档: 14 个 Superset 相关文档
  - 脚本: 13 个 Superset 相关脚本
  - SQL 文件: `create_superset_views.sql`, `refresh_superset_materialized_views.sql`
  - 代码文件: `backend/routers/superset_proxy.py`, `frontend/src/components/SupersetChart.vue`
- ✅ **更新**: `backend/main.py`移除 superset_proxy 路由引用
- ✅ **原因**: 项目从 Superset 迁移到 Metabase 作为唯一 BI 工具

#### 2. 移除 Streamlit 依赖

- ✅ **更新**: `requirements.txt`移除 Streamlit 相关依赖
  - 移除: `streamlit>=1.28.0`
  - 移除: `streamlit-aggrid>=0.3.0`
  - 移除: `streamlit-antd-components>=0.3.0`
  - 移除: `streamlit-option-menu>=0.3.6`
- ✅ **原因**: 项目已完全迁移到 Vue.js 3 前端，不再使用 Streamlit

### 📝 相关文件

- `backups/20250201_superset_cleanup/README.md` - 归档说明
- `requirements.txt` - 已移除 Streamlit 依赖
- `backend/main.py` - 已移除 superset_proxy 引用

---

## [v4.13.3] - 2025-11-22 - 修复数据流转显示问题：source_catalog_id 未设置 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **数据修复**: 使用`scripts/fix_source_catalog_id_final.py`修复了 1092 条已存在数据的`source_catalog_id`字段
- ✅ **验证**: 数据流转 API 现在正确显示 Fact 层数据数量（1092 条）

### 📝 相关文件

- `backend/services/data_ingestion_service.py`：修复数据入库时的 source_catalog_id 设置
- `backend/services/data_importer.py`：修复 upsert_product_metrics 函数的 fallback 逻辑
- `scripts/fix_source_catalog_id_final.py`：数据修复脚本（修复已存在数据）

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **影响**: 数据流转查询现在可以正确显示 Fact 层数据数量

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复 FactProductMetric.file_id 字段错误

- ✅ **问题**: 任务日志查询 API 返回 500 错误，提示`fact_product_metrics`表不存在`file_id`字段
- ✅ **原因**: `FactProductMetric`表使用`source_catalog_id`字段关联文件，而非`file_id`
- ✅ **修复**:
  - `backend/routers/auto_ingest.py`第 527 行：修复`get_task_logs`函数
  - `backend/routers/auto_ingest.py`第 627 行：修复`get_file_logs`函数
- ✅ **影响**: 任务日志查询和文件日志查询功能恢复正常

### 📝 相关文件

- `backend/routers/auto_ingest.py`：修复数据库查询字段
- `openspec/changes/improve-data-sync-reliability/BUGFIX_FactProductMetric_file_id.md`：Bug 修复文档

---

## [v4.13.1] - 2025-01-31 - 完成可选功能：数据流转可视化和丢失数据导出 ⭐

### ✅ 新增功能

#### 1. 数据流转可视化（100%完成）

- ✅ **ECharts 饼图可视化**: 在 FieldMappingEnhanced.vue 中添加数据流转可视化图表
  - 显示 Fact 层、丢失数据、隔离区的数据分布
  - 自动更新图表数据
  - 响应式布局支持
  - 窗口大小变化时自动调整

#### 2. 丢失数据导出功能（100%完成）

- ✅ **后端 API**: 添加`/api/raw-layer/export-lost-data/{file_id}`端点
  - 支持 orders/products/traffic/analytics/inventory 域
  - 导出为 Excel 格式（使用 pandas 和 openpyxl）
  - 包含丢失数据的详细信息
- ✅ **前端导出按钮**: 在对比报告中添加导出按钮
  - 当有丢失数据时显示导出按钮
  - 支持一键导出丢失数据到 Excel

### 📝 相关文件

- `backend/routers/raw_layer_export.py`：丢失数据导出 API 端点
- `frontend/src/views/FieldMappingEnhanced.vue`：数据流转可视化图表和导出按钮
- `frontend/src/api/index.js`：导出丢失数据 API 方法

---

## [v4.13.0] - 2025-01-31 - 提升数据同步可靠性 ⭐
