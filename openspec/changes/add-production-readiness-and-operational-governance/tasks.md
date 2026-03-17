## 0. 前置条件

- [x] 0.1 `refactor-rules-and-code-patterns` 已完成 `docs/DEVELOPMENT_RULES/` 核心结构重构（7 个核心主题文件 + README 索引）——V1 Phase 1 已于 2026-03-16 完成
- [x] 0.2 确认 `docs/DEVELOPMENT_RULES/README.md` 已成为 L3 文档统一入口，再开始本提案文档落地

## 1. Phase 1: 规则与文档落地（P0 批次）

### 1A: 生产就绪规则

- [ ] 1.1 新建 `docs/DEVELOPMENT_RULES/PRODUCTION_READINESS.md`：包含 API SLO 表（D1）、容量基线、慢查询门禁、压测标准（D2）
- [ ] 1.2 在 `PRODUCTION_READINESS.md` 中记录发布三级策略（D3）：迁移预演、灰度规则、回滚策略分层
- [ ] 1.3 在 `PRODUCTION_READINESS.md` 中记录 RPO/RTO 目标（D4）和备份策略
- [ ] 1.4 在 `PRODUCTION_READINESS.md` 中定义 feature flag 命名规范和生命周期规则

### 1B: 数据治理规则

- [ ] 1.5 新建 `docs/DEVELOPMENT_RULES/DATA_GOVERNANCE.md`：包含数据四级分级表（D5）
- [ ] 1.6 在 `DATA_GOVERNANCE.md` 中列出当前系统 restricted 数据清单
- [ ] 1.7 在 `DATA_GOVERNANCE.md` 中定义敏感数据访问规则：查看/导出/日志脱敏/审计保留
- [ ] 1.8 在 `DATA_GOVERNANCE.md` 中定义敏感字段在 logger 中的脱敏模式（如手机号显示为 `186****9999`）

### 1C: 规则入口更新

- [ ] 1.9 在 `.cursorrules` 中添加生产治理入口指针："发布/回滚/数据分级规则见 `docs/DEVELOPMENT_RULES/PRODUCTION_READINESS.md` 和 `DATA_GOVERNANCE.md`"（预计 +2 行）
- [ ] 1.10 更新 `docs/DEVELOPMENT_RULES/README.md` 索引，加入新增文件

### 1D: Phase 1 验收关口

- [ ] 1.11 确认 `PRODUCTION_READINESS.md` 包含 D1-D4 全部内容
- [ ] 1.12 确认 `DATA_GOVERNANCE.md` 包含 D5 全部内容和 restricted 清单
- [ ] 1.13 确认 `.cursorrules` 和 `README.md` 索引已更新
- [ ] 1.14 确认 `.cursorrules` 行数仍 <= 310 行（V1 目标 300 行 + V2 预算 ~10 行）

## 2. Phase 2: 前端 Agent 规则（P1 批次）

### 2A: 前端模板文档

- [ ] 2.1 新建 `docs/DEVELOPMENT_RULES/FRONTEND_CODE_PATTERNS.md`
- [ ] 2.2 编写 API 函数模板：统一 try/catch、参数格式、返回值处理
- [ ] 2.3 编写 Pinia Store 模板：state/getters/actions 分离、loading 管理
- [ ] 2.4 编写列表页模板：统一查询/分页/筛选/局部 loading
- [ ] 2.5 编写表单页模板：统一校验/提交/反馈/错误提示
- [ ] 2.6 编写权限按钮模板（基于 `hasPermission()` + `v-if` 模式）和后台刷新模板

### 2B: 前端规则入口

- [ ] 2.7 在 `.cursorrules` 中添加前端规则：禁止页面直接写 axios、store actions/`$patch()` 外禁止修改 state（预计 +3 行）
- [ ] 2.8 在 `.cursorrules` 中添加指针："编写新前端页面前，先查阅 `FRONTEND_CODE_PATTERNS.md`"（预计 +1 行）
- [ ] 2.9 更新 `docs/DEVELOPMENT_RULES/README.md` 索引

### 2C: Phase 2 验收关口

- [ ] 2.10 确认 `FRONTEND_CODE_PATTERNS.md` 包含 D6 全部模板
- [ ] 2.11 确认 `.cursorrules` 已包含前端强制规则
- [ ] 2.12 确认 `.cursorrules` 行数仍 <= 310 行

## 3. Phase 3: ERP 业务验收标准（P1 批次）

- [ ] 3.1 在 `docs/DEVELOPMENT_RULES/PRODUCTION_READINESS.md` 中定义金额精度规则
- [ ] 3.2 定义时间口径规则：UTC、自然月 vs 财务月、数据归属
- [ ] 3.3 为收入（MyIncome）模块创建 acceptance checklist
- [ ] 3.4 为绩效（Performance）模块创建 acceptance checklist
- [ ] 3.5 为目标（Target）模块创建 acceptance checklist
- [ ] 3.6 为财务报表模块创建 acceptance checklist

### 3A: Phase 3 验收关口

- [ ] 3.7 确认每个关键域至少有 3 条验收项
- [ ] 3.8 确认金额和时间口径规则已明确且无歧义

## 4. Phase 4: 压测门禁（P2 批次）

- [ ] 4.1 选择压测工具（建议 k6）并添加到 dev 依赖
- [ ] 4.2 创建最小压测脚本：登录 + 列表查询 + 写操作
- [ ] 4.3 创建压测报告模板：并发数、错误率、p95/p99、连接池峰值
- [ ] 4.4 将压测脚本放入 `scripts/load_test/`
- [ ] 4.5 在 PR 模板或提测流程中加入"是否需要压测"检查项

### 4A: Phase 4 验收关口

- [ ] 4.6 压测脚本可在 staging 正常运行
- [ ] 4.7 50 并发用户报告已产出且符合 D1 SLO

## 5. Phase 5: 灾备恢复自动化（P2 批次）

- [ ] 5.1 创建 `scripts/verify_restore.py`：检查关键表行数、最新记录时间、引用完整性
- [ ] 5.2 创建恢复演练操作手册（runbook）
- [ ] 5.3 在 Docker 环境中执行一次完整恢复演练
- [ ] 5.4 记录首次演练结果和改进项

### 5A: Phase 5 验收关口

- [ ] 5.5 恢复演练成功完成
- [ ] 5.6 `verify_restore.py` 执行通过

## 6. 最终验证

- [ ] 6.1 确认 `docs/DEVELOPMENT_RULES/` 包含 3 个新文件（PRODUCTION_READINESS、DATA_GOVERNANCE、FRONTEND_CODE_PATTERNS）
- [ ] 6.2 确认 `.cursorrules` 包含生产治理和前端治理的入口指针，且总行数 <= 310 行
- [ ] 6.3 确认每个关键业务域有 acceptance checklist
- [ ] 6.4 确认 restricted 数据清单已完整
- [ ] 6.5 确认压测脚本可运行（如已执行 Phase 4）
- [ ] 6.6 确认恢复验证脚本可运行（如已执行 Phase 5）

