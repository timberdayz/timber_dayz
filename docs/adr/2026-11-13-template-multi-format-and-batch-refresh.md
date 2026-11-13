# ADR-2026-11-13：模板多格式并存(format_signature)与入库批量刷新

- 状态：**已接受**
- 日期：2026-11-13
- 影响域：数据采集与治理(模板族 / 变体 / 入库刷新)
- 前置：[ADR-2026-11-13 模板漂移判定口径收敛为唯一入口(SSOT)](./2026-11-13-template-drift-classification-ssot.md)

## 背景

这一批解决的是两个**吞吐/可恢复性**问题，都来自 2026-11-07 的事故复盘
(`docs/reports/2026-11-07-shop-identity-and-template-sync-incident.md` 问题 2 / 问题 3 / 问题 5)。

### 问题 A：一个维度只能有一种格式

`core.field_mapping_templates` 的 published 唯一键只是「维度」
`(platform, data_domain, granularity, sub_domain, account)`，
应用层的 `save_template` 又把同维度**全部** published 一起归档。
⇒ 「一个维度一种格式」被硬编码进了数据模型。

但平台的导出格式是**按站点 / 按时间**变的：

| 维度 | 并存格式 | 后果 |
|---|---|---|
| `shopee/analytics/monthly` | PH 站 `01/10/2026`(斜杠) vs SG/MY 站 `01-10-2026`(连字符)，**表头完全一致** | dash 模板被归档后 SG/MY 文件解析失败 |
| `tiktok/analytics/monthly` | 旧格式 28 列 vs 新格式 29 列 | 发 v8 后 8 月旧文件变成漂移，8 月数据补不回来 |

### 问题 B：每入库一个文件刷一轮 25 个物化视图

一次刷新 25 个物化视图，单次实测 170 秒以上。
刷新队列以前只合并「pending」的任务 ⇒ 一条刷新**正在跑**的时候新到的文件
会另起一条新任务 ⇒ 一轮入库（几十个积压文件）刷出**好几轮**完整刷新。

## 决策

### 1. 格式签名 = 业务形态标识（同一份实现）

模板级新增列 `core.field_mapping_templates.format_signature`，
取值与变体级 `core.field_mapping_template_variants.variant_kind`
**完全一致**（列集合 + 解析方式 + 表头行 + 工作表名模式）。

实现只有一份：`backend/services/template_family_service.py::build_variant_kind`，
对外两个名字：
`compute_format_signature(...)`（模板级）与 `resolve_format_signature(template)`（取模板的值）。

**为什么复用而不是另立一套**：「格式」与「业务形态」在本题上是同一件事 ——
平台改一次导出格式 ⇒ 文件的业务形态变了 ⇒ 这是另一种格式。
两套定义迟早漂移，然后就会出现「模板说自己是格式 1、变体说自己是形态 2」。

迁移 `current_migrations/versions/20261229_template_format_signature.py`：
加列 → 回填(与 Python 逐字一致) → 旧索引退场 → 新索引
`(维度, format_signature) WHERE status='published'` 上场。

### 2. 归档范围按**保存意图**分

| 保存意图 | API 参数 | 归档范围 | 语义 |
|---|---|---|---|
| 更新既有模板 | `save_mode='new_version'` | 被编辑的那一版(+同签名) | **替换** |
| 新建模板 / 创建变体 | `save_mode='create'` | 只归档**同格式签名**的 | **并存** |

**为什么不一律按格式**：用户给模板**加一列**时，心智是「这一版被替换掉了」；
若一律按格式归档，这次保存就会变成「多出一种格式」，
「更新」这个动作在结果上与心智不符（接口返回 `operation` 也会从
`new_version` 变成 `created`）。

**为什么新建/创建变体要并存**：变体的定义就是「同一种业务的**另一种文件格式**」。
并存之后，同维度多份 published 模板会被家族投影成**多个变体**
（`_upsert_projection_group` 本来就按 published 模板逐个建变体），
变体选择本来就按「列集合是否被文件覆盖 + 样本行能否解析」挑
（`_select_variant` / `evaluate_variant_takeover`）⇒ 选模板的机制**不需要重写**。

### 3. 「当前已发布模板」必须限定在同格式内

多格式并存后，「维度里版本号最高的那个」可能是**另一种格式**。
拿它跟契约比，会把「另一种格式并存」误报成「我们升级过模板」，
治理面板上就会出现「文件按 v3 采集，当前已发布模板为 v12」这种看不懂的话。

⇒ 新增 `TemplateMatcher.find_published_template_by_format(...)`，
判定链路用它把「当前模板」收敛到**与基准同格式**的那一版。

两种情形必须分清：

| 基准那一版 | 同格式有已发布版本吗 | 「当前模板」取谁 | 「我们升级过模板」信号 |
|---|---|---|---|
| 仍然 published（两种格式并存） | 有（就是它自己） | 同格式那一版 | **不成立**（是并存，不是升级） |
| 已被归档（新版把它顶掉了） | 没有 | 退回「当前已发布模板」 | 照常成立 |

⇒ 找不到同格式的已发布模板时退回 **fallback(当前已发布模板)**，
而不是退回基准模板本身 —— 否则「升级」这个信号会被一起吃掉
（`test_template_upgrade_does_not_flag_file_collected_with_old_template` 守的就是这条）。

### 4. 刷新队列：运行中吸收 + 跑完收口

`RefreshQueueService`：

- `enqueue_refresh` 的合并范围从「pending」扩到「pending + running」——
  正在跑的那条会吸收后来到的事件，并打上 `rerun_requested` 标记；
- `mark_completed` 看到标记 ⇒ 不落 `completed`，而是**重新排回 pending** ⇒ 再刷一轮收口。

⇒ 一轮入库至多「跑中的那一轮 + 收口的那一轮」，而不是「每个文件一轮」。
没有标记时行为与从前**逐字一致**（直接 completed）。

## 后果

**正面**

- 同维度多格式可以并存；旧格式的历史文件仍由**它自己那一版模板**解释
  （基准选取走 `resolve_baseline_for_file` → 变体匹配，与入库同一条链路）；
- 「更新模板」的语义没变（接口返回仍是 `new_version`），
  唯一索引从「维度」变成「维度 + 格式签名」；
- 一轮入库的刷新轮次从「N 轮」降到「≤2 轮」。

**代价 / 风险**

- 模板表多一列 + 一次索引重建（迁移可回滚：downgrade 会把索引还原成「维度」并归档多出来的 published）；
- 同维度可能同时存在多份 published ⇒ 任何「取当前模板」的代码都必须问「哪个格式」；
  本次已把判定链路与契约对照口径收敛到同格式，**其它调用点**（如治理面板的维度行）
  仍按「最新一版」展示，属于展示口径，不影响判定；
- 刷新队列的「收口轮」会让一次入库多花**一轮**刷新时间（换来少刷 N-1 轮）。

**未做（留给 V2）**

- 多格式并存后，治理面板的「维度行」还没有按格式拆分展示；
- 物化视图仍是全量 `REFRESH MATERIALIZED VIEW`，没有改成增量刷新
  （问题 5 的另一半建议）。

## 守护测试

- `backend/tests/data_pipeline/test_template_format_signature_guardrails.py`
  （签名口径唯一 / 迁移回填与 Python 逐字一致 / 归档范围 / 保存意图 / 投影多变体 / 基准按格式）
- `backend/tests/data_pipeline/test_refresh_queue_batch_coalescing.py`
  （运行中吸收 / 收口轮 / 一波入库的刷新轮次）
