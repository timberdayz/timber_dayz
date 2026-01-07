# 🧭 开发规则与框架规范（v2025-09-05）

> 文档索引（推荐入口）: docs/INDEX.md

本文件汇总并固化项目的开发框架与规则，作为工程落地的唯一标准参考（与 README、PROJECT_STATUS、OUTPUTS_NAMING 配套）。

## 1. 架构与模块边界

- 新架构入口：run_new.py；应用自动发现与注册（modules/core）
- 依赖方向：apps → services → core；禁止 apps 相互 import
- 导入零副作用：模块顶层不做 I/O/网络/进程；App 元数据通过类常量提供（禁止实例化收集）
- 配置注入：通过 config/ 注入，不在导入阶段读取

## 2. Playwright 与登录规范

- 唯一入口：严格使用 local_accounts.py 的 login_url；未配置必须报错提示补齐
- 技术选型：Playwright（禁用 Selenium）
- 下载稳定性：上下文级下载监听、显式 downloads_path、可选自动重新生成

## 3. 输出目录与命名（强制）

- 目录：account_slug/shop_slug\_\_shop_id/data_type/granularity（默认启用 shop_id；详见 docs/OUTPUTS_NAMING.md）
- data_type：traffic/products/orders/finance/…；granularity：daily/weekly/monthly/manual
- 文件名：`{YYYYMMDD_HHMMSS}__{account_slug}__{shop_slug}__{data_type}__{granularity}[__{start}_{end}].ext`
- 严禁硬编码路径；一律通过统一的 build_output_path/build_filename 与 safe_slug

## 4. 临时/日志/媒体管理

- 绝不删除：清理一律移动至 backups/ 或 temp/archive/
- 保留策略：
  - development：7 天
  - outputs（根部散落文件/.tmp/.bak）：30 天（结构化输出由 cleanup_outputs 管理）
  - media/screenshots：90 天
  - logs：180 天
- 工具：temp/development/cleanup_outputs.py、cleanup_temp_files.py（支持 --preflight/--apply）

## 5. 代码规范

- PEP 8 + 类型注解；4 空格缩进；行长 ≤ 88；snake_case/ PascalCase/ CONSTANT_CASE
- 导入顺序：标准库 → 第三方 → 本地；组间空行
- Docstring：Google 风格，说明参数/返回/示例
- 严禁在根目录创建非核心文件；按功能分类入目录

## 6. 测试与 CI

- 每个组件需提供最小“契约测试”（可基于探针/按钮存在性）
- 安全验证：测试/linters/builds 可在本地与 CI 执行
- 目录健康检查：.github/workflows/outputs_check.yml 调用 temp/development/check_outputs_ci.py

## 7. 变更半径与回滚

- 小步改动（≤150 行），优先兼容层与 Feature Flag
- 重要变更提供回滚步骤与开关；文档同步 README/DEVELOPMENT_ROADMAP/PROJECT_STATUS

## 8. 平台适配与复用

- 组件化优先：login/navigation/date_picker/export 统一抽象
- 平台适配器：modules/platforms/<platform>/adapter.py 返回平台实现
- 先 Shopee，再 TikTok；严格沿用相同命名与文件落地规范

## 9. 日志策略（控制台优先）

- 默认仅输出到终端；不自动启用文件 sink（遵循用户偏好）
- 如需文件日志：开发者手动临时开启并指定路径；任务结束后请关闭
- 禁止合并输出大日志文件；调试输出以终端复制为主

## 10.     录制模块冻结（2025-09-19）

- 自 2025-09-19 起，严禁对“1. 📊 数据采集录制”模块进行功能增强或结构性修改。
- 允许的改动：仅限文档补充、示例脚本注释优化、明显错误的修正（不改变现有录制流程行为）。
- 影响范围：录制向导、录制脚本模板、Inspector 启动/暂停逻辑等。
- 原因：多次增强导致录制不稳定。冻结以保证录制能力稳定可用。

## 11. 一键/并行执行规范（2025-09-25 新增）

- 子进程“闲置超时”语义：仅在连续无输出达到 cap_to 秒（默认 600s）时判定该子进程超时；不再使用“全局墙钟超时”。
- 子进程禁止交互：一键/并行模式下，任何 input()/回车提示必须被条件保护（例如 `if not _one_click_mode: input(...)`）。
- 结果收集：子进程结束时必须输出 ONE_CLICK_RESULT_JSON（含 files/file_uris），父进程聚合并打印“🗂️ 导出文件清单（全部平台）”。

## 12. 平台切换确认（Miaoshou 订单）

- 顺序要求：导航 → 平台切换确认（最多 2 轮：点击标签 → 深链接）→ 日期选择 → 导出。
- 切换判定：以 URL ?platform= 为准（lowercase 匹配），不可仅凭 UI 高亮状态。
- 深链接来源：统一从 modules/platforms/miaoshou/components/orders_config.py 的 deep_link_template 读取，业务层禁止硬编码。

## 13. 输出清单与落盘校验

- 一键模式必须汇总“成功导出文件清单”：打印绝对路径与 file:/// 链接，并以“EXPORTED_FILE:” 标记，便于快速检索与人工核查。
- 妙手“商品表现”归于 products/snapshot（时点快照），订单表现按子类型（orders/shopee|tiktok/daily|weekly）分目录存放。
- 若出现跨平台/跨域落盘（路径污染），以 URL 与执行上下文的 platform/account/shop 强校验为准，立即记录告警并停止后续跨域写入。

## 14. 数据库与入库架构（2025-09-25 新增）

- 数据域优先级：先 Orders/Products，后 Metrics（daily/weekly/monthly）。
- 主键与去重：
  - 订单：platform + shop_id + order_id 唯一
  - 产品：platform + shop_id + platform_sku 唯一
  - 指标（日/周/月）：platform + shop_id + sku + metric_date + metric_type 唯一
- 权威清单：数据库表 catalog_files 为权威记录（hash/size/source/path/metadata/status）；
  - 目录级“月度清单（.jsonl/.json.gz）”可选，减少旁文件数量；不再强制每个 .xlsx 生成 .json。
  - 入库源以 temp/outputs 为主；支持手动上传目录 data/input/manual_uploads/；downloads/ 与 profiles/ 仅作补偿来源。
- 入库标准流程（manifest-first + 缺失清单回填）：
  - 优先读取旁清单/目录清单；
  - 若缺失，则从“路径/文件名 + Excel 表头嗅探”回填最小元数据；
  - 计算文件哈希，按主键幂等 upsert，失败入 quarantine 并落 catalog_files。
- 汇率与货币：每日从 exchangerate.host 拉取，缓存至 dim_currency_rates；统一提供 RMB 归一列；失败走固定汇率兜底。
- 数据库策略：
  - Dev：SQLite（默认 DATABASE_URL）；
  - Prod：PostgreSQL（推荐），统一用 SQLAlchemy + Alembic 管理迁移；通过 DATABASE_URL 切换；建议连接池 pool_size=10、max_overflow=20。
