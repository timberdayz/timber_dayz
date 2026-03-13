# Tasks: 混合采集（API + Playwright）按店铺分流

**搁置**：本提案已搁置，暂不实施。详见 `proposal.md` 顶部「搁置说明」。以下任务保留供后续恢复排期时使用。

## 1. 配置与数据模型

- [ ] 1.1 在账号或店铺维度增加「采集方式」与 API 鉴权存储
  - 方案 A：扩展现有账号/店铺表或配置表，增加 `collection_method`（api | playwright）及 API 相关字段（如 partner_id、partner_key、access_token 等，按平台区分）
  - 方案 B：独立「采集配置」表，关联账号/店铺，包含 collection_method 与 API 凭据
  - 确定后补充 Alembic 迁移（若改表）
- [ ] 1.2 后端配置/模型与 API：若存在账号/店铺管理 API，增加采集方式与 API 凭据的读写（敏感字段仅限采集服务使用，不向前端明文暴露）

## 2. 任务层与执行层分流

- [ ] 2.1 任务创建或执行入口处，根据「店铺/账号」解析是否使用 API 采集（读取 collection_method 或 use_api）
- [ ] 2.2 执行层路由：若使用 API → 调用 API 采集器；否则 → 调用现有 Playwright 执行器（保持现有调用方式不变）
- [ ] 2.3 统一任务模型不变（平台、店铺、数据域、日期范围等），仅在执行分支上区分

## 3. API 采集器（核心）

- [ ] 3.1 实现「API 采集适配器」抽象或接口：输入（平台、店铺、数据域、日期范围、鉴权），输出（落盘文件路径；内部完成落盘 + 写 .meta.json + 调用 register_single_file）
- [ ] 3.2 Shopee Open Platform 适配器
  - 鉴权：partner_id / partner_key，获取 access_token（按文档时效刷新）
  - 调用订单/报表等 API，获取 JSON
  - 将结果转换为与现有字段映射兼容的 Excel/CSV（列名与现有模板一致或新增模板可映射）
  - **落盘**：目标目录 `data/raw/YYYY/`（YYYY 为当前年或按日期范围）；文件名使用 `StandardFileName.generate(source_platform, data_domain, granularity, sub_domain, ext)`；写入后调用 `MetadataManager.create_meta_file()` 生成 `.meta.json`（business_metadata：source_platform、data_domain、date_from、date_to、shop_id；collection_info：account、shop_id、collection_platform 等）
  - **登记**：调用 `catalog_scanner.register_single_file(落盘绝对路径)`，复用现有去重与字段填充，不手写 CatalogFile 插入
- [ ] 3.3 TikTok Shop Partner API 适配器
  - 鉴权：OAuth 或 Partner Center 文档要求的方式
  - 调用订单/商品/报表等 API，获取 JSON
  - 同上：转 Excel/CSV；落盘到 data/raw/YYYY/ + StandardFileName + .meta.json；调用 register_single_file
- [ ] 3.4 错误处理与重试：API 限流、超时、鉴权失效时记录状态并可选重试，与现有采集任务状态一致（如 failed、error_message）

## 4. 文件登记与格式兼容

- [ ] 4.1 确保 API 采集器**仅通过** `catalog_scanner.register_single_file(落盘路径)` 登记；落盘路径需满足：位于 `data/raw/YYYY/`、文件名为 StandardFileName 可解析格式、同路径下存在 .meta.json（以便 register_single_file 解析 shop_id、日期、account 并正确去重与填 catalog 字段），保证与 Playwright 路径登记结果一致，同步侧无例外
- [ ] 4.2 若 API 来源列名与现有字段映射模板不一致，在采集层做列映射或新增 field_mapping_templates 配置，确保现有同步管道无需改代码即可入库

## 5. 验收与文档

- [ ] 5.1 验收：对「已配置 API」的店铺创建采集任务，执行后能在 catalog_files 中看到新记录，且同步模块能正常对该文件做字段映射与入库
- [ ] 5.2 验收：对「未配置 API」的店铺，仍走 Playwright，行为与当前一致
- [ ] 5.3 更新数据采集相关文档（若存在），说明如何配置 API 采集及支持的平台
