# Change: 混合采集（API + Playwright）按店铺分流

## Why

1. **API 授权覆盖不足**：大量 TikTok Shop / Shopee 店铺尚未完成平台 Open API 授权，仅靠 Playwright 才能采集这些店铺数据；已授权 API 的店铺若改用官方 API 可避免弹窗、验证码与反爬干扰，提高稳定性与数据准确性。
2. **统一体验与可扩展**：需要在一套任务模型下按店铺选择「API 直采」或「Playwright 模拟」，便于后续逐步提高 API 占比并降低对浏览器自动化的依赖。
3. **同步模块零改动**：当前数据同步模块（catalog_files → 字段映射 → 入库）运行良好，重构仅限采集侧；采集无论 API 还是 Playwright，均产出「文件 + catalog_files 登记」，下游同步逻辑保持不变。

## What Changes

### 1. 任务/店铺配置：采集方式标识

- 在账号或店铺维度增加「采集方式」配置（如 `collection_method`: `api` | `playwright`，或 `use_api`: bool）。
- 任务创建或下发时能推导出「该店铺是否使用 API 采集」。

### 2. 执行层：按店铺分流（API vs Playwright）

- 执行层根据任务对应的店铺配置，选择：
  - **已配置 API** → 走新增的「API 采集器」；
  - **未配置或 Playwright** → 走现有 Playwright 执行器（逻辑保持）。
- 统一任务模型（平台、店铺、数据域、日期等）不变，仅执行路径分支。

### 3. 新增 API 采集器（TikTok Shop / Shopee）

- 新增 API 采集适配器：调用平台 Open API（TikTok Shop Partner API、Shopee Open Platform）拉取订单、报表等（JSON）。
- 在采集模块内将 API 返回数据转换为与现有字段映射兼容的 Excel/CSV，**落盘与登记与当前 Playwright 流程对齐**：
  - **落盘目录**：`data/raw/YYYY/`（与现有 executor 的 `_process_files` 一致），保证同步侧 `_safe_resolve_path` 的允许根（data/raw、data/input、downloads、temp/outputs）内可解析。
  - **文件名与元数据**：使用 `StandardFileName.generate()` 生成标准文件名；使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 伴生文件（含 business_metadata、collection_info），便于解析 shop_id、date_from、date_to、account。
  - **登记**：落盘后调用现有 `catalog_scanner.register_single_file(落盘路径)`，复用去重、平台/数据域/粒度校验及相对路径存储，写入 `catalog_files` 的字段与 Playwright 路径一致（platform_code、shop_id、data_domain、date_from、date_to、file_path、status=pending 等），供现有同步管道消费且**无需改同步代码**。

### 4. 账号/店铺存储 API 鉴权信息

- 在账号或店铺配置中存储 API 所需鉴权（如 Shopee 的 partner_id/partner_key 及授权后的 access_token；TikTok Shop 的 OAuth 凭据），仅采集模块使用，同步模块不读取。

### 5. 数据同步模块与 catalog_files 契约

- **不修改**。同步模块的契约为：仅消费「catalog_files 中的记录 + 磁盘上 file_path 指向的文件」；`_safe_resolve_path` 仅解析允许根（data/raw、data/input、downloads、temp/outputs）下的路径，模板匹配依赖 platform_code、data_domain、granularity、sub_domain。API 路径通过「落盘到 data/raw/YYYY/ + 标准文件名 + .meta.json + register_single_file」满足该契约，故无需改动同步代码。若 API 来源列名与现有模板不一致，仅通过新增或调整字段映射模板（配置）解决。

## Impact

### 受影响的规格

- **data-collection**：ADDED 采集方式按店铺、API 采集器、统一产出契约（文件 + catalog_files）；可选 MODIFIED 多平台采集补充「或通过 API」场景。

### 受影响的代码（仅采集侧）

| 类型       | 位置/模块                         | 修改内容                                       |
|------------|------------------------------------|------------------------------------------------|
| 配置/模型  | 账号或店铺配置 / DB 或配置表       | 新增 collection_method 或 use_api、API 鉴权字段 |
| 采集       | 任务执行入口（如 collection 路由） | 按店铺配置选择 API 或 Playwright 执行路径      |
| 采集       | 新增模块                           | API 采集器（TikTok Shop / Shopee）：调 API、转文件、登记 catalog_files |
| 采集       | 现有 Playwright 执行器             | 保持现状，仅被「未选 API」时调用               |

### 不修改

- **data-sync**：无变更；仍从 catalog_files 读 file_path，做字段映射与入库。
- **field-mapping**：仅可能新增模板配置以兼容 API 来源列名，不强制改代码。

### 依赖关系

- 依赖现有：catalog_files 表结构、文件登记服务、Playwright 执行器、数据同步管道。
- 无前置变更阻塞；TikTok Shop / Shopee 的 API 文档与授权流程需在实现时对接。

## Non-Goals

- 不在此变更中实现「采集执行与 Backend 解耦」（本地 Agent 部署）——可后续单独提案。
- 不修改数据同步模块的代码或契约。
- 不在此变更中实现全部平台的 API 适配器；优先实现 Shopee 与 TikTok Shop，其他平台可后续扩展。
