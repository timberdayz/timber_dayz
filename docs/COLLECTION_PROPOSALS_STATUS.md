# 采集模块 OpenSpec 提案开发进度与执行顺序

本文档面向「主要针对采集相关提案工作」的 Agent，汇总当前采集相关提案的状态与建议执行顺序。依据 `.cursorrules`、`openspec/AGENTS.md` 及 `openspec/changes/` 下各提案的 `proposal.md`、`tasks.md` 整理。

---

## 一、当前采集相关提案一览

### 1. 已归档（已完成）的采集相关提案

| 归档目录 | 说明 |
|----------|------|
| `archive/2026-03-13-add-collection-recorder-python-output` | 录制工具产出 Python 组件（规范对齐） |
| `archive/2026-03-13-add-web-captcha-optimization` | 网页登录验证码统一优化（OTP/图形验证码、暂停回传、妙手改造） |
| `archive/2026-03-13-refactor-collection-unify-sequential-parallel` | 采集执行器修复与双轨统一（Phase 1 完成；Phase 2 已作废） |
| `archive/2026-03-13-add-hybrid-collection-api-playwright` | 混合采集（API + Playwright）按店铺分流；**搁置归档**（未实施，需启用时从 archive 恢复排期，见该目录下 proposal/tasks 与 ALIGNMENT_ASSESSMENT.md） |
| `archive/2026-03-03-migrate-collection-off-yaml` | 采集迁移出 YAML，仅用 Python 组件 |
| `archive/2026-02-27-add-collection-script-writing-guide` | 《采集脚本编写规范》文档 |
| `archive/2026-02-25-add-collection-session-fingerprint-alignment` | 采集会话与指纹对齐 |
| `archive/2026-02-25-fix-local-collection-headed-mode` | 本地采集有头模式修复 |
| `archive/2026-02-24-add-local-run-launcher` | 本地运行启动器 |
| `archive/2025-12-29-refactor-collection-async-components` | 采集异步组件重构 |
| `archive/2025-12-28-optimize-collection-component-workflow` | 采集组件工作流优化 |
| `archive/2025-12-28-verify-collection-and-sync-e2e` | 采集与同步 E2E 验证 |
| `archive/2025-12-19-refactor-collection-module` | 采集模块重构 |

规范与实现基础：**《采集脚本编写规范》** 位于 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`，编写/修改采集组件时必须遵循；数据采集能力规格在 `openspec/specs/data-collection/spec.md`。

---

### 2. 进行中（未归档）的采集相关提案

#### 2.1 ~~add-collection-recorder-python-output~~（已归档 2026-03-13）

- 已归档至 `openspec/changes/archive/2026-03-13-add-collection-recorder-python-output/`；主 spec `data-collection` 已合并 delta（录制工具产出符合规范的 Python 组件）。

---

#### 2.2 optimize-component-version-management（采集组件版本管理重构）

- **目标**：组件唯一性 (platform + component_type)、测试执行与选中版本一致（按 file_path 加载）、验证码必选暂停、删除规则放宽、生产按 file_path 加载、测试环境与生产对齐等。
- **进度**：
  - **已完成**：0.1～0.6（component_name 标准化、录制保存新版本、批量注册、迁移脚本、前端 export 传 data_domain/sub_domain）、1.1～1.4（适配器注入、测试传组件类、验证码恢复、生产按 file_path 加载）、2.x（验证码 unconditional 暂停）、3.x（删除规则）、4.x（体验）、5.x（前端单 Tab）、6.2～6.3（文档与部署检查）。
  - **未完成**：
    - 1.5 回归：多版本分别测试（含验证码回传）、生产稳定版按 file_path 执行。
    - 1.6 非登录组件测试前登录/复用会话（单组件测试模拟完整链路）。
    - 1.7 测试环境与生产对齐（SessionManager + DeviceFingerprintManager、account_id 必填、阶段可观测性）。
    - 1.8 发现模式组件（date_picker/filters）的 test_mode、test_config 策略。
    - 6.1 验收：版本管理测试、验证码回传、录制保存新版本、测试先登录/会话与生产一致等。
- **状态**：**核心功能已落地**，剩余为测试/回归、测试环境与生产对齐、发现模式组件策略及整体验收。

---

#### 2.3 ~~add-web-captcha-optimization~~（已归档 2026-03-13）

- 已归档至 `openspec/changes/archive/2026-03-13-add-web-captcha-optimization/`；主 spec `data-collection` 已合并 delta（登录验证码检测与处理）。人工验收 6.1/6.2 在测试环境下已通过，采集环境待后续验证，有问题再修复。

---

#### 2.4 ~~refactor-collection-unify-sequential-parallel~~（已归档 2026-03-13）

- 已归档至 `openspec/changes/archive/2026-03-13-refactor-collection-unify-sequential-parallel/`。Phase 1 已验收（认证 HTTPException、create_adapter/config、并行路径统一为 adapter、无 db_session_maker）；Phase 2 已作废（与组件版本管理设计冲突）。主 spec 已合并「顺序与并行使用同一套组件执行模型」。

---

#### 2.5 add-collection-step-observability（采集步骤可观测与组件契约统一）

- **目标**：步骤级日志与进度持久化、任务详情与步骤时间线、组件 run() 统一为 async。
- **进度**：
  - **已完成**：1.x（回调扩展、顺序/并行打点、CollectionTask started_at/completed_at）、2.x（任务详情与步骤时间线）、3.x（各平台 run 改为 async）、4.4（文档）。
  - **未完成**：4.1～4.3 人工验收（步骤时间线、故意失败、多平台无 await 报错）。
- **状态**：**实现已完成**，仅差人工验收即可归档。

---

#### 2.6 refresh-collection-module-frontend（数据采集模块前端整体修改）

- **目标**：前后端对齐、菜单/路由、快速采集与任务列表、任务详情与步骤时间线、采集配置与定时、采集历史、实时进度与错误处理；账号统一从数据库；可选扩展（数据域、日期范围、删除任务等）。
- **进度**：仅 5.1（历史列表）已勾选；1.x～4.x、5.2～5.3、6.x、7.x（DELETE 任务接口）、8.x 多为未勾选。
- **状态**：**大部分未做**，依赖后端步骤可观测与任务/配置 API 已就绪（add-collection-step-observability 已实现）。

---

## 二、依赖关系简述

- **add-collection-recorder-python-output**：是「录制→Python」的闭环，与 **optimize-component-version-management** 的录制保存（component_name 推导、新版本、file_path）有重叠，后者在 0.2 中已改为「保存即新版本」。
- **optimize-component-version-management**：依赖录制保存与 component_name 标准化；与 **add-collection-recorder-python-output** 的 save 语义衔接（后者主路径保存 .py，前者规定保存即新版本、版本化 file_path）。
- **add-web-captcha-optimization**：与录制/版本管理中的验证码类型、测试阶段回传（add-collection-recorder 的 7.x）互补，主流程已打通。
- **add-collection-step-observability**：为 **refresh-collection-module-frontend** 的「任务详情 + 步骤时间线」提供后端能力，应先于前端整体刷新验收。
- **refactor-collection-unify-sequential-parallel**：已归档；Phase 2 已作废，不再实施。

---

## 三、建议执行顺序（针对采集 Agent）

按「先收尾可归档 → 再完成未闭环 → 最后前端与架构」的顺序推进：

1. **optimize-component-version-management**  
   - 按 tasks.md 顺序完成：  
     - 1.5 回归（多版本测试、生产稳定版 file_path）  
     - 1.6 非登录组件测试前登录/复用会话  
     - 1.7 测试环境与生产对齐（SessionManager + 指纹、阶段可观测）  
     - 1.8 发现模式组件 test_mode/test_config  
     - 6.1 验收  
   - 全部完成后归档。

2. **add-collection-step-observability**  
   - 补 4.1～4.3 人工验收（步骤时间线、故意失败、多平台 async），通过后归档。

3. **refresh-collection-module-frontend**  
   - 在步骤可观测已验收的前提下，按 tasks.md 从 1.x 到 8.x 依次实施（菜单/路由、快速采集与任务列表、任务详情与步骤时间线、配置与定时、历史、进度与错误处理、DELETE 任务、验收与文档）。

---

## 四、日常自检（采集 Agent）

- 编写/修改采集组件时：必读 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`，遵循元素定位、等待、契约与各场景约定。
- 新增/修改 API：Pydantic 模型放在 `backend/schemas/`，路由带 `response_model`；异步路由用 `get_async_db()`。
- 录制与版本管理：component_name 按 `{platform}/{component_type}` 或 `{platform}/{domain}_export`（子域用 sub_domain）；保存即新版本、file_path 相对路径、测试与生产按 file_path 执行。
- 验证码：检测到即暂停、VerificationRequiredError、同一 page 回传；类型区分 OTP 与图形验证码。
- 归档前：运行 `openspec validate <change-id> --strict`，确认无遗漏；归档时使用 `openspec archive <change-id> [--yes]`，并视情况更新 `specs/`。

---

*文档生成后可根据实际归档与完成情况在仓库中更新。*
