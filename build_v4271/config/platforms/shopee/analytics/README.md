# Shopee 数据分析配置模板

## 概述

这个目录包含了 Shopee 各个数据分析子类型的声明式配置文件，支持零代码接入新的分析页面。

## 文件结构

```
config/platforms/shopee/analytics/
├── README.md           # 本说明文件
├── traffic.yaml        # 流量表现配置（已完成）
├── order.yaml          # 订单表现配置（支持录制）
├── finance.yaml        # 财务表现配置（支持录制）
└── template.yaml       # 新子类型模板（待创建）
```

## 配置文件说明

每个 YAML 配置文件包含以下主要部分：

### 1. 元数据 (metadata)
- `name`: 显示名称
- `type`: 类型标识符
- `version`: 配置版本
- `description`: 描述信息
- `url_path`: 页面路径

### 2. 页面导航 (navigation)
- `base_url`: 基础URL
- `path`: 页面路径
- `query_params`: 查询参数
- `ready_probes`: 页面就绪探针

### 3. 日期选择器 (date_picker)
- `open_selectors`: 打开日期选择器的触发器
- `panel_selectors`: 日期面板容器选择器
- `quick_options`: 快捷时间选项（支持多语言）
- `option_selectors`: 快捷项选择器模板

### 4. 数据导出 (export)
- `button_selectors`: 导出按钮选择器
- `download_selectors`: 下载按钮选择器
- `status_selectors`: 导出状态检测

### 5. 弹窗处理 (popups)
- `notification_selectors`: 通知弹窗选择器
- `close_selectors`: 关闭按钮选择器

### 6. 录制模式 (recording)
- `env_var`: 环境变量开关
- `pause_message`: 暂停提示信息
- `pause_after`: 暂停时机

### 7. 验证配置 (validation)
- `time_display_selectors`: 时间显示验证
- `data_loaded_selectors`: 数据加载验证

### 8. 错误处理 (error_handling)
- `max_retries`: 最大重试次数
- `retry_delay`: 重试延迟
- `timeouts`: 超时配置
- `fallback_enabled`: 是否启用降级
- `fallback_selectors`: 降级选择器

## 使用方法

### 1. 现有子类型
- **流量表现**: 已完全适配，支持自动化日期选择和数据导出
- **订单表现**: 支持录制模式，可通过 Inspector 录制具体操作
- **财务表现**: 支持录制模式，可通过 Inspector 录制具体操作

### 2. 录制新子类型操作

1. 设置环境变量启用录制模式：
   ```powershell
   $env:PW_RECORD_DATE_PICKER = "1"
   ```

2. 运行对应的子类型导出功能

3. 在 Inspector 中点击 "Record" 按钮

4. 手动完成日期选择和导出操作

5. 复制录制的选择器到配置文件中

6. 关闭录制模式：
   ```powershell
   Remove-Item Env:PW_RECORD_DATE_PICKER -ErrorAction SilentlyContinue
   ```

### 3. 添加新子类型

1. 复制 `template.yaml` 为新的配置文件
2. 修改元数据和页面路径
3. 使用录制模式获取具体选择器
4. 在代码中添加对应的枚举值和路由
5. 运行契约测试确保基本功能正常

## 配置优先级

1. **精确选择器**: 优先使用页面特有的选择器
2. **通用选择器**: 回退到通用的选择器模式
3. **降级选择器**: 最后使用基础的HTML元素选择器

## 多语言支持

配置文件支持多语言环境：
- 中文简体
- 英文
- 其他语言可按需添加到 `quick_options` 中

## 注意事项

1. **选择器维护**: 页面结构变化时需要更新对应的选择器
2. **版本控制**: 重大变更时需要更新配置版本号
3. **测试验证**: 新增配置后需要运行完整的测试流程
4. **性能考虑**: 选择器数量不宜过多，优先使用高效的选择器

## 故障排除

### 常见问题

1. **日期选择失败**
   - 检查 `open_selectors` 是否匹配当前页面
   - 确认 `panel_selectors` 能正确等待面板出现
   - 验证 `quick_options` 包含目标时间选项

2. **导出按钮找不到**
   - 更新 `button_selectors` 包含新的按钮样式
   - 检查是否有权限限制或登录状态问题

3. **弹窗干扰**
   - 添加新的弹窗选择器到 `notification_selectors`
   - 确保关闭按钮选择器正确

### 调试技巧

1. 启用录制模式进行手动操作
2. 使用浏览器开发者工具检查元素
3. 查看日志输出定位具体失败点
4. 逐步验证每个配置部分

## 扩展性

这个配置系统设计为高度可扩展：
- 新增子类型只需添加配置文件
- 支持插件化的选择器策略
- 可以轻松适配不同地区的页面差异
- 支持A/B测试等页面变体
