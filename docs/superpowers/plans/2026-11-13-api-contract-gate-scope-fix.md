# API 契约门禁：扫描范围空转 + 告警口径失真（**待批准开工**）

> 状态：**第一批方案已成型，等待批准开工**（2026-11-13 提交人：MCode）。
>
> 这份文件记录的是**实测数据**与**两批处置方案**，不含实现。
> §2 是「这条门禁到底在干什么」，§3 是「修好之后它会报什么」，
> §4/§5 是方案，§6 是验收口径。
>
> ⚠️ **尚未动手**：本文件落地时，`scripts/validate_api_contracts.py` 未被修改。

---

## 1. 一句话

发布流水线里的「Validate API Contracts (Release Gate)」**从未检查过任何一行真实路由代码**；
修好扫描范围**不会卡住任何一次发版**（实测 error = 0），但必须**同时**把告警口径改成仓库的真实口径，
否则只是把「狼来了」从 571 条换成另一个触发方式。

---

## 2. 现状：这条门禁一直在空转

### 2.1 路由代码有两层，旧目录只剩垫片

| 位置 | 文件数 | 是什么 |
|---|---|---|
| `backend/routers/*.py` | 77（76 个垫片 + `__init__.py`） | **兼容垫片**，1–3 行转发 |
| `backend/domains/*/routers/*.py` | **158** | **真正的路由实现** |

垫片长这样（`backend/routers/collection.py`）：

```python
from backend.domains.collection.routers.collection import *  # noqa: F403
```

### 2.2 脚本的扫描范围停在旧目录

`scripts/validate_api_contracts.py`：

- `scan_router_files()` → `project_root / "backend" / "routers"`（**只扫垫片**）
- `validate_all(target_files)` 的过滤条件 → `file_path_str.startswith("backend/routers/")`

于是两种模式都无效：

| 模式 | 谁在用 | 实际扫到 | 结果 |
|---|---|---|---|
| whole-repo（不传 `--files`） | 手工体检 | 77 个垫片 | 垫片里没有 API 代码 ⇒ **0 问题** |
| `--changed-files` | **deploy-production.yml 的发布门禁** | 只匹配 `backend/routers/` 前缀 | 改动的真实路由**一个都匹配不到** ⇒ 报「验证文件数: 0（本次发布没有改动 router 文件，跳过验证）」并**绿灯放行** |

**后果**：v7.23.0 改了 `backend/domains/business/routers/product_center.py`，
门禁报告「跳过验证」——它从未看过这个文件。

### 2.3 附带发现：告警扫描器本身也不可靠

`validate_error_handling()` 用**正则找 `try:` + 按缩进猜块尾**：

- 一个 `try:` 配多个 `except:` ⇒ 重复计数；
- `try:` 出现在字符串 / 注释里 ⇒ 误命中；
- 块尾靠 `content.find('\n    ')` 猜 ⇒ 缩进一变就切错。

⇒ 它报出的「518 条缺错误日志」这个数字**本身不可信**（§3 用 AST 重算）。

---

## 3. 实测：修好之后它会报什么

### 3.1 修好扫描范围后（158 个真实路由全扫）

| 项 | 数量 |
|---|---|
| **error** | **0** |
| warning | 571（518 缺日志 + 35 `raise HTTPException` 旧风格 + 18 缺 `recovery_suggestion`） |

`main()` 的退出码只看 `issues["errors"]` ⇒ **error = 0 ⇒ 退出码 0 ⇒ 不会卡任何一次发版**。
这是动手的安全垫。

### 3.2 告警质量：用 AST 把 748 个 except 块重新分桶

| 分类 | 数量 | 该不该拦 | 说明 |
|---|---|---|---|
| A 记了日志（`logger.error` / `logger.exception`） | 363 | ✅ | 合规 |
| D 显式 `raise`（含 `raise ... from exc`） | 172 | ❌ | **口径分歧**：错误带着 cause 走，不是缺陷 |
| B 只记了 `logger.warning` 等其它级别 | 95 | ❌ | 脚本只认 error/exception ⇒ 误报 |
| C 结构化 `error_response(...)` 返回 | 37 | ❌ | **这是正确写法** |
| E 有意降级（skip / continue / pass / 回退默认值） | 35 | ❌ | 设计如此 |
| **F 真静默**（不记、不抛、不结构化处理） | **47** | ✅ | **该拦** |

⇒ 现状噪音比 **518 : 47 ≈ 11 : 1**。

### 3.3 47 处真静默的分布

24 个文件，最大一处 `data_sync.py` 10 个：

| 文件 | 处数 | 文件 | 处数 |
|---|---|---|---|
| `data_sync.py` | 10 | `product_center.py` | 2 |
| `mv.py` | 3 | `raw_layer.py` | 2 |
| `notification_websocket.py` | 3 | `raw_layer_export.py` | 2 |
| `system_monitoring.py` | 3 | `collection_config.py` | 2 |
| `users_admin.py` | 3 | `field_mapping_files.py` | 2 |
| 其余 12 个文件 | 各 1 | `field_mapping_ingest.py` | 2 |

落在「守卫 / 校验」类函数里的**只有 1 处**：`collection_schedule.py:548`（`health_check()`）。

另有**语义上属于守卫**、但函数名没带关键词的 2 处：
`product_center.py` 的 `_count_sku_references`（`except: rollback; refs = 0`）
⇒ 统计引用数失败就报 0 条引用 ⇒ **删除守卫 fail-open**。
既有代码（`855f8a8a4` / 2026-09-16），不是 v7.23.0 引入的。

---

## 4. 第一批：修门禁（建议本周内，**不碰任何业务代码**）

| # | 改动 | 说明 |
|---|---|---|
| 1 | **扫描范围** | `scan_router_files()` 改为发现 `backend/**/routers/*.py`（真实实现 158 个）；`--changed-files` 的过滤不再用 `startswith("backend/routers/")`，改用同一个发现函数判定「是不是路由文件」 |
| 2 | **告警口径 + 改用 AST** | error（该拦）= 真静默（§3.2 的 F 桶）；warning（不拦）= D/B/C/E 四桶。异常块判定从「正则 + 缩进猜测」改成 AST |
| 3 | **报告不刷屏** | 按类型聚合计数；只对**本次改动的文件**逐条列。whole-repo 模式留作手工体检，**不进 CI** |
| 4 | **守护测试** | 断言 `backend/domains/*/routers/` 下的文件必须被识别为路由文件 ⇒ 防止范围再退回去（同 `test_architecture_ssot_gate_scope.py` 的写法） |

**范围与口径必须同批**：只做 1，每次发版日志会多几十条 warning，而真正该看的只有 1–2 条 ⇒ 门禁还是没人看。

**仍然只挂在 `deploy-production.yml`**（tag 触发）；先跑一个版本确认噪音可接受，再考虑加进 `ci.yml`。

**风险**：低。实测 error = 0 ⇒ 不卡发版；不改任何业务代码；退出码语义不变（只看 errors）。

---

## 5. 第二批：47 处真静默的分流与清理（**单独排**）

跨 data_platform / collection / business / platform **四个域**、24 个文件 ⇒ 按 pre-launch
「跨 3 个以上模块要拆分」必须单独一批，且**不能混进 launch 期**。

**优先做 2 处 fail-open**（其余 45 处多为「消息推送失败不该打断请求」这类合理韧性）：

| 位置 | 风险 |
|---|---|
| `backend/domains/business/routers/product_center.py` `_count_sku_references` | 引用计数失败 ⇒ 报 0 ⇒ **删除守卫放行**（既有代码，2026-09-16） |
| `backend/domains/collection/routers/collection_schedule.py:548` `health_check()` | 吞异常 ⇒ **健康检查会说谎** |

---

## 6. 验收口径

第一批完成后应同时成立：

| 项 | 期望 |
|---|---|
| `python scripts/validate_api_contracts.py --files backend/domains/business/routers/product_center.py` | 验证文件数 = 1（不再是 0），error = 0，退出码 0 |
| `--changed-files` 传入一个 domain 路由 | 验证文件数 ≥ 1（不再是「跳过验证」） |
| 全仓体检 | error = 0；warning 中「真静默」类 = 47（第一批不清理，只报数） |
| 守护测试 | 新增用例通过；且**故意把范围改回旧目录时该用例必须失败**（守卫生效验证） |
| 发版 | `deploy-production.yml` 的 Validate 步骤在真实改动上跑出非 0 文件数，且流水线仍绿 |

---

## 7. 引用

- `scripts/validate_api_contracts.py`（被改对象）
- `.github/workflows/deploy-production.yml` → `Validate API Contracts (Release Gate)`
- `docs/guides/PRE_LAUNCH_RULES.md` → 「跨 3 个以上模块要拆分」「不混架构清理与业务改动」
- `docs/guides/RELEASE_CHECKLIST.md` → 「After Deployment」验收清单
