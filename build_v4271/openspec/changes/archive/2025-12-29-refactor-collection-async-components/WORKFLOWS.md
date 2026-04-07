# 数据采集模块工作流程

本文档详细说明组件录制、组件测试和生产环境采集的完整流程，包括各个环节调用的工具。

---

## 流程图1：组件录制流程（Inspector模式）

### 流程概述

用户通过前端界面录制组件，系统使用Playwright Inspector API捕获操作，生成Python组件代码骨架。

### 详细步骤

```
1. 用户操作（前端）
   └─> ComponentRecorder.vue
       ├─> 选择平台（shopee/tiktok/miaoshou）
       ├─> 选择组件类型（login/navigation/export/date_picker）
       ├─> 选择测试账号
       └─> 点击"开始录制"按钮

2. 前端API调用
   └─> POST /collection/recorder/start
       └─> backend/routers/component_recorder.py
           ├─> 验证账号存在
           ├─> 创建RecorderSession
           └─> 启动子进程

3. 录制脚本执行
   └─> tools/launch_inspector_recorder.py
       └─> InspectorRecorder.record()
           ├─> 创建持久化浏览器上下文
           │   └─> PersistentBrowserManager
           ├─> 应用固定设备指纹
           │   └─> DeviceFingerprintManager
           ├─> 自动执行login组件（如果录制非login组件）
           │   └─> PythonComponentAdapter.login()
           ├─> 处理弹窗
           │   └─> UniversalPopupHandler
           ├─> 启动Trace录制
           │   └─> context.tracing.start()
           └─> 打开Playwright Inspector
               └─> page.pause()

4. 用户操作（浏览器）
   └─> 在浏览器中执行操作
       ├─> 系统捕获事件（click/fill/goto/wait）
       └─> 前端轮询 GET /collection/recorder/steps

5. 停止录制
   └─> 用户点击"停止录制"
       └─> POST /collection/recorder/stop
           ├─> 停止Trace录制
           ├─> 保存trace.zip文件
           └─> 解析Trace文件

6. Trace解析
   └─> backend/utils/trace_parser.py
       └─> TraceParser.parse()
           ├─> 提取操作事件
           ├─> 生成Python组件代码骨架
           └─> 返回给前端

7. 用户编辑
   └─> 在代码编辑器编辑Python代码
       ├─> 添加业务逻辑
       ├─> 添加弹窗处理
       └─> 添加等待和重试逻辑

8. 保存组件
   └─> POST /collection/recorder/save
       ├─> 保存Python文件
       │   └─> modules/platforms/{platform}/components/{name}.py
       └─> 创建ComponentVersion记录
```

### 关键工具说明

| 工具/模块 | 路径 | 功能 |
|-----------|------|------|
| 前端录制界面 | `frontend/src/views/ComponentRecorder.vue` | 用户录制界面 |
| 录制API | `backend/routers/component_recorder.py` | 录制API路由 |
| 录制脚本 | `tools/launch_inspector_recorder.py` | Inspector录制器 |
| Trace解析器 | `backend/utils/trace_parser.py` | Trace文件解析 |
| 持久化浏览器 | `PersistentBrowserManager` | 管理持久化上下文 |
| 设备指纹 | `DeviceFingerprintManager` | 固定设备指纹 |
| 弹窗处理 | `UniversalPopupHandler` | 自动处理弹窗 |

---

## 流程图2：组件测试流程

### 流程概述

用户测试Python组件，系统在独立进程中执行组件，记录测试结果并保存历史。

### 详细步骤

```
1. 用户操作（前端）
   └─> ComponentVersions.vue 或 ComponentRecorder.vue
       ├─> 选择Python组件
       └─> 点击"测试组件"按钮

2. 前端API调用
   └─> POST /collection/recorder/test
       └─> backend/routers/component_recorder.py
           └─> test_component()

3. 测试服务准备
   └─> backend/services/component_test_service.py
       └─> ComponentTestService.prepare_account_info()
           └─> EncryptionService.decrypt_password()
               └─> 解密账号密码

4. 启动测试进程
   └─> ComponentTestService.run_component_test_subprocess()
       └─> 启动子进程
           └─> tools/run_component_test.py
               └─> ComponentTester.test_component()

5. 组件加载
   └─> component_loader.load_python_component()
       ├─> 解析组件路径（如 shopee/products_export）
       └─> 从 modules/platforms/{platform}/components/{name}.py 加载

6. 创建适配器
   └─> PythonComponentAdapter
       ├─> 创建ExecutionContext
       └─> 初始化PlatformAdapter

7. 创建浏览器
   └─> async_playwright()
       ├─> 创建浏览器实例
       └─> 打开浏览器窗口（非headless模式）

8. 执行组件
   └─> 根据组件类型执行
       ├─> login → adapter.login(page)
       ├─> navigation → adapter.navigate(page, target_page)
       └─> export → adapter.export(page, data_domain)

9. 记录结果
   └─> 实时记录每个步骤
       ├─> 成功/失败状态
       ├─> 执行耗时
       └─> 错误信息（如果失败）

10. 保存截图
    └─> 失败时保存错误截图
        └─> temp/screenshots/

11. 验证成功条件
    └─> 检查success_criteria
        ├─> URL验证
        └─> 元素存在性验证

12. 生成测试结果
    └─> ComponentTestResult
        ├─> 总步骤数
        ├─> 成功/失败数
        ├─> 成功率
        └─> 步骤详情列表

13. 保存测试历史
    └─> ComponentTestHistory表
        ├─> 测试ID
        ├─> 组件名称
        ├─> 测试结果
        └─> 步骤详情（JSON）

14. 返回结果
    └─> 前端显示测试报告
        ├─> 测试概览卡片
        ├─> 步骤执行详情（Timeline视图）
        └─> 失败截图展示
```

### 关键工具说明

| 工具/模块 | 路径 | 功能 |
|-----------|------|------|
| 前端测试界面 | `frontend/src/views/ComponentVersions.vue` | 组件测试界面 |
| 测试API | `backend/routers/component_recorder.py` | 测试API路由 |
| 测试服务 | `backend/services/component_test_service.py` | 统一测试服务 |
| 测试脚本 | `tools/run_component_test.py` | 独立测试进程 |
| 组件适配器 | `PythonComponentAdapter` | Python组件适配层 |
| 组件加载器 | `component_loader.load_python_component()` | 加载Python组件 |

---

## 流程图3：生产环境采集流程（定时/手动触发）

### 流程概述

系统通过定时任务或手动触发执行数据采集，使用Python组件完成登录、导航、导出等操作。

### 详细步骤

```
1. 任务触发
   ├─> 定时触发：APScheduler到达Cron时间
   │   └─> CollectionScheduler._execute_scheduled_task(config_id)
   └─> 手动触发：前端/API调用
       └─> POST /collection/tasks
           └─> backend/routers/collection.py

2. 任务创建
   └─> 检查任务冲突
       ├─> 同一配置是否已有运行任务
       └─> 为每个账号创建CollectionTask记录
           └─> collection_tasks表

3. 后台任务启动
   └─> asyncio.create_task()
       └─> _execute_collection_task_background()
           └─> backend/routers/collection.py

4. 账号加载
   └─> AccountLoaderService.load_account()
       ├─> 从数据库加载账号信息
       └─> EncryptionService.decrypt_password()
           └─> 解密账号密码

5. 执行引擎初始化
   └─> CollectionExecutorV2
       ├─> 创建ComponentLoader
       └─> 创建UniversalPopupHandler

6. 浏览器创建
   └─> async_playwright()
       ├─> 创建浏览器实例
       └─> 创建浏览器上下文

7. 登录执行
   └─> executor.execute()
       └─> PythonComponentAdapter.login(page)
           └─> 执行登录组件
               └─> modules/platforms/{platform}/components/login.py

8. 并行数据域采集
   └─> executor.execute_parallel_domains()
       └─> asyncio.gather()
           ├─> 数据域1: orders
           ├─> 数据域2: products
           └─> 数据域3: services

9. 每个数据域执行流程
   └─> 并行执行
       ├─> 步骤1: 导航
       │   └─> PythonComponentAdapter.navigate(page, target_page)
       │       └─> modules/platforms/{platform}/components/navigation.py
       │
       ├─> 步骤2: 日期选择（如果需要）
       │   └─> PythonComponentAdapter.date_picker(page, option)
       │       └─> modules/platforms/{platform}/components/date_picker.py
       │
       ├─> 步骤3: 导出
       │   └─> PythonComponentAdapter.export(page, data_domain)
       │       └─> modules/platforms/{platform}/components/{data_domain}_export.py
       │
       ├─> 步骤4: 文件下载
       │   ├─> page.expect_download()（UI监听）
       │   └─> 文件系统兜底（扫描下载目录）
       │
       ├─> 步骤5: 文件重命名
       │   └─> build_filename()
       │       └─> 标准命名格式
       │
       └─> 步骤6: 文件注册
           └─> FileRegistrationService.register_file()
               └─> catalog_files表

10. 结果汇总
    └─> 汇总所有数据域结果
        ├─> completed_domains: 成功的数据域列表
        ├─> failed_domains: 失败的数据域列表（含错误信息）
        └─> 更新任务状态
            ├─> completed: 全部成功
            ├─> partial_success: 部分成功
            └─> failed: 全部失败

11. 进度更新
    └─> 前端轮询
        └─> GET /collection/tasks/{task_id}
            └─> 返回任务状态和进度
                ├─> 当前执行的数据域
                ├─> 已完成的数据域数
                └─> 采集的文件数

12. 前端显示
    └─> 显示采集进度和结果
        ├─> 任务状态
        ├─> 进度百分比
        ├─> 已完成的数据域
        └─> 采集的文件列表
```

### 关键工具说明

| 工具/模块 | 路径 | 功能 |
|-----------|------|------|
| 调度器 | `backend/services/collection_scheduler.py` | APScheduler定时任务 |
| 任务API | `backend/routers/collection.py` | 采集任务API |
| 执行引擎 | `modules/apps/collection_center/executor_v2.py` | 采集执行引擎 |
| 组件适配器 | `PythonComponentAdapter` | Python组件适配层 |
| 账号加载 | `AccountLoaderService` | 账号加载服务 |
| 文件注册 | `FileRegistrationService` | 文件注册服务 |
| 文件命名 | `build_filename()` | 统一文件命名 |

---

## 流程对比总结

| 流程 | 主要工具 | 执行环境 | 输出 |
|------|----------|----------|------|
| **组件录制** | InspectorRecorder, TraceParser | 子进程（subprocess） | Python组件代码骨架 |
| **组件测试** | ComponentTestService, PythonComponentAdapter | 子进程（subprocess） | ComponentTestResult |
| **生产采集** | CollectionExecutorV2, PythonComponentAdapter | 异步任务（asyncio.create_task） | CollectionResult + 文件 |

---

## 关键决策点

1. **录制模式**：仅使用Inspector模式，移除Codegen模式
2. **组件格式**：仅支持Python组件，移除YAML组件支持
3. **执行方式**：统一使用异步API（`async_playwright`）
4. **密码处理**：统一在适配层解密，组件无需关心加密逻辑
5. **文件处理**：UI监听 + 文件系统兜底的双重保障

