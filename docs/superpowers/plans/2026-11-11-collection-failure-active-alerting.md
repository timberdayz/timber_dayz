# 批次 3.4 —— 采集失败主动告警（任务单 P2-5）

- 所属方案：`docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md`（批次 3.4）
- 分支：`feature/2026-11-11-shop-identity-failure-alerting`（base = `main`）
- 状态：**已实现**（代码 + 守护测试已落地；待开 PR）

---

## 1. 要解决的问题

采集失败到今天为止**没有任何主动通知**：任务落库成 `failed`，然后就躺在
`core.collection_tasks` 里等人翻。问题单 P2-5 要求「采集失败要能主动喊人」。

本批次把**采集执行器的失败终态路径**接上仓库**现成的**通知通道，并把同一轮里
「7 个店挂在同一个错误上」这种噪声收敛成**一条**通知。

---

## 2. 失败终态怎么判（口径不动）

判据在 `modules/apps/collection_center/executor_v2.py`
::`CollectionExecutorV2._resolve_final_collection_status`：

| 条件 | 终态 | 是否告警 |
|---|---|---|
| `completed_count == 0 and failed_count > 0` | `failed` | ✅ 告警 |
| `failed_count > 0` 且有域成功 | `partial_success` | ❌ 不告警（另记一档） |
| 其余 | `completed` | ❌ |

另有 3 条**直接置 `failed`** 的路径（执行器顶层异常 / 恢复时找不到 context /
并行执行没有数据域），它们最终都落进同一个 `CollectionResult.status == failed`
⇒ **告警入口只需要看「任务终态是不是 failed」这一件事**，不必去数「几条置 failed 路径」。

**取舍**：告警判据挂在**任务终态**上（`collection_task_status.STATUS.FAILED`），
不挂在执行器内部 ⇒ 将来新增任何一条失败路径，**不用**再改告警代码。

---

## 3. 通知通道：只用现成的两条

| 通道 | 入口 | 说明 |
|---|---|---|
| 站内信 | `backend/domains/platform/routers/notifications.py::create_notifications_for_admins` | 通知类型 `NotificationType.SYSTEM_ALERT`（枚举早就预留好，此前零调用）；只 `flush()` 不 `commit()`，提交由调用方负责 |
| webhook / 钉钉 | `backend/services/alert_service.py::send_resource_alert` | 自带**进程内**冷却（`RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES`，默认 5 分钟） |

**明确不用的两条**（与批次 3.3 同一判断，写在代码注释里）：

- ⚠️ **`core.alert_rules`（`AlertRule`）**：只有 CRUD、**没有求值器**（前端也写「开发中」）
  ⇒ 当不了现成通道。**别让它继续冒充 SSOT** —— 真要启用它得先补求值器，那是另一件事。
- **飞书投影**（`backend/services/feishu_projection_service.py`）：是
  「业务记录 → 飞书多维表格」的**业务投影**（entity_type + 表 id + 字段映射），
  不是消息通道；接它就得新增表与字段映射 = 另造一套通知体系。

### 3.1 `send_resource_alert` 的返回值（唯一一处既有文件的行为变更）

原先 `send_resource_alert` 返回 `None`，调用方无从判断「到底送没送到」——
没配 webhook 时它静默返回，调用方却会以为「发过了」⇒ 去重状态会把**没送达**的
问题记成「已通知」，下一轮就不再提醒 ⇒ 告警被静默吞掉。

因此把它改成返回 `bool`（是否真的送达外部通道）：

- 改动是**加法**（原先返回 `None`，现在返回 `False`/`True`），既有调用方
  （`backend/services/resource_monitor.py`）忽略返回值 ⇒ **行为不变**；
- 站内信侧同理：`create_notifications_for_admins` 返回空列表（没有管理员账号）
  ⇒ 判定为「站内信未送达」。

---

## 4. 同轮聚类：7 个店同一错误 ⇒ 1 条

「一轮」= 一次采集轮次（`CollectionConfigRun`）。一轮里每个账号一个
`CollectionTask`，7 个店就是 7 个任务、7 条失败记录。

聚类键 = **归一化错误指纹**：先脱敏，再把「每次都不一样」的部分归一掉
（URL / UUID / 时间戳 / 文件路径 / 长十六进制 id / 数字），剩下的小写文本就是指纹。

⇒ 7 个店都挂在 `TimeoutError: date option was not clicked` ⇒ **1 个指纹 ⇒ 1 条通知**，
通知正文里写「7 个店铺受影响」并列出**脱敏后**的店铺标识。

⚠️ 聚类必须在**轮次层**做：执行器只看得到单个任务，跨账号聚合只有轮次收尾时才有。
所以轮次级告警挂在 `CollectionQueueRunner._finalize_run`（轮次收尾点），
而不是 `CollectionConfigRunService.finalize_run_from_tasks` —— 后者是**服务层 API**，
且该文件在 main 上本就有 black 格式漂移（改动它会带来上百行无关排版噪声）。

---

## 5. 跨轮去重：同一问题连续多轮只通知一次

仓库现成的去重/冷却机制只有 `alert_service._cooldown`（**进程内**、按 `alert_type`、
默认 5 分钟）⇒ 只能挡「5 分钟内的重复」，**挡不住「连续多轮」**（可能跨天、跨进程重启）。
所以跨轮去重状态落在**既有的运行日志** `ops.pipeline_run_log`（**不加表不加迁移**），
放在 `context.notified_collection_failures`。

状态语义（**累计集合**，不是「上一轮通知过什么」）：

```
下一轮状态 = (上一轮状态 ∩ 本轮仍在失败的指纹) ∪ 本轮成功送达的指纹
```

⇒ 三种情形：

| 情形 | 结果 |
|---|---|
| 上一轮通知过、本轮仍失败 | 本轮**不再通知**（指纹留在集合里） |
| 本轮不再失败（恢复） | 指纹**移出集合** ⇒ 之后再次失败会**重新通知** |
| 两条通道都失败 | **不记入**集合 ⇒ 下一轮重试 |

「本轮没有任何失败且没有历史状态」时不写运行日志（避免噪声）。

⚠️ 已知边界：状态是**全局**的（不分平台/账号），所以两个**不同**店铺的**完全相同**错误
文本会被当成同一个问题去重。这是有意的取舍：指纹里的账号标识不参与聚类，
聚类键越稳定，通知越少。

---

## 6. 「等待验证码回填」单独归类（取舍：单独一档**记录**，不单独发通知）

分类由 `classify_failure_category()` 判定，命中以下标记即归入
`category=verification_wait`：

```
验证码等待超时 / 等待验证码 / 需要验证码 / 等待人工处理超时 / 等待人工处理
verification required / verification_required
```

**为什么它不会与步骤失败混聚**：它在 `failed_domains` 里是**独立条目**，
归类后走**独立分支**，既不进步骤失败的聚类，也不进步骤失败的指纹集合。

**为什么它不单独发通知**（取舍）：

1. 验证码回填超时的**任务终态本来就是 `paused` / `manual_intervention_required`**，
   **不是 `failed`** ⇒ 它压根不进失败告警的入口（只有 `failed` 任务会被读）；
2. 验证码回填本身有专门的运维入口（任务停在待回填状态，人工回填后继续），
   再叠一条失败告警只会造成噪音；
3. 真正需要喊人的场景（「回填超时导致整轮采集没跑成」）在同一轮里**同时**还有
   步骤失败，那一步会照常告警。

⇒ **单独一档记录**：运行日志 `context.verification_waits` 里留一档（任务/平台/
脱敏店铺/数据域），台账里看得见，但不进通知。

⚠️ 唯一的交叉情形：任务被**恢复**（`resume_task` 复用同一个 `TaskContext`）后再次失败，
`failed_domains` 里会残留上一次的「验证码等待超时」条目 —— 归类保证它仍然不与
步骤失败混聚。

---

## 7. `partial_success` 不当失败告警（取舍：单独一档**记录**，不发通知）

`partial_success` = 「采到了一部分」，**不是失败终态**。

- **不发失败告警**：半夜被半成功刷屏的代价高于漏报的价值；
- **单独一档记录**：运行日志 `context.partial_success_clusters` 留一档（聚类后的
  错误指纹 + 店铺数 + 数据域），台账里看得见。

若将来要把它升级成「单独一档通知」，去重机制已经就位（同一套指纹集合 + 冷却），
不需要另造。

---

## 8. 脱敏

通知正文里**只有**：平台、脱敏后的店铺标识、数据域、错误指纹、脱敏后的错误样例、
轮次键。

- **形态级脱敏复用批次 3.3 已落地的同一份实现**
  （`backend/services/data_pipeline/source_freshness_notify.py::mask_sensitive_text`），
  **不抄第二份**；守护测试断言两者是**同一个函数对象**（SSOT 守护）。
  - 连接串凭据 `://u:p@` → `://***:***@`；
  - `password/passwd/pwd/secret/token/api_key/access_key=值` → `=***`。
- **错误指纹 = 脱敏后再归一化** ⇒ 指纹本身（要落库）也不含凭据。
- **店铺标识中段遮蔽**：`shop-sg-1` → `sh***-1`。
  - 整段抹掉就没法定位问题；明文铺开又会把店铺名单泄进外部通道 ⇒ 只遮中段。
- **绝不进通知**：连接串、口令、token、完整原始数据行、原始任务 payload。

---

## 9. 通知失败绝不影响采集主流程

- 站内信是**数据库写入** ⇒ 失败后当前事务已处于失败状态，**必须 `await db.rollback()`**，
  否则后面写 `ops.pipeline_run_log` 会跟着炸（这一点与批次 3.3 同一教训）。
- 两条通道的异常**全部捕获**并降级为日志；调用点（路由 / 队列运行器）再兜一层
  `try/except`，**任何异常都不许冒泡**。
- 采集的**状态落库顺序不变**：任务状态先落库并提交，**之后**才告警 ⇒
  告警失败不会回滚采集结果。

---

## 10. 改动清单

| 文件 | 改动 |
|---|---|
| `backend/services/collection_failure_alert_service.py` | **新增**：指纹归一化、失败分类、同轮聚类、跨轮去重、脱敏、双通道派发 |
| `backend/services/collection_queue_runner.py` | 轮次收尾时接上告警（**同轮聚类**的入口） |
| `backend/domains/collection/routers/collection_tasks.py` | **不属于配置轮次**的快速采集任务失败时告警 |
| `backend/services/alert_service.py` | `send_resource_alert` 返回 `bool`（是否真的送达） |
| `backend/tests/collection/test_collection_failure_alerting.py` | **新增**：20 条守护测试 |

**不新增**表、**不新增**迁移、**不新增**第三方依赖、**不改** CI 配置。

---

## 11. 守护测试

`backend/tests/collection/test_collection_failure_alerting.py`（20 条）覆盖：

1. 失败终态判定口径不变（`failed` / `partial_success` / `completed` 三例）；
2. 同轮 7 个店同一错误 ⇒ **1 条**通知；
3. 同一轮两个不同错误 ⇒ 两条通知；
4. 跨轮去重：第二轮不再通知；
5. 恢复后再失败 ⇒ 重新通知；
6. `partial_success` 不告警但单独记一档；
7. 验证码等待单独归类、不与步骤失败混聚；
8. 脱敏：口令 / token / 连接串不进正文；店铺中段遮蔽；
9. 脱敏 SSOT：与批次 3.3 是**同一个函数对象**；
10. 指纹归一化：数字 / 时间戳变化不产生第二条指纹；
11. 通道全失败 ⇒ 不抛异常、状态照常落库、**不记入已通知** ⇒ 下轮重试；
12. 通道直接抛异常 ⇒ 告警不冒泡、且**回滚**了坏事务；
13. 快速采集（单任务）失败也会告警；
14. `alert_type` 按指纹隔离（冷却不误伤别的错误）；
15. 去重状态落在**既有的** `ops.pipeline_run_log`（不加表不加迁移）。

---

## 12. 遗留与风险

| 项 | 说明 |
|---|---|
| 跨轮状态是全局的 | 两个**不同**店铺的完全相同错误文本会被并成一个问题去重（有意取舍，见 §5） |
| 轮次级告警依赖队列运行器 | `CollectionConfigRun` 由 `CollectionQueueRunner` 收尾；轮次**没有正常收尾**（进程被杀、任务卡住）时不会告警 —— 那是批次 3.5「僵尸回收」的范围，本批次**不碰** |
| `mark_run_failed` 路径不告警 | 「一轮都没跑起来」（如没有可展开的任务）走的是 `mark_run_failed`，本批次不告警 |
| 两条通道都没配置时 | 站内信（无管理员）+ webhook/钉钉（未配置）⇒ 判定为「未送达」⇒ 不记入已通知 ⇒ 每轮都会重试并留日志（这是**正确**行为：没通道就不该假装已通知） |
| 进程内冷却只有 5 分钟 | `alert_service._cooldown` 重启即失效 ⇒ 跨轮去重必须靠 DB 状态（本批次已做） |

## 13. 记入 V2 的技术债

- `mask_sensitive_text` 住在 `backend/services/data_pipeline/` 下，采集域反向依赖它
  ⇒ 该工具函数应上移到**中立模块**（本次不顺手改，避免与批次 3.3 的已合入代码冲突）。
- `AlertRule` 求值器仍未补 —— 出口仍不是单一真相源（本批次只在代码注释里写明，
  不再让它冒充 SSOT）。
