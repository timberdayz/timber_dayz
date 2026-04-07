# v4.11.2 A类数据权限修复

**日期**: 2025-11-15  
**问题**: A类数据配置页面在前端不可见  
**原因**: 权限配置缺失 + 菜单位置错误

## 🔍 问题分析

### 发现的问题

1. **权限缺失**:
   - `campaign:read` - 销售战役管理需要的权限
   - `target:read` - 目标管理需要的权限
   - `performance:read` - 绩效管理需要的权限

2. **菜单位置错误**:
   - `target-management` 在 `system` 组中，应该在 `sales-analytics` 组中

## ✅ 修复内容

### 1. 更新权限配置

**文件**: `frontend/src/stores/user.js`

**修复内容**:
- ✅ 添加 `campaign:read` 权限（销售战役管理）
- ✅ 添加 `target:read` 权限（目标管理）
- ✅ 添加 `performance:read` 权限（绩效管理）

**修改位置**:
- `login` 方法中的权限列表
- `initUserInfo` 方法中的默认权限列表

### 2. 更新菜单配置

**文件**: `frontend/src/config/menuGroups.js`

**修复内容**:
- ✅ 将 `target-management` 从 `system` 组移动到 `sales-analytics` 组
- ✅ 在 `sales-analytics` 组中添加注释标识A类数据

**修改前**:
```javascript
// sales-analytics 组
items: [
  '/sales-dashboard-v3',
  '/sales-campaign-management',
  '/customer-management',
  '/order-management'
]

// system 组
items: [
  '/user-management',
  '/role-management',
  '/permission-management',
  '/target-management',  // ❌ 错误位置
  '/system-settings',
  '/system-logs',
  '/personal-settings'
]
```

**修改后**:
```javascript
// sales-analytics 组
items: [
  '/sales-dashboard-v3',
  '/sales-campaign-management',  // A类数据
  '/target-management',           // A类数据 ✅ 已移动
  '/customer-management',
  '/order-management'
]

// system 组
items: [
  '/user-management',
  '/role-management',
  '/permission-management',
  '/system-settings',
  '/system-logs',
  '/personal-settings'
]
```

## 📋 A类数据页面配置总结

### 页面清单

1. **销售战役管理**
   - 路径: `/sales-campaign-management`
   - 菜单: `销售与分析 → 销售战役管理`
   - 权限: `campaign:read`
   - 角色: `['admin', 'manager', 'operator']`

2. **目标管理**
   - 路径: `/target-management`
   - 菜单: `销售与分析 → 目标管理` ✅ 已修复位置
   - 权限: `target:read`
   - 角色: `['admin', 'manager']`

3. **绩效权重配置**
   - 路径: `/hr-performance-management`
   - 菜单: `人力资源 → 绩效管理`
   - 权限: `performance:read`
   - 角色: `['admin', 'manager', 'operator']`

## 🔄 刷新前端

修复后需要：
1. **刷新浏览器页面**（清除缓存）
2. **重新登录**（重新加载权限）
3. **检查菜单**（确认A类数据页面可见）

## ✅ 验证步骤

1. 打开浏览器开发者工具（F12）
2. 检查控制台是否有权限拦截警告
3. 检查菜单中是否显示：
   - `销售与分析` → `销售战役管理`
   - `销售与分析` → `目标管理`
   - `人力资源` → `绩效管理`
4. 点击菜单项，确认可以正常访问页面

## 📝 注意事项

- 如果仍然看不到菜单，请清除浏览器缓存并重新登录
- 确保用户角色为 `admin`、`manager` 或 `operator`
- 权限检查在路由守卫中进行，缺少权限会自动跳转到业务概览页面

