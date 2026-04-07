# Change: 验证并完善数据采集-同步端到端管道

## Why

数据采集模块已完成架构重构（归档提案 `2025-12-19-refactor-collection-module`），基础设施已就绪（Phase 1-6完成），但生产环境部署前需要验证完整链路：

1. **录制工具待验证**：Phase 2.1代码已实现（2025-12-19），但实际录制功能未经用户手动测试验证
2. **组件YAML待更新**：模板组件使用占位符选择器，需要实际录制更新为真实选择器
3. **端到端流程未验证**：完整的"登录→下载→注册→映射→同步→定时刷新"链路未经实际测试
4. **定时同步配置待验证**：APScheduler定时任务和数据同步API集成需要验证
5. **云端部署兼容性待检查**：环境变量配置、无头浏览器模式、路径相对化需要预检查

**根本原因**：采集模块重构完成了架构和代码实现，但未完成实际平台录制和端到端集成测试，无法保证生产环境可用性。

## What Changes

### 1. 验证录制工具功能正确性（P0）
- 测试 `tools/record_component.py` 的3个核心功能：
  - 自动登录功能（加载并执行login.yaml）
  - Playwright Inspector捕获（完整记录用户操作）
  - YAML生成质量（正确的选择器和success_criteria）
- 修复发现的问题

### 2. 实际录制妙手ERP核心组件（P0）
- 录制 `login.yaml`（登录组件）
- 录制 `navigation.yaml`（导航组件）
- 录制 `orders_export.yaml`（订单导出）
- 录制 `products_export.yaml`（产品导出）
- 使用 `tools/test_component.py` 验证组件可执行

### 3. 端到端流程集成测试（P0）
- 创建测试采集配置（妙手ERP + orders域 + 昨天）
- 手动触发采集任务，验证：
  - 文件正确下载到 `data/raw/YYYY/`
  - 文件正确注册到 `catalog_files` 表
  - 元数据字段完整且正确
- 触发数据同步，验证：
  - 数据正确入库到事实表
  - 去重机制正常工作
  - 数据行数验证通过

### 4. 定时同步机制验证（P1）
- 验证 APScheduler 定时任务正常触发
- 验证数据同步API与定时任务集成
- 验证物化视图自动刷新机制

### 5. 云端部署预检查（P1）
- 创建环境变量配置清单（PROJECT_ROOT、DATA_DIR、DATABASE_URL等）
- 验证 Docker Compose 配置完整性
- 测试无头浏览器模式（PLAYWRIGHT_HEADLESS=true）
- 验证路径管理器环境变量支持

### 6. 合规性验证（P0）⭐
- 运行 `python scripts/verify_architecture_ssot.py`
- 运行 `python scripts/verify_contract_first.py`
- 运行 `python scripts/verify_api_contract_consistency.py`
- 修复发现的问题

## Impact

### 受影响的规格（Affected Specs）

- **data-collection** (MODIFIED) - 新增端到端验证requirement
- **data-sync** (MODIFIED) - 新增定时同步验证requirement

### 受影响的代码（Affected Code）

**可能需要修复的文件**：
- `tools/record_component.py` - 根据测试结果修复bug
- `config/collection_components/miaoshou/*.yaml` - 更新为实际录制的选择器
- `backend/services/collection_scheduler.py` - 验证定时任务配置
- `backend/routers/data_sync.py` - 验证API端点和response_model
- `backend/schemas/data_sync.py` - 验证Pydantic模型定义（Contract-First）

**测试验证文件**：
- `tests/e2e/test_complete_collection_to_sync.py` - 新增端到端测试

### 破坏性变更（Breaking Changes）

**无破坏性变更** - 本change为验证和修复，不改变现有API契约或数据模型。

## Non-Goals

- ❌ **不添加新平台支持**：仅验证现有平台（妙手ERP/Shopee/TikTok）
- ❌ **不重构现有架构**：架构已定型（组件驱动），仅验证和修复bug
- ❌ **不实现AI自修复**：高级功能（Phase 10）不在本次范围
- ❌ **不实现新的数据域**：仅验证现有6个数据域（orders/products/services/analytics/finance/inventory）
- ❌ **不修改Metabase配置**：数据看板API不在本次范围

## Playwright 使用规范（2025-12-21 新增）⭐⭐⭐

### 问题背景

在开发过程中，我们多次实现和移除了 subprocess 方式运行 Playwright，主要原因是对 Playwright 官方建议理解不清晰。为避免后续再次出现此类问题，特制定本规范。

### Playwright API 选择原则

#### 1. **async_playwright vs sync_playwright**

**官方建议**：
- ✅ **异步框架（FastAPI/Django Async/Tornado）**：**必须使用 `async_playwright`**
- ✅ **独立命令行脚本**：可以使用 `sync_playwright`
- ❌ **禁止**：在异步框架中使用 `sync_playwright`（会导致 `RuntimeError: Event loop is running`）

**决策表**：

| 场景 | 使用 API | 原因 |
|------|---------|------|
| FastAPI 路由中的组件测试 | `async_playwright` | 与 FastAPI 异步架构兼容 |
| 批量采集任务（executor_v2.py） | `async_playwright` | 支持并发，性能更好 |
| 组件录制工具（独立进程） | `sync_playwright` | 独立脚本，无事件循环 |
| 命令行测试工具 | `async_playwright` + `asyncio.run()` | 统一使用异步，避免混乱 |

#### 2. **执行方式选择：subprocess vs threading vs async**

**官方建议**：
- ✅ **异步框架中**：直接使用 `async_playwright` + `asyncio.create_task()`
- ⚠️ **独立脚本**：使用 `sync_playwright` + subprocess（如果需要隔离）
- ❌ **禁止**：在异步框架中使用 `sync_playwright` + threading（违反官方建议）

**决策表**：

| 场景 | 执行方式 | 代码位置 | 原因 |
|------|---------|---------|------|
| 组件测试（FastAPI） | `async_playwright` + `asyncio.create_task()` | `backend/routers/component_versions.py` | 符合官方建议，代码简洁 |
| 批量采集（FastAPI） | `async_playwright` + 异步函数 | `modules/apps/collection_center/executor_v2.py` | 支持并发，性能最优 |
| 组件录制（独立进程） | `sync_playwright` + subprocess | `backend/routers/component_recorder.py` | 需要独立进程，避免阻塞 |
| 命令行测试工具 | `async_playwright` + `asyncio.run()` | `tools/test_component.py` | 统一异步，避免混乱 |

### 禁止的模式

#### ❌ 禁止：在异步框架中使用 sync_playwright + threading

```python
# ❌ 错误示例（已废弃）
def run_test_in_thread():
    with sync_playwright() as p:  # 会导致事件循环冲突
        browser = p.chromium.launch()
        # ...

thread = threading.Thread(target=run_test_in_thread)
thread.start()
```

**问题**：
- `sync_playwright()` 内部会创建新的事件循环
- 如果当前线程已有事件循环，会导致 `RuntimeError: Event loop is running`
- 需要复杂的跨线程通信（`asyncio.run_coroutine_threadsafe`）
- 代码复杂，性能差

#### ❌ 禁止：在异步框架中使用 subprocess 运行测试

```python
# ❌ 错误示例（已废弃）
result = subprocess.run([
    sys.executable, 'tools/run_component_test.py', config_path, result_path
])
```

**问题**：
- 无法实时传递进度回调
- 只能等待完成后读取结果文件
- 用户体验差（"盲测"）
- 不符合 Playwright 官方建议

### 推荐的模式

#### ✅ 推荐：在异步框架中直接使用 async_playwright

```python
# ✅ 正确示例（当前实现）
async def test_component_version():
    async def async_progress_callback(event_type: str, data: dict):
        await websocket_service.send_progress(...)
    
    tester = ComponentTester(
        progress_callback=async_progress_callback  # 异步回调
    )
    
    # 直接异步调用
    result = await tester._test_with_browser(component, result)
    
    # 直接发送 WebSocket（无需跨线程）
    await websocket_service.send_complete(...)

# 启动后台任务
asyncio.create_task(test_component_version())
```

**优势**：
- ✅ 符合 Playwright 官方建议
- ✅ 代码简洁（减少约 150 行）
- ✅ 性能更好（无线程切换开销）
- ✅ 实时反馈更直接（无需跨线程通信）
- ✅ 无事件循环冲突

### 历史教训总结

#### 问题1：subprocess 多次实现和移除

**原因**：
- 最初使用 subprocess 是为了隔离 Playwright 事件循环
- 但 subprocess 无法实时传递进度回调
- 改为 threading + sync_playwright，但仍有事件循环冲突
- 最终改为 async_playwright，问题彻底解决

**教训**：
- ⚠️ **不要为了隔离而隔离**：如果框架本身支持异步，应该直接使用异步
- ⚠️ **遵循官方建议**：Playwright 官方明确建议在异步框架中使用 `async_playwright`
- ⚠️ **避免过度设计**：简单的异步方案往往比复杂的线程/进程方案更好

#### 问题2：事件循环冲突

**原因**：
- `sync_playwright()` 内部会创建新的事件循环
- 在已有事件循环的线程中调用会导致冲突

**教训**：
- ⚠️ **理解 API 设计**：`sync_playwright` 和 `async_playwright` 的设计目的不同
- ⚠️ **选择正确的 API**：根据使用场景选择，不要混用

### 验证检查清单

在实现新的 Playwright 相关功能前，必须检查：

- [ ] 是否在异步框架（FastAPI）中使用？
  - ✅ 是 → 使用 `async_playwright`
  - ❌ 否 → 可以使用 `sync_playwright`
- [ ] 是否需要实时进度反馈？
  - ✅ 是 → 使用 `async_playwright` + 异步回调
  - ❌ 否 → 可以使用 subprocess（但需评估是否必要）
- [ ] 是否需要并发执行？
  - ✅ 是 → 使用 `async_playwright` + `asyncio.gather()`
  - ❌ 否 → 可以使用 `sync_playwright`（独立脚本）
- [ ] 是否遵循 Playwright 官方建议？
  - ✅ 是 → 继续实现
  - ❌ 否 → 重新评估方案

### 相关文档

- [Playwright Python 官方文档](https://playwright.dev/python/docs/intro)
- [Playwright 异步 API 文档](https://playwright.dev/python/docs/api/class-asyncplaywright)
- [FastAPI 异步编程指南](https://fastapi.tiangolo.com/async/)

### 实施记录

- **2025-12-21**: 将组件测试从 `sync_playwright + threading` 改为 `async_playwright`
- **2025-12-21**: 移除 `subprocess` 方式运行测试（保留用于录制工具）
- **2025-12-21**: 统一使用 `async_playwright` 在异步框架中
- **2025-12-21**: 修复 Windows 事件循环策略问题（`NotImplementedError`）
  - 在 `backend/main.py`、`tools/test_component.py`、`tools/run_component_test.py` 中添加 `WindowsSelectorEventLoopPolicy`
  - 解决 Playwright 在 Windows 上使用 `ProactorEventLoop` 时的兼容性问题
- **2025-12-22**: 移除 WebSocket 实时同步，改用 HTTP 轮询
  - 创建 `GET /{version_id}/test/{test_id}/status` 端点
  - `run_component_test.py` 写入进度到 `_progress.json` 文件
  - 前端使用 `setInterval` 轮询进度
- **2025-12-22**: 修复步骤成功率计算问题
  - 在 `run_component_test.py` 中正确计算 `success_rate`
  - 在 `get_test_status` 端点中补充计算逻辑

## Inspector API 录制模式（2025-12-23 新增）⭐⭐⭐

### 问题背景

原有的 Codegen 录制模式存在以下问题：
1. **无持久化会话**：每次录制需要重新登录
2. **无固定指纹**：每次录制使用随机指纹，增加检测风险
3. **代码解析不稳定**：依赖正则表达式解析 Python 代码，易出错
4. **步骤提取不完整**：部分操作可能丢失

### 解决方案：Inspector API + Trace 录制

切换到 Inspector API 录制模式，使用 `page.pause()` 打开 Inspector 进行交互式录制，同时使用 Trace 录制捕获完整操作序列。

### 新增文件

| 文件 | 功能 |
|------|------|
| `backend/utils/trace_parser.py` | Trace 文件解析器，提取步骤 |
| `tools/launch_inspector_recorder.py` | Inspector API 录制脚本 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `backend/routers/component_recorder.py` | 新增 Inspector 模式支持，双模式切换 |

### 录制模式对比

| 特性 | Codegen 模式（旧） | Inspector 模式（新） |
|------|-------------------|---------------------|
| 持久化会话 | ❌ 不支持 | ✅ 使用 PersistentBrowserManager |
| 固定指纹 | ❌ 不支持 | ✅ 使用 DeviceFingerprintManager |
| 自动登录 | ❌ 需要手动 | ✅ 自动执行 login 组件 |
| 弹窗处理 | ❌ 需要手动 | ✅ 自动处理 |
| 步骤提取 | 代码解析（不稳定） | Trace 解析（结构化） |
| 调试能力 | 有限 | ✅ 完整 Trace 回放 |

### 配置切换

在 `backend/routers/component_recorder.py` 中：

```python
# v4.7.5: 录制模式配置
RECORDING_MODE = "inspector"  # "codegen" 或 "inspector"
```

### Trace 解析器设计

遵循 Playwright 官方 Trace 格式：

1. **输入**：Trace ZIP 文件（包含 `trace.trace` 事件流）
2. **解析**：提取 action 类型事件（click, fill, goto 等）
3. **转换**：将事件转换为组件步骤格式（YAML）
4. **输出**：结构化步骤列表

支持的操作类型：
- `click` → `click` 步骤
- `fill` / `type` → `fill` 步骤
- `goto` / `navigate` → `navigate` 步骤
- `waitForNavigation` / `waitForSelector` / `waitForTimeout` → `wait` 步骤
- `selectOption` → `select` 步骤
- `press` → `keyboard` 步骤
- `hover` → `hover` 步骤
- `scroll` → `scroll` 步骤

### 新录制流程

```
用户点击"开始录制"
  ↓
后端启动 subprocess（launch_inspector_recorder.py）
  ↓
使用 PersistentBrowserManager 创建持久化上下文
  ↓
应用固定指纹（DeviceFingerprintManager）
  ↓
如果是非 login 组件 → 自动执行登录组件
  ↓
处理弹窗（UniversalPopupHandler）
  ↓
启动 Trace 录制
  ↓
打开 Inspector（page.pause()）
  ↓
用户在浏览器中操作（Inspector 自动记录）
  ↓
用户关闭浏览器或点击 Resume
  ↓
停止 Trace 录制 → 保存 trace.zip
  ↓
解析 Trace → 提取步骤 → 保存 steps.json
  ↓
后端读取 steps.json → 返回步骤列表给前端
```

### 实施记录

- **2025-12-23**: 创建 `backend/utils/trace_parser.py` Trace 解析器
- **2025-12-23**: 创建 `tools/launch_inspector_recorder.py` Inspector 录制脚本
- **2025-12-23**: 修改 `backend/routers/component_recorder.py` 支持 Inspector 模式
- **2025-12-23**: 更新 RecorderSession 类支持新字段（recording_mode, steps_file, config_file, trace_file）
- **2025-12-23**: 新增 `_parse_inspector_output()` 解析 Inspector 模式输出
