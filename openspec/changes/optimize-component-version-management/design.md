# Design: 采集组件版本管理模块重构

## Context

- 录制器已产出符合规范的 Python 组件，组件版本管理页是「测试 → 选版 → 生产」的关键环节。
- 当前测试路径使用 `adapter.login()` 等按模块名加载，与 `version.file_path` 脱节，导致「测 A 执行 B」。
- 删除规则过严、验证码静默穿透、缺少「实际执行文件」展示，易造成混淆与误操作。
- 需按业界主流实践重新设计，而非延续旧设计修补。

## 业界主流实践参考

| 来源 | 核心能力 | 借鉴点 |
|------|----------|--------|
| Polyaxon Component Hub | 多版本、stage、运行引用 | 组件 = 可执行实体，版本 = tag，运行指定 `org/component:v1.1` |
| Mendix Marketplace | Releases  tab、Download、Manage Versions | 版本列表、操作入口、详情分 Tab |
| n8n Node Versioning | 新流程用最新、老流程锁版本 | 版本与执行明确绑定 |
| ScriptRunner Registry | 集中注册、按功能分组、可搜 | 按能力组织、快速定位 |
| Apicurio Registry | Dashboard 概览、版本 diff | 统计卡片、版本对比 |
| OpCon / MicroFocus | 启用/禁用、部署、回滚 | 删除规则、部署语义 |

共识：**版本与执行明确绑定**、**实际执行文件可见**、**删除/启用规则清晰**、**执行结果可追溯**。

## 组件唯一性与更新工作流（方案 A + C）

### 组件唯一性（方案 A）

- **逻辑组件**：按 `(platform, component_type)` 唯一，同一平台同一类型只允许一个逻辑组件槽位。
- **component_name 标准化**：
  - login / navigation / shop_switch / date_picker：`{platform}/{component_type}`，如 `miaoshou/login`
  - export：`{platform}/{domain}_export` 或 `{platform}/{domain}_{sub}_export`，如 `miaoshou/orders_export`
- **多版本**：同一 component_name 可有多个 version（v1.0.0、v1.1.0）；生产仅使用 is_stable 版本。
- **约束**：禁止同一 (platform, component_type) 下存在多个 component_name（如 miaoshou/login 与 miaoshou/miaoshou_login 并存）；批量注册与录制保存均按标准化 component_name 操作。

### 录制保存行为（方案 C）

- 录制保存时**更新已有组件**，不新建 component_name。
- 保存 = 为该组件创建**新版本**（如 v1.1.0），写入对应 file_path，新版本默认**非稳定**。
- 用户选择「更新哪个组件」：由 platform + component_type（录制时已知）推导 component_name，或前端显式选择目标组件。
- 若该 component_name 尚不存在（首次录制），则创建首版本（v1.0.0），可标记为稳定或草稿。

### 版本工作流

1. **保存** → 新版本（草稿）
2. **测试** → 在版本管理中选中该版本，执行 `version.file_path` 对应实现
3. **提升稳定** → 测试通过后，将该版本设为 is_stable，取消同组件其他稳定版
4. **生产** → 执行器通过 ComponentVersionService 选 stable 版本，按 file_path 加载

### 文件存储策略

- **优先**：版本化文件名，如 `login_v1.0.0.py`、`login_v1.1.0.py`，每版本独立文件，便于回滚与并行测试。
- **备选**：主文件 + 草稿，如 `login.py`（稳定版）+ `login_draft.py`（草稿）；提升稳定时草稿覆盖主文件，简单但回滚依赖 Git。
- 新版本保存时写入版本化路径，ComponentVersion.file_path 指向对应文件。

## Goals / Non-Goals

- **Goals**：组件唯一性按 (platform, component_type)；录制保存更新已有组件并创建新版本；测试执行与选中版本一致；已禁用版本可删除；验证码步骤到达即暂停；列表与测试弹窗展示实际执行文件；同平台同类型多稳定版冲突提示；可选按平台分组浏览。
- **Non-Goals**：不改变生产执行器选版逻辑（仍按 ComponentVersionService）；不实现验证码自动打码；不在此变更中实现完整「按平台」树形浏览（可列为后续迭代）。

## 目标功能集

### 必须

- 组件/版本浏览（平台、类型、状态筛选）
- 测试时执行 `version.file_path` 对应实现
- 验证码回传（图形验证码截图 + 输入、OTP 输入）
- 删除规则：`!is_testing && !is_active` 可删
- 列表与测试弹窗展示「实际执行文件」

### 强烈建议

- 同平台同类型多稳定版冲突提示
- 组件类型标签（login/navigation/export 等）

### 后续迭代

- Tab「概览」Dashboard
- Tab「按平台」树形浏览
- 版本详情侧栏、最近 N 次测试历史

## 前端页面结构

### 布局

```
+------------------------------------------------------------------+
|  采集组件库                                                        |
+------------------------------------------------------------------+
|  [概览] [按平台] [全部版本]  |  筛选: 平台 | 类型 | 状态 | [批量注册] |
+------------------------------------------------------------------+
|                        主内容区                                    |
+------------------------------------------------------------------+
```

- **Tab 概览**（可选）：统计卡片、最近活动、冲突告警、快速入口
- **Tab 按平台**（可选）：树形 platform → component_type → 组件，展示「当前生产」版本
- **Tab 全部版本**（必须）：表格，列含「实际执行文件」、状态、成功率、操作

### 测试弹窗

- 顶部显式展示：**组件名、版本号、实际执行文件路径**
- 验证码：图形验证码展示截图 + 输入框；OTP 仅输入框
- 进度：步骤级日志、成功/失败结果

## Decisions

### 1. 测试时执行哪个组件类

- **决策**：测试路径必须使用从 `version.file_path` 加载到的组件类执行，而非适配器按 component_type 再按模块名加载。所有 component_type（login、navigation、export、date_picker）均须支持注入。
- **验证码恢复路径**：`_run_login_with_verification_support` 二次调用 `adapter.login(page)` 时，必须使用同一注入类。
- **实现**：采用适配器注入方案 `create_adapter(..., override_login_class=component_class)`；若未暴露注入点则改造 `_run_login_with_verification_support` 接收 `run_fn`。

### 2. 删除条件

- **决策**：可删除 = `!is_testing && !is_active`。批量注册的稳定版禁用后也可删除。启用中的版本不可删除。

### 3. 验证码步骤生成语义

- **决策**：图形验证码步骤生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，不生成 `count()>0` / `is_visible()` 及 `except Exception: pass`。
- **注意**：若某平台存在「有时无验证码」登录页，可后续通过可选验证码步骤单独支持；本变更统一为必选暂停。

## Risks / Trade-offs

- **适配器注入**：增加可选参数后，生产路径不传入 override，默认行为不变。
- **删除稳定版**：放宽后用户可能误删唯一稳定版；通过「可删 = 已禁用」降低风险（禁用即「不用」，删除前需先禁用）。

## Migration Plan

- **验证码**：已存在的 `miaoshou_login.py` 等组件需按 2.2 手动改验证码块或通过重新保存刷新。
- **组件唯一性**：若存在 `miaoshou/miaoshou_login` 与 `miaoshou/login` 并存等重复 component_name，需迁移脚本将其合并：将 miaoshou_login 的记录迁移为 miaoshou/login 的新版本（或由用户决定保留哪个实现），并统一 component_name 为 `miaoshou/login`。
- **文件路径**：采用版本化文件名后，存量 `login.py` 可对应为 `login_v1.0.0.py` 或保持 `login.py` 作为首版路径，新版本使用版本化路径；迁移脚本需更新 ComponentVersion.file_path。

## Open Questions

- 生产执行器与版本管理脱节：executor_v2 若未按 file_path 加载，版本管理的「稳定版」「使用统计」可能与生产实际不一致；生产打通需单独提案。
