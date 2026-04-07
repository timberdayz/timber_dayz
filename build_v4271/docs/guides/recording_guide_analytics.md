# 📊 客流表现录制开发快速指南

> 文档索引（推荐入口）: docs/INDEX.md

## 🎯 开发目标

基于已完成的"商品表现"组件化录制模板，快速开发"客流表现"录制脚本。

## 🚀 快速开始（最简路径）

### 1. 配置文件编辑

**打开配置文件**：

```bash
# 方法1：菜单快捷键
运行系统 → 数据采集中心 → 客流数据采集 → 按 'c'

# 方法2：直接编辑
编辑文件：modules/platforms/shopee/components/analytics_config.py
```

**确认深链接**：

```python
# 验证实际客流表现页面 URL，如需要则更新
TRAFFIC_OVERVIEW_PATH: Final[str] = "/datacenter/traffic/overview"
```

### 2. 选择器配置

**导出按钮选择器**（按优先级排序）：

```python
EXPORT_BUTTON_SELECTORS: Final[List[str]] = [
    'button:has-text("导出数据")',
    'button:has-text("导出")',
    '[data-testid="export-button"]',
    '.export-btn',
    'button[class*="export"]'
]
```

**下载按钮选择器**：

```python
DOWNLOAD_BUTTON_SELECTORS: Final[List[str]] = [
    'button:has-text("下载")',
    'a:has-text("下载")',
    '[data-testid="download-button"]',
    '.download-btn'
]
```

**数据就绪探针**：

```python
DATA_READY_PROBES: Final[List[str]] = [
    '.data-table tbody tr',
    '[data-testid="data-row"]',
    '.traffic-data-row'
]
```

### 3. 组件化验证

**运行组件化路径**：

```bash
运行系统 → 数据采集中心 → 客流数据采集 → 1. 组件化优先导出
```

**观察执行日志**：

- `📍 步骤3: 执行导航组件...`
- `📍 导航结果: success=true, url=客流表现页面`
- `📍 步骤4: 执行日期选择组件...`
- `📍 日期选择结果: success=true`

## 🔧 常见问题排查

### 导航失败

**症状**：`📍 导航结果: success=false`
**解决**：

1. 检查 `TRAFFIC_OVERVIEW_PATH` 是否正确
2. 确认账号有访问权限
3. 验证 shop_id 是否匹配

### 导出按钮找不到

**症状**：点击导出按钮失败
**解决**：

1. 更新 `EXPORT_BUTTON_SELECTORS` 列表
2. 使用浏览器开发者工具检查实际选择器
3. 添加更通用的选择器表达式

### 下载未触发

**症状**：点击下载但文件未生成
**解决**：

1. 检查 `DOWNLOAD_BUTTON_SELECTORS`
2. 确认页面数据已加载完成
3. 验证 `DATA_READY_PROBES` 探针

## 📋 开发检查清单

### 配置阶段

- [ ] 确认深链接 `TRAFFIC_OVERVIEW_PATH`
- [ ] 更新导出按钮选择器
- [ ] 更新下载按钮选择器
- [ ] 配置数据就绪探针

### 测试阶段

- [ ] 组件化路径导航成功
- [ ] 日期选择组件正常
- [ ] 导出按钮点击成功
- [ ] 下载文件生成正常

### 生产阶段

- [ ] 生成录制脚本模板
- [ ] 跨账号测试验证
- [ ] 添加错误处理
- [ ] 文档更新完成

## 🎨 选择器编写技巧

### 文本匹配

```python
'button:has-text("导出数据")'  # 精确匹配
'button:has-text("导出")'      # 部分匹配
```

### 属性匹配

```python
'[data-testid="export-button"]'  # 测试ID
'button[class*="export"]'        # 类名包含
'button[aria-label*="导出"]'     # 无障碍标签
```

### 层级匹配

```python
'.toolbar button:has-text("导出")'     # 工具栏中的导出按钮
'div.actions >> button.primary'       # 操作区域的主按钮
```

### 通用兜底

```python
'button, a, [role="button"]'  # 所有可点击元素
':has-text("导出"):visible'   # 包含"导出"的可见元素
```

## 🚀 高级功能

### 自动重新生成报告

```python
# 在 config/simple_config.yaml 中配置
platforms:
  shopee:
    export:
      auto_regenerate: true  # 启用自动重新生成
```

### 网络抓包诊断

```python
# 录制时自动保存网络快照
# 输出文件：temp/recordings/network_snapshots/
```

### 多账号适配

```python
# 配置文件支持多账号共享
# 深链接自动适配不同 shop_id
```

## 📞 技术支持

**遇到问题时**：

1. 检查配置文件语法
2. 查看组件化执行日志
3. 使用浏览器开发者工具验证选择器
4. 参考"商品表现"成功案例

**联系方式**：

- 开发文档：`docs/` 目录
- 配置示例：`modules/platforms/shopee/components/products_config.py`
- 技术架构：`.cursorrules` 文件

---

> **提示**：本指南基于 v3.2.1 配置注册中心架构，确保系统版本匹配。
