# Tasks: 验证并完善数据采集-同步端到端管道

## 概述

验证并修复数据采集和同步的完整管道，确保生产环境可部署。

**总预估时间**: 2-3天  
**优先级说明**: P0 = 阻塞性, P1 = 高优先级, P2 = 中优先级

---

## Phase 1: 录制工具功能验证（P0）- 预计 0.5 天

### 1.1 测试录制工具V2核心功能

- [ ] 1.1.1 测试妙手ERP登录组件录制
  - 命令: `python tools/record_component.py --platform miaoshou --component login --account {account_id}`
  - 验证: 生成的 `config/collection_components/miaoshou/login.yaml` 包含完整步骤
  - 验证: YAML包含 `success_criteria` 配置
  - 验证: YAML包含 `popup_handling` 配置

- [ ] 1.1.2 测试自动登录功能
  - 命令: `python tools/record_component.py --platform miaoshou --component navigation --account {account_id}`
  - 验证: 系统自动加载并执行 `miaoshou/login.yaml`
  - 验证: 登录成功后才开始录制navigation组件
  - 验证: 控制台输出显示"自动登录成功"

- [ ] 1.1.3 测试Playwright Inspector捕获
  - 在录制过程中执行5个操作（点击、输入、选择等）
  - 验证: 生成的YAML包含所有5个操作
  - 验证: 选择器格式正确（如 `role=button[name='xxx']`）

- [ ] 1.1.4 测试YAML生成质量
  - 检查生成的 `success_criteria` 是否合理
  - 检查生成的 `popup_handling` 配置是否存在
  - 检查 `verification_handlers` 配置是否存在

### 1.2 修复发现的问题

- [ ] 1.2.1 根据测试结果修复录制工具bug
  - 如果自动登录失败：修复 `_auto_login` 方法
  - 如果Inspector未捕获操作：检查 `page.pause()` 调用
  - 如果YAML格式错误：修复 `_generate_yaml_v2` 方法

- [ ] 1.2.2 更新录制工具文档
  - 文件: `docs/guides/component_recording.md`
  - 新增: 实际录制流程示例（包含妙手ERP截图）
  - 新增: 常见问题排查指南

---

## Phase 2: 妙手ERP核心组件录制（P0）- 预计 1 天

### 2.1 录制必需组件

- [ ] 2.1.1 录制妙手ERP登录组件
  - 命令: `python tools/record_component.py --platform miaoshou --component login --account {account_id}`
  - 输出文件: `config/collection_components/miaoshou/login.yaml`
  - 验证: 使用 `python tools/test_component.py -p miaoshou -c login -a {account_id}` 测试通过

- [ ] 2.1.2 录制妙手ERP导航组件
  - 命令: `python tools/record_component.py --platform miaoshou --component navigation --account {account_id}`
  - 输出文件: `config/collection_components/miaoshou/navigation.yaml`
  - 验证: 测试工具验证通过

- [ ] 2.1.3 录制妙手ERP订单导出组件
  - 命令: `python tools/record_component.py --platform miaoshou --component export --account {account_id} --data-domain orders`
  - 输出文件: `config/collection_components/miaoshou/orders_export.yaml`
  - 验证: 测试工具验证通过，文件成功下载

- [ ] 2.1.4 录制妙手ERP产品导出组件
  - 命令: `python tools/record_component.py --platform miaoshou --component export --account {account_id} --data-domain products`
  - 输出文件: `config/collection_components/miaoshou/products_export.yaml`
  - 验证: 测试工具验证通过，文件成功下载

### 2.2 组件测试验证

- [ ] 2.2.1 创建组件测试报告
  - 文件: `temp/development/miaoshou_component_test_report.md`
  - 内容: 每个组件的测试结果、执行时间、成功率

- [ ] 2.2.2 验证组件可组装性
  - 测试: 手动组装 login → navigation → orders_export
  - 验证: 完整流程可以正常执行

---

## Phase 3: 端到端流程集成测试（P0）- 预计 0.5 天

### 3.1 采集流程测试

- [ ] 3.1.1 通过前端创建测试采集配置
  - 访问: `http://localhost:5173/collection-config`
  - 创建配置:
    - 平台: 妙手ERP
    - 账号: {选择一个测试账号}
    - 数据域: orders
    - 日期: 昨天
  - 验证: 配置创建成功

- [ ] 3.1.2 手动触发采集任务
  - 访问: `http://localhost:5173/collection-tasks`
  - 点击"快速采集"，选择妙手ERP + orders + 昨天
  - 验证: 任务创建成功，状态为 `running`

- [ ] 3.1.3 验证实时进度显示
  - 查看: CollectionTasks页面的进度条
  - 验证: WebSocket实时推送进度更新
  - 验证: 显示当前步骤（"正在登录..." → "正在下载..."）

- [ ] 3.1.4 验证文件下载和命名
  - 等待任务完成
  - 检查目录: `data/raw/2025/`
  - 验证: 文件命名符合规范（`miaoshou_orders_daily_YYYYMMDD_HHMMSS.xlsx`）
  - 验证: 存在伴生文件 `.meta.json`

### 3.2 文件注册验证

- [ ] 3.2.1 验证catalog_files表注册
  - 查询: `SELECT * FROM catalog_files ORDER BY created_at DESC LIMIT 5`
  - 验证: 新增记录存在
  - 验证: 元数据字段完整（platform_code='miaoshou', data_domain='orders', status='pending'）
  - 验证: file_path指向正确的文件路径

- [ ] 3.2.2 验证文件哈希去重
  - 重新触发相同的采集任务
  - 验证: catalog_files表不创建重复记录（file_hash唯一性）

### 3.3 数据同步测试

- [ ] 3.3.1 触发单文件同步
  - API调用: `POST /api/data-sync/sync-file/{file_id}`
  - 验证: API返回成功响应
  - 验证: 文件状态更新为 `ingested`

- [ ] 3.3.2 验证事实表数据入库
  - 查询: `SELECT * FROM b_class.fact_miaoshou_orders_daily ORDER BY ingest_timestamp DESC LIMIT 10`
  - 验证: 数据成功入库
  - 验证: JSONB格式存储原始数据
  - 验证: data_hash唯一性约束生效

- [ ] 3.3.3 验证数据行数一致性
  - 对比: Excel文件行数 vs 数据库表行数
  - 验证: 导入行数合理（允许5%去重误差）
  - 如果差异>5%: 检查去重配置和data_hash计算逻辑

### 3.4 批量同步测试

- [ ] 3.4.1 触发批量同步
  - API调用: `POST /api/data-sync/trigger`（指定平台=miaoshou, data_domain=orders）
  - 验证: API立即返回task_id
  - 验证: 任务状态为 `processing`

- [ ] 3.4.2 查询同步进度
  - API调用: `GET /api/data-sync/progress/{task_id}`
  - 验证: 返回实时进度（processed_files, file_progress）
  - 验证: 任务完成后状态更新为 `completed`

- [ ] 3.4.3 验证同步统计
  - 检查: 同步结果统计（total_files, imported_rows, skipped_files）
  - 验证: 统计数据准确

---

## Phase 4: 定时同步机制验证（P1）- 预计 0.5 天

### 4.1 定时采集验证

- [ ] 4.1.1 创建定时采集配置
  - 通过前端配置界面创建定时任务
  - Cron表达式: 测试用（每5分钟：`*/5 * * * *`）
  - 验证: APScheduler job已注册

- [ ] 4.1.2 验证定时任务触发
  - 等待5分钟
  - 查看后端日志: 查找"定时任务触发"相关日志
  - 查询数据库: 验证新的采集任务已创建
  - 验证: 任务自动执行并完成

### 4.2 定时数据同步验证

- [ ] 4.2.1 检查数据同步定时任务
  - 查看: `backend/main.py` lifespan事件
  - 验证: 物化视图刷新定时任务已注册（每天凌晨2点）

- [ ] 4.2.2 手动触发物化视图刷新
  - API调用: `POST /api/materialized-views/refresh`（如果存在）
  - 或运行脚本: `python scripts/refresh_materialized_views.py`
  - 验证: 物化视图数据更新

---

## Phase 5: 云端部署预检查（P1）- 预计 0.5 天

### 5.1 环境变量配置检查

- [ ] 5.1.1 创建云端环境变量清单
  - 文件: `docs/deployment/cloud_environment_variables.md`
  - 包含: PROJECT_ROOT, DATA_DIR, DOWNLOADS_DIR, TEMP_DIR, DATABASE_URL, PLAYWRIGHT_HEADLESS, ENVIRONMENT, MAX_COLLECTION_TASKS
  - 说明: 每个变量的作用和默认值

- [ ] 5.1.2 验证路径管理器环境变量支持
  - 检查: `modules/core/path_manager.py`
  - 验证: get_project_root()优先使用环境变量
  - 验证: 所有路径函数支持环境变量覆盖

### 5.2 Docker配置验证

- [ ] 5.2.1 验证Docker Compose配置
  - 文件: `docker-compose.collection.yml`
  - 检查: Playwright依赖安装完整
  - 检查: 环境变量传递正确

- [ ] 5.2.2 测试无头浏览器模式
  - 设置: `PLAYWRIGHT_HEADLESS=true` 和 `ENVIRONMENT=production`
  - 测试: 执行一个简单采集任务
  - 验证: 任务正常完成，无需显示浏览器窗口

### 5.3 硬编码路径检查

- [ ] 5.3.1 代码扫描硬编码路径
  - 命令: `rg "f:\\\\|F:\\\\|C:\\\\Users|/home/|/Users/" --type py`
  - 验证: 仅在配置文件或测试文件中存在硬编码
  - 修复: 如果核心代码有硬编码，改为使用path_manager

---

## Phase 6: 合规性验证（P0）⭐ - 预计 0.5 天

### 6.1 SSOT架构验证

- [ ] 6.1.1 运行SSOT验证脚本
  - 命令: `python scripts/verify_architecture_ssot.py`
  - 期望: 100%合规，无重复ORM模型定义
  - 修复: 如果发现重复定义，删除并统一使用schema.py

### 6.2 Contract-First验证

- [ ] 6.2.1 运行Contract-First验证脚本
  - 命令: `python scripts/verify_contract_first.py`
  - 检查项:
    - 重复Pydantic模型定义
    - response_model覆盖率
    - schemas/目录覆盖率
  - 期望: 所有采集和同步API都有response_model
  - 修复: 如果缺少response_model，补充到对应的@router装饰器

- [ ] 6.2.2 验证schemas定义位置
  - 检查: `backend/schemas/collection.py` 存在
  - 检查: `backend/schemas/data_sync.py` 存在
  - 验证: routers/中没有定义Pydantic模型
  - 修复: 如果routers/中有模型定义，移动到schemas/

### 6.3 API契约一致性验证

- [ ] 6.3.1 运行API一致性验证脚本
  - 命令: `python scripts/verify_api_contract_consistency.py`
  - 检查: 前端API调用是否匹配后端端点
  - 修复: 如果不一致，更新前端或后端

---

## Phase 7: 端到端测试脚本编写（P1）- 预计 0.5 天

### 7.1 创建端到端测试

- [ ] 7.1.1 编写完整流程测试脚本
  - 文件: `tests/e2e/test_complete_collection_to_sync.py`
  - 测试流程:
    1. 创建采集配置
    2. 触发采集任务
    3. 等待任务完成
    4. 验证文件下载和注册
    5. 触发数据同步
    6. 验证数据入库
  - 使用: pytest + 真实账号（或mock）

- [ ] 7.1.2 运行端到端测试
  - 命令: `pytest tests/e2e/test_complete_collection_to_sync.py -v`
  - 验证: 所有测试通过

- [ ] 7.1.3 创建测试总结报告
  - 文件: `temp/development/e2e_test_report.md`
  - 内容: 测试结果、发现的问题、修复建议

---

## 验证清单

### 功能验证

- [ ] V1: 录制工具自动登录功能正常
- [ ] V2: Playwright Inspector捕获所有用户操作
- [ ] V3: 生成的YAML格式正确且完整
- [ ] V4: 组件测试工具验证通过
- [ ] V5: 端到端采集流程成功（登录→下载→注册）
- [ ] V6: 文件正确保存到data/raw/YYYY/目录
- [ ] V7: catalog_files表正确注册文件
- [ ] V8: 元数据字段完整且正确
- [ ] V9: 数据同步流程正常（单文件+批量）
- [ ] V10: 数据正确入库到事实表
- [ ] V11: 去重机制正常工作
- [ ] V12: 数据行数验证通过
- [ ] V13: 定时采集任务正常触发
- [ ] V14: 定时同步任务正常触发
- [ ] V15: 物化视图刷新机制正常

### 云端部署验证

- [ ] D1: 环境变量清单完整
- [ ] D2: 路径管理器支持环境变量
- [ ] D3: Docker Compose配置正确
- [ ] D4: 无头浏览器模式正常工作
- [ ] D5: 无硬编码路径问题

### 合规性验证 ⭐

- [ ] C1: SSOT验证通过（100%）
- [ ] C2: Contract-First验证通过
- [ ] C3: response_model覆盖率100%
- [ ] C4: schemas定义在正确位置
- [ ] C5: API契约一致性验证通过

---

## 依赖关系

```
Phase 1 (录制工具验证)
    │
    ├──▶ Phase 2 (组件录制)
    │       │
    │       └──▶ Phase 3 (端到端测试)
    │               │
    │               └──▶ Phase 4 (定时任务)
    │
    └──▶ Phase 5 (云端检查)
            │
            └──▶ Phase 6 (合规性验证) ⭐
                    │
                    └──▶ Phase 7 (测试脚本)
```

---

## 注意事项

1. **录制工具**：Phase 2.1代码已实现但未经实际测试，可能需要调试
2. **真实账号**：录制和测试需要真实的妙手ERP账号和网络环境
3. **数据安全**：测试数据不要提交到Git，使用.gitignore排除
4. **合规优先**：Phase 6的合规性验证是强制项，必须100%通过 ⭐
5. **Contract-First**：所有API修改必须先定义schemas，后实现逻辑
6. **测试环境**：建议在开发环境完成所有测试，再部署到云端
