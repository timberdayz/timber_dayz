# 店铺自动同步功能实现报告

**版本**: v4.19.0  
**日期**: 2026-01-27  
**状态**: ✅ 已完成

---

## 📋 概述

实现了 `platform_accounts` 到 `dim_shops` 的自动同步机制，确保数据仓库维度表的完整性，解决目标管理创建分解时外键约束失败的问题。

---

## 🎯 实现的功能

### 1. 创建共享同步服务

**文件**: `backend/services/shop_sync_service.py`

- 函数: `sync_platform_account_to_dim_shop()`
- 功能:
  - 自动创建/更新 `dim_shops` 记录
  - 确保平台 (`dim_platforms`) 存在
  - 同步店铺信息（名称、区域、货币等）
  - 支持创建和更新操作

### 2. 账号管理接口集成

**文件**: `backend/routers/account_management.py`

在以下接口中集成了自动同步：

- ✅ `POST /api/accounts` - 创建账号时自动同步
- ✅ `PUT /api/accounts/{account_id}` - 更新账号时自动同步
- ✅ `POST /api/accounts/batch` - 批量创建时自动同步
- ✅ `POST /api/accounts/import-from-local` - 导入时自动同步

### 3. 目标管理接口集成

**文件**: `backend/routers/target_management.py`

- ✅ `POST /api/targets/{target_id}/breakdown` - 创建分解时，如果店铺不存在，自动同步

---

## 🔄 同步逻辑

### 数据映射关系

```
platform_accounts (业务配置)          dim_shops (数据仓库维度)
┌─────────────────────────┐         ┌──────────────────────┐
│ platform                 │ ──────>│ platform_code (PK)  │
│ shop_id / account_id     │ ──────>│ shop_id (PK)        │
│ store_name               │ ──────>│ shop_name           │
│ shop_region              │ ──────>│ region               │
│ currency                 │ ──────>│ currency             │
└─────────────────────────┘         └──────────────────────┘
```

### 同步规则

1. **shop_id 确定**:
   - 优先使用 `platform_accounts.shop_id`
   - 如果为空，使用 `platform_accounts.account_id`

2. **平台创建**:
   - 如果 `dim_platforms` 中不存在，自动创建
   - 平台名称映射：`miaoshou` → `妙手ERP`, `shopee` → `Shopee` 等

3. **店铺创建/更新**:
   - 如果 `dim_shops` 中不存在，创建新记录
   - 如果存在，更新店铺信息（名称、区域、货币）

---

## 🧪 测试

### 测试脚本

**文件**: `scripts/test_shop_sync.py`

测试场景：
1. ✅ 创建账号时自动同步到 dim_shops
2. ✅ 更新账号时自动更新 dim_shops
3. ✅ 没有 shop_id 的账号跳过同步

### 运行测试

```bash
# 确保数据库运行
python scripts/test_shop_sync.py
```

---

## 📝 使用说明

### 1. 账号管理页面

用户在账号管理页面创建/更新账号时，系统会自动：
- 同步店铺信息到 `dim_shops`
- 确保平台记录存在
- 更新店铺的描述性信息

### 2. 目标管理页面

用户在目标管理页面创建目标分解时：
- 如果店铺在 `dim_shops` 中不存在
- 系统会自动从 `platform_accounts` 同步
- 然后创建目标分解

---

## ⚠️ 注意事项

1. **错误处理**: 同步失败不会影响主流程（账号创建/更新）
2. **日志记录**: 所有同步操作都会记录日志
3. **事务管理**: 同步操作在独立事务中执行，失败时回滚

---

## 🔍 验证方法

### 1. 验证账号创建同步

```python
# 1. 在账号管理页面创建账号（设置 shop_id）
# 2. 查询 dim_shops 表
SELECT * FROM dim_shops WHERE shop_id = 'your_shop_id';
```

### 2. 验证目标管理同步

```python
# 1. 在目标管理页面创建目标分解
# 2. 检查是否自动创建了店铺记录
SELECT * FROM dim_shops WHERE platform_code = 'shopee' AND shop_id = 'your_shop_id';
```

---

## ✅ 完成状态

- [x] 创建共享同步服务函数
- [x] 账号管理接口集成
- [x] 目标管理接口集成
- [x] 错误处理和日志记录
- [x] 测试脚本编写

---

## 🚀 下一步

1. **生产环境测试**: 在云端部署后验证功能
2. **性能优化**: 如果同步操作频繁，考虑批量同步
3. **数据清理**: 清理 `dim_shops` 表中的非店铺ID记录

---

## 📚 相关文件

- `backend/services/shop_sync_service.py` - 同步服务
- `backend/routers/account_management.py` - 账号管理接口
- `backend/routers/target_management.py` - 目标管理接口
- `scripts/test_shop_sync.py` - 测试脚本
