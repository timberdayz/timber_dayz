# 账号设备身份 SSOT 收口 —— 执行卡（2026-11-13 / 2026-11-14）

> 配套方向文档：`2026-11-13-account-profile-device-identity-ssot-closure.md`
> 规范真源：`docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（R8 及其小节）
>
> **2026-11-14 修订**：原 10 张执行卡是「让所有账号像同一台电脑」方向，**已作废**。
> 下表是**实际执行的 9 张卡**（新1–新9），每张卡标注真实产出与实测证据。

---

## 执行卡总览

| 卡 | 内容 | 状态 | 主要产出 |
|---|---|---|---|
| 新1 | 账号设备画像模块 | ✅ | `modules/utils/sessions/account_device_profile.py`（462 行） |
| 新2 | machine_id 隔离 | ✅ | 同上模块内 `derive_machine_id` / `ensure_profile_machine_id` |
| 新3 | 采集侧注入（顺序路径） | ✅ | `runtime_session.py` |
| 新4 | 采集侧注入（并行扇出路径） | ✅ | `executor_v2.py` |
| 新5 | 巡店侧 CDP 注入 + machine_id 隔离 | ✅ | `modules/utils/pwcli_native.py` |
| 新6 | 主账号级代理位 + 巡店/采集同 IP | ✅（**留接口不强制**） | 3 个 loader + inventory SQL |
| 新7 | 规范修订 R8 + 上位文档对齐 | ✅ | 2 份 `docs/guides/` |
| 新8 | 新增账号前置检查脚本 | ✅ | `scripts/check_account_readiness.py`（353 行） |
| 新9 | 巡店面板就绪可见 | ✅ | `account_readiness.py`（131 行）+ 面板端点 + 前端 |

---

## 新1 — 账号设备画像模块

**产出**：`modules/utils/sessions/account_device_profile.py`（20,831 bytes / 462 行）

| 能力 | 函数 | 说明 |
|---|---|---|
| 参数化自洽生成 | `build_device_profile` | 浏览器 × 版本 × 视口 **+ 宿主 OS / 宿主地区**；**OS 与地区都锁宿主**（Playwright 路径改不了 `navigator.platform`，且地区必须与出口 IP 一致） |
| 确定性派生 | 同上 | 按 `account_id` 派生 ⇒ 账号内稳定、**不随代码版本变** |
| 读写 | `read_device_profile` / `write_device_profile` | 原子写（`.tmp` → `replace`）；落在 `profiles/<平台>/<账号>/.device_profile.json` |
| 占用校验 | `assign_device_profile` | 目标槽位被别的账号占用 ⇒ **顺延**到下一个可用槽位 |
| 注入项白名单 | `device_context_options` | 只放行 `user_agent` / `viewport` / `locale` / `timezone_id` / `extra_http_headers` |
| CDP 覆盖项 | `device_cdp_overrides` | 巡店是裸 Chromium ⇒ 走 `Emulation.*` |

安全边界：画像里**只有设备特征**，**没有任何凭据**（不写 cookie / token / 代理口令 / 账号密码）。

## 新2 — machine_id 隔离

`derive_machine_id(platform, account_id)`：uuid5 + 固定命名空间 ⇒ 确定性可复现。
`ensure_profile_machine_id(profile_dir, ...)`：幂等改写 `Local State` →
`user_experience_metrics.machine_id`，**失败不抛**（设备隔离是增强项，不该让「打开浏览器」失败）。

**实测**：临时目录 + bundled Chromium，headless 与 headed 均验证改写值被**持久接受、不重新生成**。

## 新3 — 采集侧注入（顺序路径）

`modules/apps/collection_center/runtime_session.py`：

- `build_runtime_context_options(..., use_device_fingerprint=False)` —— profile 模式**弃用旧人造指纹**。
- `open_persistent_runtime_bundle` 读画像注入（缺失 ⇒ 沿用 profile 原生环境，不注入任何覆盖项）。

## 新4 — 采集侧注入（并行扇出路径）

`modules/apps/collection_center/executor_v2.py`：并行扇出**不挂载 profile** ⇒ 必须显式注入画像。
画像缺失时 **WARN**：`PARALLEL_COLLECTION_NO_DEVICE_PROFILE` —— 不得静默。
代理显式带入该分支。

## 新5 — 巡店侧 CDP 注入 + machine_id 隔离

`modules/utils/pwcli_native.py`：

- `prepare_account_device_identity(profile_dir, ...)` —— **启动前**分配画像 + 隔离 machine_id。
- `apply_device_profile_to_context(context, page, payload)` —— CDP `Emulation.setUserAgentOverride` /
  `setLocaleOverride` / `setTimezoneOverride` / `setDeviceMetricsOverride`。
- `launch_browser` 在 Chromium 启动前准备身份、在 **`page.goto` 之前**注入
  （否则首个请求已经带旧 UA 发出去了）。

## 新6 — 主账号级代理位 + 巡店/采集同 IP

代理权威位上移到 `core.main_accounts.extra_config['proxy']`（店铺级仅回退）。
巡店与采集读**同一套优先级规则** ⇒ 登录 IP 与采集 IP 不会不一致。

改动文件：`backend/services/account_loader_service.py`、`backend/services/shop_account_loader_service.py`、
`scripts/pwcli_account_inventory.py`（`ACCOUNT_QUERY` 加 `m.extra_config as main_extra_config`）。

> ⚠️ **资源未到位**：库里代理配置 **0 条**（缺口 G1）。当前所有账号仍共用宿主出口 IP。
> 巡店侧另有硬保护：代理配置坏了**显式失败**，不静默直连。

## 新7 — 规范修订

- `docs/guides/COLLECTION_SESSION_LIFECYCLE.md`：R8 整节改写为「账号设备画像（账号间不可关联）」，
  含 R8.0–R8.4；术语表加「设备画像」「机器标识」；验收项 H 改写。
- `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`：《按账号固定设备画像》整节改写 +
  顶部冲突声明（以 R8 为准）。

## 新8 — 新增账号前置检查脚本

`scripts/check_account_readiness.py`（16,659 bytes / 353 行，**只读**：不写库、不写盘）。

7 项检查：① ID 规范 ② profile 目录不撞车 ③ 平台在巡店白名单 ④ 设备画像已分配
⑤ machine_id 已隔离 ⑥ 已人工首登 ⑦ 出口 IP 已配置（**提示项**）。

两种模式语义不同：

- `--candidate-id`（**新号前置**）：ID 不合规 / 目录已存在 / 平台不在白名单 ⇒ **FAIL**。
- `--account-id` / `--all`（**存量体检**）：ID 不合规 ⇒ **WARN**（历史事实，改名会换登录态）；
  只有**真实撞车**（另一个主账号净化后落到同一目录）与「平台不在白名单」⇒ **FAIL**。

**实测**（9 个主账号）：只有 1 个 FAIL —— `验证码测试账号`（platform 被填成中文，永不入白名单）。
其余 8 个：画像未分配 6 个、machine_id 未隔离 6 个（等下次巡店/采集自动改写）、出口未配 9 个。

## 新9 — 巡店面板就绪可见

**新增共享判据** `modules/utils/sessions/account_readiness.py`（131 行）——
`profile_contains_state` / `read_profile_machine_id` / `build_profile_state` / `build_account_readiness`。

**判据三处同源**（SSOT）：

| 消费方 | 入口 |
|---|---|
| 采集侧 | `runtime_session._profile_contains_state` → **委托**共享模块 |
| CLI 体检 | `scripts/check_account_readiness.py` → `build_profile_state` |
| 巡店面板 | `scripts/pwcli_inspection_panel.py` → `build_account_readiness` |

**后端**：新增只读端点 `GET /api/accounts/readiness`（带 token 校验）。
`/api/accounts` 的既有响应形状**不动**（有逐字段断言的既有契约）⇒ 就绪信息走独立端点。

**被白名单排除的账号不再静默消失**：`build_skipped_account_details` 返回
`platform` / `account_id` / `display_name` / `reason`，面板显式列出并写明原因。

**前端**（`scripts/pwcli_inspection_panel_static/index.html`）：
15 秒轮询刷新；卡片徽标显示「已首登 / 画像已分配 / machine_id 已隔离 / 出口已配」
+ 画像摘要；「上次刷新」时间戳；跳过账号区块。

---

## 验收证据

| 范围 | 命令 | 结果 |
|---|---|---|
| 设备隔离契约 | `python -m pytest tests/test_account_device_isolation_contract.py -q --no-header` | **25 passed** |
| 就绪契约 | `python -m pytest tests/test_account_readiness_contract.py -q --no-header` | **11 passed** |
| 代理来源契约 | `python -m pytest tests/test_account_proxy_source_contract.py -q --no-header` | **4 passed** |
| 采集相关回归 | `backend/tests/test_collection_runtime_session.py` + `test_collection_executor_session_alignment.py` + `test_collection_executor_reused_session_scope.py` + `test_account_proxy_config.py` + `test_collection_session_reuse_contract.py` | **174 passed** |
| 面板与运行时回归 | `tests/test_pwcli_inspection_panel.py` + `tests/test_pwcli_daily_inspection.py` + `backend/tests/test_pwcli_inspection_panel_reporting.py` + 上述契约文件 | **76 passed** |
| 后端全量 | `python -m pytest backend/tests -q --no-header` | **5974 passed / 8 skipped** |
| 根 tests 全量 | `python -m pytest tests -q --no-header` | **837 passed / 5 skipped** |
| 前端 | `frontend/scripts` 100 个 + `frontend/tests` 20 个 `.test.mjs` | 全绿 |

**CI 根契约清单**：`ci.yml` 的 "Run root contract tests (no DB)" 步骤新增三条

```
tests/test_account_device_isolation_contract.py \
tests/test_account_readiness_contract.py \
tests/test_account_proxy_source_contract.py \
```

⇒ 根契约清单条目 57 → **60**；`scripts/audit_guard_tests.py` 分类确认三条均为 **A 类（CI 硬门禁）**。

> ⚠️ **代理契约为什么是纯同步的独立文件**（2026-11-14 实测，CI run 43485663421）：
> `backend/tests/test_account_proxy_config.py` 含 9 个 **async** 用例。CI 钉
> `pytest==7.4.3` / `pytest-asyncio==0.21.1`，而 `backend/tests/conftest.py` 用
> `@pytest.fixture(scope="session")` 覆盖了 `event_loop`（pytest-asyncio 1.x 会忽略它）。
> 把它放进根契约清单 ⇒ 它排在 `backend/tests/test_celery_dispatch_event_loop_isolation.py`
> 之后 ⇒ 拿到**已关闭**的 session 事件循环 ⇒ 9 个用例报
> `RuntimeError: Event loop is closed`。
> ⇒ 断言移进纯同步的新文件；异步用例留在原文件，由**全量回归**覆盖（CI 的
> "Run pytest (if test files exist)" 步骤单独跑它是绿的）。
> **根因未修** ⇒ 已并入 `STATUS.md`「当前未结」#8 记账到 V2。

---

## 回滚记录（方向纠偏）

原方向（「所有账号像同一台电脑」）产出并**已回滚**的文件：

```
docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md
modules/utils/sessions/device_fingerprint.py
modules/utils/sessions/legacy_shop_artifact_cleanup.py
modules/apps/collection_center/runtime_session.py
modules/apps/collection_center/executor_v2.py
backend/tests/test_device_fingerprint_headers.py
```

方向错误时新建的 `modules/utils/sessions/device_profile_manifest.py` 已**可恢复删除**（mavis-trash）。

> 教训：业务目标没确认就动手，会一次性改 6 个文件 + 新建 1 个模块，返工成本远高于先问一句。
