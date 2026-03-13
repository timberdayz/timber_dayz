# 数据采集能力 - 混合采集变更增量

## ADDED Requirements

### Requirement: 采集方式按店铺可配置

系统 SHALL 支持在账号或店铺维度配置采集方式（API 或 Playwright），并在执行采集任务时根据该配置选择对应的采集实现。

#### Scenario: 已配置 API 的店铺走 API 采集

- **WHEN** 创建或执行采集任务时，该任务对应的店铺已配置为使用 API 采集（如 collection_method=api 或 use_api=true）
- **THEN** 系统使用平台 Open API（TikTok Shop / Shopee）拉取数据，而非启动 Playwright 浏览器
- **AND** 系统不打开浏览器、不处理页面弹窗或验证码

#### Scenario: 未配置 API 的店铺走 Playwright 采集

- **WHEN** 创建或执行采集任务时，该任务对应的店铺未配置 API 采集或显式配置为 Playwright
- **THEN** 系统使用现有 Playwright 执行器进行浏览器自动化采集
- **AND** 行为与变更前一致（登录、导航、导出、文件落盘、登记 catalog_files）

#### Scenario: 任务模型与执行分支解耦

- **WHEN** 上层调度或 API 下发采集任务
- **THEN** 任务模型统一包含平台、店铺、数据域、日期范围等信息，不因采集方式不同而改变
- **AND** 执行层根据店铺的采集方式配置自动选择 API 或 Playwright 路径

### Requirement: API 采集器产出与同步契约一致

系统 SHALL 使 API 采集路径产出的数据以「文件 + catalog_files 登记」的形式呈现，与 Playwright 采集路径一致，供现有数据同步模块消费且无需修改同步逻辑。

#### Scenario: API 数据落盘并登记

- **WHEN** API 采集器从平台 Open API 获取到订单或报表数据（JSON）
- **THEN** 系统在采集模块内将数据转换为与现有字段映射兼容的 Excel 或 CSV
- **AND** 系统将文件写入 data/raw/YYYY/ 目录（YYYY 为当前年或按日期），文件名使用 StandardFileName.generate 生成，并生成同路径下的 .meta.json 伴生文件（含 business_metadata、collection_info）
- **AND** 系统调用 catalog_scanner.register_single_file(落盘路径) 登记，与 Playwright 路径共用同一登记逻辑，向 catalog_files 写入记录（platform_code、shop_id、data_domain、date_from、date_to、file_path、status=pending 等，含相对路径与去重）
- **AND** 现有数据同步模块可像处理 Playwright 产出文件一样对该记录进行字段映射与入库，无需修改同步代码

#### Scenario: API 产出文件格式可被现有模板映射

- **WHEN** API 采集器生成的文件列名或格式与某平台后台导出的 Excel 不完全一致
- **THEN** 系统在采集层做列映射或提供可配置的模板（如新增 field_mapping_templates 行），使同步模块的现有解析与入库逻辑无需改代码即可处理
- **AND** 不要求数据同步模块增加「直接消费 API 响应」的分支

### Requirement: 平台 Open API 采集适配器

系统 SHALL 提供基于平台 Open API 的采集适配器，至少支持 Shopee 与 TikTok Shop，用于在店铺已授权 API 时拉取订单、报表等数据并转化为文件并登记。

#### Scenario: Shopee Open Platform 采集

- **WHEN** 店铺已配置 Shopee API 鉴权（如 partner_id、partner_key 及有效 access_token）且采集方式为 API
- **THEN** 系统调用 Shopee Open Platform 订单/报表等接口获取数据
- **AND** 系统将响应转换为与现有字段映射兼容的文件并落盘、登记 catalog_files
- **AND** 鉴权失效或限流时记录错误状态并可配置重试

#### Scenario: TikTok Shop Partner API 采集

- **WHEN** 店铺已配置 TikTok Shop API 鉴权（如 OAuth 或 Partner Center 要求的方式）且采集方式为 API
- **THEN** 系统调用 TikTok Shop Partner API 获取订单/商品/报表等数据
- **AND** 系统将响应转换为与现有字段映射兼容的文件并落盘、登记 catalog_files
- **AND** 鉴权失效或限流时记录错误状态并可配置重试

#### Scenario: API 采集失败不影响 Playwright 路径

- **WHEN** 某店铺配置为 API 采集但 API 调用失败（如网络、限流、鉴权过期）
- **THEN** 系统将任务标记为失败或可重试，并记录错误信息
- **AND** 未配置为 API 的其他店铺的 Playwright 采集任务不受影响
