# await 语法错误修复报告

**日期**: 2026-01-03  
**问题**: `'await' outside async function` 错误  
**状态**: ✅ 已修复

---

## 问题描述

在测试任务恢复机制时，发现 Celery 任务提交失败，错误信息：

```
'await' outside async function (data_sync_tasks.py, line 146)
```

---

## 问题分析

### 根本原因

在 `backend/tasks/data_sync_tasks.py` 中，有多个地方在同步函数中使用了 `await`：

1. **第 127 行**：在 `_async_task()` 函数的 `finally` 块中，使用了 `asyncio.run()`，但缩进错误
2. **第 148 行**：在 `sync_single_file_task()` 的 `except` 块中，使用了 `await`
3. **第 458 行**：在 `_async_task()` 函数的 `finally` 块中，使用了 `asyncio.run()`，但缩进错误
4. **第 477 行**：在 `sync_batch_task()` 的 `except` 块中，使用了 `await`

### 代码结构

- `sync_single_file_task()` 和 `sync_batch_task()` 是**同步函数**（Celery 任务函数）
- `_async_task()` 是**异步函数**（内部异步逻辑）
- 在同步函数中不能直接使用 `await`，需要使用 `asyncio.run()`
- 在异步函数内部可以直接使用 `await`

---

## 修复方案

### 修复位置 1: `_async_task()` 函数的 `finally` 块

**问题**：在异步函数的 `finally` 块中，应该使用 `await`，而不是 `asyncio.run()`

**修复前**：
```python
finally:
    if user_id:
        try:
            quota_service = get_user_task_quota_service()
            # ❌ 错误：在异步函数中使用 asyncio.run()，且缩进错误
        asyncio.run(quota_service.decrement_user_task_count(user_id))
        except Exception as quota_error:
            ...
```

**修复后**：
```python
finally:
    if user_id:
        try:
            quota_service = get_user_task_quota_service()
            # ✅ 正确：在异步函数内部，可以直接使用 await
            await quota_service.decrement_user_task_count(user_id)
        except Exception as quota_error:
            ...
```

### 修复位置 2: `sync_single_file_task()` 和 `sync_batch_task()` 的 `except` 块

**问题**：在同步函数的 `except` 块中，不能直接使用 `await`

**修复前**：
```python
except Exception as exc:
    if user_id:
        try:
            quota_service = get_user_task_quota_service()
            # ❌ 错误：在同步函数中使用 await
            await quota_service.decrement_user_task_count(user_id)
        except Exception as quota_error:
            ...
```

**修复后**：
```python
except Exception as exc:
    if user_id:
        try:
            quota_service = get_user_task_quota_service()
            # ✅ 正确：在同步函数中使用 asyncio.run() 执行异步代码
            asyncio.run(quota_service.decrement_user_task_count(user_id))
        except Exception as quota_error:
            ...
```

---

## 修复验证

✅ **代码导入测试通过**

```bash
python -c "from backend.tasks.data_sync_tasks import sync_single_file_task; print('[OK] Import successful')"
# 输出: [OK] Import successful
```

---

## 相关文件

- `backend/tasks/data_sync_tasks.py` - 已修复
- `scripts/test_task_recovery.py` - 任务恢复测试脚本

---

## 总结

✅ **问题已解决**

1. ✅ 修复了 `_async_task()` 函数中 `finally` 块的 `await` 使用（应该使用 `await`，不是 `asyncio.run()`）
2. ✅ 修复了同步函数中 `except` 块的 `await` 使用（应该使用 `asyncio.run()`，不是 `await`）
3. ✅ 修复了缩进错误
4. ✅ 代码通过导入测试

**下一步**：
- 等待后端服务重启后，继续测试任务恢复机制
- 继续完成其他测试工作

