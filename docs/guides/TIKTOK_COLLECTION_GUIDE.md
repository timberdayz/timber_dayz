## TikTok 流量表现采集（组件化）技术说明

本说明覆盖 TikTok 卖家端“流量表现”数据采集在新架构下的实现要点与调试指引。

### 范围与页面
- 基础域名：https://seller.tiktokshopglobalselling.com
- 相关路径：
  - 流量表现：/compass/data-overview
  - 商品表现：/compass/product-analysis
  - 服务表现：/compass/service-analytics
- 登录入口必须使用账号配置的 login_url（如 https://seller.tiktokglobalshop.com）。

### 执行流程（深链接 → 时间 → 导出）
1) 选择账号 → 选择店铺/区域（shop_region）
2) 深链接导航到目标页面（自动拼接 shop_region）
3) 执行时间策略（日期控件）
4) 执行导出并保存到统一目录结构

### 日期控件“打开面板”策略（已实现）
- 多上下文：同时在主文档与所有 iframe 中尝试。
- 容器限定：优先定位 div.theme-arco-picker.theme-arco-picker-range。
- 点击优先级：suffix 图标 → svg → svg path → 第二/最后输入框 → 通用触发器 → role=button 兜底。
- 显式等待：点击后等待 .theme-arco-picker-dropdown/.eds-date-picker__dropdown 可见。
- 等待+重试：2.5 秒短轮询，间隔 200ms；输出 attempt# 和 ctx# 调试日志（仅控制台）。

### 当前时间策略（今日约定）
- 默认：昨天（T-1 ~ T-1）。
- 后续：扩展为任意起止日期；面板打开后进入“自定义”页签并选择起止日期。

### 调试日志解读
- [TiktokDatePicker] attempt#4 ctx#1 click '...'
- [TiktokDatePicker] clicked by role=button fallback
- [TiktokDatePicker] open panel failed after retries（重试结束仍未检测到面板）

### 下一步计划（明日）
- 面板内“自定义”页签稳定选择：
  - 识别左/右日历，处理跨月/跨年翻页。
  - 先选开始，再选结束；若结束 < 开始则自动交换。
  - 确认按钮可点击后再提交；必要时回退到输入框直接填充。
- 契约测试：最小用例覆盖“打开面板 + 选择昨天 + 确认”。

