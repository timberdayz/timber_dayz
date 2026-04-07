# add-hybrid-collection-api-playwright 与开发需求对齐评估

**评估时间**：2026-03-13  
**提案首次提交**：2026-02-19（git commit: feat:数据采集优化提案完成）

---

## 一、提案创建时间

- 该提案于 **2026-02-19** 随提交「feat:数据采集优化提案完成」加入仓库，早于后续的组件版本管理、验证码优化、录制 Python 产出等变更，但**不依赖**这些变更，也未与它们冲突。

---

## 二、与当前开发需求的一致性

### 1. 与现有架构的契合

| 维度 | 当前约定 / 实现 | 本提案 | 结论 |
|------|------------------|--------|------|
| **数据同步零改动** | 同步模块仅消费 catalog_files + file_path，禁止改同步契约 | 明确「不修改 data-sync」；API 路径产出「文件 + catalog_files」，与 Playwright 一致 | 一致 |
| **catalog_files 与落盘** | 文件落盘 data/raw/YYYY/，StandardFileName、MetadataManager.create_meta_file、register_single_file | 提案要求 API 采集器落盘至 data/raw/YYYY/，使用 StandardFileName.generate、create_meta_file、register_single_file，与 design/tasks 一致 | 一致 |
| **Playwright 路径保持** | 当前仅 Playwright 采集，executor_v2 + 组件版本管理 + Python 组件 | 提案：未配置 API 或显式 Playwright 时走现有 Playwright 执行器，逻辑保持不变 | 一致 |
| **任务模型统一** | 任务含平台、账号、数据域、日期等 | 提案保持任务模型不变，仅在执行层按店铺配置分流 API / Playwright | 一致 |

### 2. 与后续采集变更的关系

- **optimize-component-version-management**：针对 Playwright 组件的版本、file_path、适配器；本提案仅在执行入口增加「API vs Playwright」分支，Playwright 分支仍走现有执行器，**无冲突**。
- **add-web-captcha-optimization**：针对 Playwright 登录验证码；API 路径不涉及浏览器与验证码，**无冲突**。
- **add-collection-recorder-python-output**：针对录制产出 Python 组件；API 路径不涉及录制与组件，**无冲突**。
- **refactor-collection-unify-sequential-parallel**：Phase 1 统一顺序/并行为 adapter 模型；本提案在「选好 API 或 Playwright 之后」再走现有 Playwright 执行器，**无冲突**。

### 3. 与主 spec 及规范的关系

- **data-collection 主 spec**：要求多平台自动化数据采集、文件注册到 catalog_files；未限定「仅 Playwright」。本提案 **ADDED**「按店铺可选 API 或 Playwright」「API 采集器」「统一产出契约」，为能力扩展，不削弱既有要求。
- **.cursorrules**：SSOT（schema/catalog_files）、Contract-First、禁止改同步契约等，提案均遵守；新增配置（collection_method、API 鉴权）属采集侧扩展，需落库时走 Alembic 迁移即可。

### 4. 设计决策与实现要点

- **统一产出契约**：无论 API 还是 Playwright，均为「文件 + catalog_files 登记」——与现有同步消费方式一致，无需同步侧改动。
- **分流方式**：执行入口按店铺/账号的 collection_method 选择 API 采集器或 Playwright 执行器，不替换、不重写现有 Playwright 流程。
- **API 采集器**：新模块，调用平台 Open API → 转 Excel/CSV → 落盘 data/raw/YYYY/ + StandardFileName + .meta.json → register_single_file，与 design.md、tasks.md 一致。

---

## 三、结论与建议

- **创建时间**：2026-02-19。
- **是否符合开发需求**：**符合**。提案在保持 Playwright 路径与数据同步契约不变的前提下，增加「按店铺 API/Playwright 分流」与「API 采集器」，与当前架构、主 spec 及后续采集相关变更一致，无冲突。
- **建议**：可保留本提案并按 tasks.md 排期实现；实现时注意：
  - 配置层：在账号/店铺维度新增 collection_method 与 API 鉴权存储时，遵循现有表结构与迁移规范（若改表则 Alembic + 幂等）。
  - 执行层：在现有任务执行入口（如 `_execute_collection_task_background` 或调用 executor 前）按店铺解析 collection_method，分支调用 API 采集器或现有 Playwright 执行器。
  - API 采集器：严格复用 StandardFileName、MetadataManager、register_single_file，保证与 Playwright 产出的 catalog 与文件格式一致，以便同步模块零改动。
