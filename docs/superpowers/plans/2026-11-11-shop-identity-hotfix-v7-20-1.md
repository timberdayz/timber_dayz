# 店铺身份「保未来」热修 v7.20.1 —— 矛盾行能定位到行 + 守卫契约与实现对齐

- 日期：2026-11-11
- 基线：`main` = v7.20.0（PR #17，merge commit `ed228059`）
- 主题：**一** 个 —— 让「矛盾行台账 + 手工重发入口」这条链路**真的可用**，并把守卫的契约与实现对齐。

---

## 一、为什么有这次热修

v7.20.0 上线后做了两件事：

1. **独立复核**（只读）：对批次 3.7「同步侧双基准守卫」按 10 个核实点逐条查证。
   结论：**无阻断项** —— 判定口径正确、SSOT 未分叉、历史数据边界与检查点推进语义未被破坏。
   但报出 **2 处「应修」+ 4 处「建议」**。
2. **自己上手验**：把「手工重发入口」这条链路从源行一路追到脚本，发现**两处功能缺口**，
   其中一处与复核的「建议-1」**独立指向同一根因**。

两处缺口合起来 ⇒ **批次 4.3 承诺的「被跳过的行不再消失、能手工重发」，在 v7.20.0 上其实兑现不了**：
台账能记下行，但**定位不到那一行**，于是补发脚本一行也发不出去。

---

## 二、根因（一句话）

**源行主键在「源行 → 同步负载 → 身份闸门 → 矛盾行台账 → 重发脚本」这条链上被丢掉了两次。**

| 丢在哪 | 表现 | 后果 |
|---|---|---|
| `build_sync_payload` 只保留 canonical 列（canonical 列里**没有** `id`） | 生产路径上写入器拿到的是**没有主键的负载行** | 身份闸门与台账的 `row.get("id")` 恒为 `None` ⇒ 台账「源行主键」恒为空 ⇒ 补发定位不到行 |
| 重发脚本读源行时**只 SELECT canonical 列** | 真库**只返回被 SELECT 的列** ⇒ `id` 不在其中 | `mapping.get("id")` 恒为 `None` ⇒ 映射键全变成 `"None"` ⇒ 每行都被判成「源行已不存在」 |

⚠️ 顺带一个容易误判的点：**`source_row_id` 空并不影响台账的去重** ——
去重键里的「行内定位」在缺主键时退化成只剩 `data_hash`，而 `data_hash` 本身就在写入云的
冲突键里 ⇒ 内容相同的行本来就是同一行 ⇒ 去重**仍然正确**。
真正坏掉的是「**按行补发**」这一环。

---

## 三、改了什么（4 处代码 + 8 处用例）

### 代码

1. `backend/services/cloud_b_class_sync_service.py::build_sync_payload`
   —— **保留源行主键**（`id` 不是 canonical 列 ⇒ 写云端时 SQL 仍只绑 canonical 列，
   多出来的键被 SQLAlchemy 忽略 ⇒ 与「直接拿源行写库」那条路径行为一致）。
2. `scripts/replay_shop_identity_conflict_rows.py::_load_source_rows`
   —— 读源行时**把主键一起 SELECT 出来**（映射键靠它）。
3. `backend/services/cloud_sync_identity_guard_service.py::load_cloud_identity_registry`
   —— **拆行 + 建索引纳入 try**：失败即降级为「双基准不可用」，
   **绝不**因为云端这一侧的问题把整批同步打挂。
4. `backend/services/cloud_sync_identity_guard_service.py::_redact`
   —— 口令含**未编码 `@`** 时按最后一个 `@` 切 netloc 取完整口令，且**长的先抹**。
5. `backend/services/cloud_b_class_auto_sync_worker.py`
   —— `partial_success` 兜底文案补「或被双基准降级」。

### 用例（新增 7 条 + 改写 1 条）

| 用例 | 盯住什么 |
|---|---|
| `test_the_sync_payload_keeps_the_source_row_primary_key` | 负载必须带源行主键 |
| `test_the_production_path_records_the_source_row_id` | **生产路径**（源行 → 负载 → 闸门）必须记下源行主键 |
| `test_the_replay_loader_selects_the_primary_key` | 读源行必须 SELECT 主键（用**忠实形状**的替身：只按 SQL 里实际 SELECT 的列造行） |
| `test_the_replay_payload_keeps_the_same_dedup_key_as_the_original` | 重发算出的去重键必须与原始那一行**一致**（否则台账会多出一行） |
| `test_the_cloud_registry_index_build_failure_does_not_escape` | 云端建索引炸了**不得**把同步打挂 |
| `test_redaction_handles_a_password_with_a_bare_at_sign` | 带裸 `@` 的口令必须**整个**抹掉 |
| `test_a_raising_event_recorder_does_not_block_the_sync` | 事件记录器**整个**抛异常也不阻塞同步（第二层兜底） |
| `test_event_recording_failure_does_not_block_the_sync`（**改写**） | 原来是**空转**的：行内身份用「账号编码」（两端本来就一样）⇒ 压根不进 `record_mismatch`。改成用**平台编号**制造真不一致 + 断言事件记录器**确实被调用过** |

### 负向验证（6 项，全部通过）

把每个修复**逐个回退**，确认对应用例**立刻变红**：

| 回退 | 对应用例变红 |
|---|---|
| `build_sync_payload` 丢掉主键 | ✔ |
| 重发脚本不 SELECT 主键 | ✔ |
| 云端建索引异常不再被吞 | ✔ |
| 脱敏不处理裸 `@` | ✔ |
| 记录器整层兜底被拆掉 | ✔ |
| 记录器内部 + 外层兜底**都**被拆掉 | ✔ |

⇒ 「回退后仍然绿」= 这条用例没盯住那个缺陷。**这是本仓库的第 3 条同型教训**
（批次 3.5 的 fake 不忠实、批次 4.3 的假引擎不校验绑定参数、本次的假引擎不校验 SELECT 列）。

---

## 四、边界（不变）

- **历史数据一行未改**：不回填、不改历史行归属、不重推 11 月。
- **零迁移、零数据改动**：只改代码与用例。
- **检查点推进算法不变**：仍是「推进到最后一个落库行」，**不改成**「停在第一个矛盾行」。
- **不新增第二套去重口径**：仍用台账服务的 `build_dedup_key`。
- **不改语义层计数口径**：`count(DISTINCT c.resolved_shop_id)` 不动。

---

## 五、遗留（与 v7.20.0 相同）

- 律 3（候选名单副本物化视图）在**存量库**里仍是旧定义 ⇒ 需 DROP+CREATE 且下游被跟踪
  ⇒ 需专门维护窗口，本轮仍**不做**（已留档，见 `STATUS.md`「已知未落地项」）。
- 用户侧待办：配置 `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`；
  下一轮采集后核「新增月份认不出 = 0」。
