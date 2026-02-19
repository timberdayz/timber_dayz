# Design: 混合采集（API + Playwright）架构决策

## Context

- 当前采集仅支持 Playwright：浏览器下载 Excel → 落盘 → 登记 catalog_files，下游数据同步模块按 file_path 读文件并入库。
- 需求：部分店铺已具备 TikTok Shop / Shopee 的 Open API 授权，希望用 API 直采以规避弹窗与反爬；未授权店铺继续 Playwright。同步模块需保持零改动。

## Goals / Non-Goals

- **Goals**：按店铺选择 API 或 Playwright；两种路径产出统一契约（文件 + catalog_files）；不修改数据同步模块。
- **Non-Goals**：不在此设计中实现采集执行与 Backend 解耦（本地 Agent）、不实现全部平台的 API、不改变同步模块接口。

## Decisions

### 1. 统一产出契约：始终「文件 + catalog_files」

- **决策**：无论 API 还是 Playwright，采集层最终都产出「磁盘上的文件」+「一条 catalog_files 记录」。
- **理由**：同步模块已稳定依赖「从 catalog_files 取 file_path → 读文件 → 字段映射 → 入库」。若 API 路径直接写库或走另一套接口，会破坏该契约并迫使同步模块大改。保持契约后，仅采集侧多一条「API → 转文件 → 登记」的路径即可。
- **替代**：让同步模块支持「从 API 响应直接入库」——被否决，因与「尽量不改同步」冲突。

### 2. 采集方式配置落在账号/店铺维度

- **决策**：在账号或店铺维度存储 `collection_method`（api | playwright）及 API 鉴权信息，任务执行时根据「该任务对应的店铺」解析采集方式。
- **理由**：API 授权是「按店铺/按卖家」的，与账号或店铺一一对应；任务模型已有平台、账号、店铺，便于解析。
- **替代**：在任务级别由用户每次选择——增加操作成本且易与店铺实际授权状态不一致。

### 3. 执行层「策略路由」而非替换 Playwright

- **决策**：在执行入口根据店铺配置做分支：API → API 采集器，否则 → 现有 Playwright 执行器。不替换、不重写现有 Playwright 流程。
- **理由**：降低风险，未配置 API 的店铺行为与当前完全一致；后续扩展其他数据源可继续加分支或抽象为策略/适配器表。

### 4. API 采集器输出格式与现有模板兼容

- **决策**：API 返回的 JSON 在采集模块内转换为 Excel/CSV，列名与数据类型与现有字段映射模板一致（或新增仅列名不同的模板），以便现有解析与入库逻辑无需改代码。
- **理由**：同步模块的字段映射与入库是针对「文件列」设计的；保持「文件形态 + 列语义一致」即可零改动。若某平台 API 列名与后台导出不一致，仅在采集层做一次映射到「标准列名」或新增模板配置。

### 5. 文件路径、命名与登记与 Playwright 流程对齐

- **决策**：API 产出的文件写入 **data/raw/YYYY/**（与当前 executor_v2._process_files 一致），使用 **StandardFileName.generate()** 生成文件名，使用 **MetadataManager.create_meta_file()** 生成 **.meta.json** 伴生文件，然后调用 **catalog_scanner.register_single_file(落盘路径)** 登记，不手写 CatalogFile 插入。
- **理由**：同步侧 `_safe_resolve_path` 的允许根包含 data/raw；register_single_file 依赖标准文件名与 .meta.json 解析 platform、data_domain、shop_id、日期等并做 file_hash 去重。与 Playwright 共用同一套落盘与登记流程，可保证 catalog 字段、相对路径存储、去重行为一致，同步模块零改动、零例外分支。
- **替代**：API 路径写 temp/outputs 再手写 CatalogFile 插入——易导致字段或去重与现有逻辑不一致，不采纳。

## Risks / Trade-offs

- **API 限流与时效**：平台 API 有 QPS 与 token 时效，需在适配器内实现重试、退避与 token 刷新；失败时写入任务状态与 error_message，与 Playwright 失败一致。
- **列名与模板维护**：新增 API 来源后，若列名与现有模板不完全一致，需维护多套模板或采集层做列映射，增加少量配置与测试成本——可接受，以换取同步模块零改动。

## Migration Plan

- 无数据迁移强制要求。新增配置字段后，现有账号/店铺默认视为「未配置 API」或 collection_method=playwright，行为与当前一致。
- 逐步为已授权 API 的店铺配置 collection_method=api 与凭据，验证通过后即可切到 API 采集。

## Open Questions

- 账号/店铺配置存储的具体表结构（扩展现有表 vs 独立采集配置表）可在实现阶段根据现有代码结构确定。
- TikTok Shop / Shopee 的 API 文档与授权流程以官方最新文档为准，实现时需对接并处理各站点差异（如 Shopee 多站点）。

## 与现有采集流程的对应关系

- **Playwright 当前流程**（executor_v2._process_files）：下载文件 → 移动至 data/raw/YYYY/，StandardFileName.generate → MetadataManager.create_meta_file → register_single_file(target_path)。
- **API 采集器**：API 响应 → 转 Excel/CSV → 写入 data/raw/YYYY/（StandardFileName.generate）→ create_meta_file → register_single_file。仅数据来源不同，落盘与登记路径与 Playwright 完全一致，便于维护与同步契约统一。
