# Playwright 使用规范 - 快速参考

**创建时间**: 2025-12-21  
**目的**: 避免 subprocess 多次实现和移除的问题，遵循 Playwright 官方建议

---

## 🎯 核心原则

### 1. API 选择（必须遵守）

| 场景 | 使用 API | 示例代码位置 |
|------|---------|------------|
| **FastAPI 路由** | `async_playwright` | `backend/routers/component_versions.py` |
| **批量采集任务** | `async_playwright` | `modules/apps/collection_center/executor_v2.py` |
| **独立命令行脚本** | `async_playwright` + `asyncio.run()` | `tools/test_component.py` |
| **组件录制（subprocess）** | `sync_playwright` | `backend/routers/component_recorder.py` |

### 2. 执行方式选择

| 场景 | 执行方式 | 原因 |
|------|---------|------|
| **FastAPI 中的测试** | `async_playwright` + `asyncio.create_task()` | 符合官方建议，代码简洁 |
| **批量采集** | `async_playwright` + `asyncio.gather()` | 支持并发，性能最优 |
| **独立脚本** | `async_playwright` + `asyncio.run()` | 统一异步，避免混乱 |
| **录制工具** | `sync_playwright` + subprocess | 需要独立进程，避免阻塞 |

---

## ❌ 禁止的模式

### 1. 在异步框架中使用 sync_playwright + threading

```python
# ❌ 错误：已废弃
def run_test_in_thread():
    with sync_playwright() as p:  # 会导致事件循环冲突
        browser = p.chromium.launch()
        # ...

thread = threading.Thread(target=run_test_in_thread)
thread.start()
```

**问题**：
- `RuntimeError: Event loop is running`
- 需要复杂的跨线程通信
- 代码复杂，性能差

### 2. 在异步框架中使用 subprocess 运行测试

```python
# ❌ 错误：已废弃
result = subprocess.run([
    sys.executable, 'tools/run_component_test.py', config_path, result_path
])
```

**问题**：
- 无法实时传递进度回调
- 用户体验差（"盲测"）
- 不符合 Playwright 官方建议

---

## ✅ 推荐的模式

### 1. FastAPI 路由中的组件测试

```python
# ✅ 正确：当前实现
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

### 2. 批量采集（并发执行）

```python
# ✅ 正确：当前实现
async def execute_parallel_domains():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        
        # 并发执行多个数据域
        tasks = [
            collect_domain(domain, browser)
            for domain in domains
        ]
        results = await asyncio.gather(*tasks)
```

### 3. 命令行工具

```python
# ✅ 正确：当前实现
async def main():
    tester = ComponentTester(...)
    result = await tester.test_component(component_name)
    # ...

if __name__ == '__main__':
    asyncio.run(main())
```

---

## 📋 决策检查清单

在实现新的 Playwright 相关功能前，必须检查：

- [ ] **是否在异步框架（FastAPI）中使用？**
  - ✅ 是 → 使用 `async_playwright`
  - ❌ 否 → 可以使用 `sync_playwright`

- [ ] **是否需要实时进度反馈？**
  - ✅ 是 → 使用 `async_playwright` + 异步回调
  - ❌ 否 → 可以使用 subprocess（但需评估是否必要）

- [ ] **是否需要并发执行？**
  - ✅ 是 → 使用 `async_playwright` + `asyncio.gather()`
  - ❌ 否 → 可以使用 `sync_playwright`（独立脚本）

- [ ] **是否遵循 Playwright 官方建议？**
  - ✅ 是 → 继续实现
  - ❌ 否 → 重新评估方案

---

## 📚 相关文档

- **详细规范**: [proposal.md](./proposal.md#playwright-使用规范2025-12-21-新增)
- **规格定义**: [specs/data-collection/spec.md](./specs/data-collection/spec.md)
- **开发规范**: [.cursorrules](../../../.cursorrules)
- **Playwright 官方文档**: https://playwright.dev/python/docs/intro

---

## 🔄 历史变更记录

- **2025-12-21**: 将组件测试从 `sync_playwright + threading` 改为 `async_playwright`
- **2025-12-21**: 移除 `subprocess` 方式运行测试（保留用于录制工具）
- **2025-12-21**: 统一使用 `async_playwright` 在异步框架中
- **2025-12-21**: 添加本规范文档，避免后续重复实现
- **2025-12-21**: 修复 Windows 事件循环策略问题
  - **问题**: `NotImplementedError` 在 `asyncio.base_events._make_subprocess_transport`
  - **原因**: Windows 默认使用 `ProactorEventLoop`，Playwright 需要 `SelectorEventLoop`
  - **修复**: 在应用启动前设置 `asyncio.WindowsSelectorEventLoopPolicy()`
  - **影响文件**: `backend/main.py`、`tools/test_component.py`、`tools/run_component_test.py`

---

## ⚠️ 历史教训

### 问题0：Windows 事件循环策略（2025-12-21）

**问题**：
- `NotImplementedError` 在 `asyncio.base_events._make_subprocess_transport`
- 发生在调用 `async_playwright()` 时

**原因**：
- Windows 上 Python 3.8+ 默认使用 `ProactorEventLoop`
- Playwright 内部创建 subprocess 时，`ProactorEventLoop` 的 `_make_subprocess_transport` 抛出 `NotImplementedError`

**修复**：
```python
# 在导入其他模块之前设置事件循环策略
if sys.platform == 'win32':
    import asyncio
    if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

**教训**：
- ⚠️ **Windows 兼容性**：在 Windows 上使用 Playwright 时，必须设置正确的事件循环策略
- ⚠️ **时机很重要**：必须在导入其他模块之前设置，否则无效
- ⚠️ **所有入口点**：需要在所有可能运行 Playwright 的入口点设置（main.py、命令行工具等）

### 问题1：subprocess 多次实现和移除

**原因**：
- 最初使用 subprocess 是为了隔离 Playwright 事件循环
- 但 subprocess 无法实时传递进度回调
- 改为 threading + sync_playwright，但仍有事件循环冲突
- 最终改为 async_playwright，问题彻底解决

**教训**：
- ⚠️ **不要为了隔离而隔离**：如果框架本身支持异步，应该直接使用异步
- ⚠️ **遵循官方建议**：Playwright 官方明确建议在异步框架中使用 `async_playwright`
- ⚠️ **避免过度设计**：简单的异步方案往往比复杂的线程/进程方案更好

### 问题2：事件循环冲突

**原因**：
- `sync_playwright()` 内部会创建新的事件循环
- 在已有事件循环的线程中调用会导致冲突

**教训**：
- ⚠️ **理解 API 设计**：`sync_playwright` 和 `async_playwright` 的设计目的不同
- ⚠️ **选择正确的 API**：根据使用场景选择，不要混用

---

**记住**：在异步框架中，始终使用 `async_playwright`！

