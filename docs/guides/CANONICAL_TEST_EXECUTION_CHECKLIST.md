# Canonical 组件测试执行清单

本文档用于指导当前阶段如何开始使用、测试、优化 canonical 采集组件。

目标不是重新录制脚本，而是：
- 只围绕 canonical 组件测试
- 只围绕 canonical 组件修复
- 逐个平台、逐个数据域推进到可用

## 使用原则

- 只测试 `modules/platforms/<platform>/components/` 下的 canonical 组件
- 不再把旧录制脚本、历史别名、临时脚本作为默认维护对象
- 一个组件测试失败，只修改对应 canonical 文件
- 通过后再进入下一个组件，不并行扩大范围

## 当前建议顺序

### 第一优先级：Shopee

先测这条主链路：
- `shopee/login`
- `shopee/products_export`

然后按顺序扩展：
- `shopee/services_export`
- `shopee/analytics_export`
- `shopee/orders_export`
- `shopee/finance_export`

原因：
- Shopee 当前 canonical 收口最完整
- `products_export`、`services_export`、`analytics_export` 都已经做过多轮契约和链路修复
- 适合作为正式优化的第一批平台

### 第二优先级：TikTok

先测这条主链路：
- `tiktok/login`
- `tiktok/shop_switch`
- `tiktok/export`

重点关注：
- `service-analytics` 下的禁用态是否真的是无数据
- 切换“聊天详情”后导出按钮是否稳定出现
- 二次确认按钮是否仍存在作用域误判

### 第三优先级：妙手

先测这条主链路：
- `miaoshou/login`
- `miaoshou/export`

重点关注：
- dropdown 是否稳定展开
- dialog / iframe 是否存在真实页面差异
- 导出确认按钮是否还需要额外收口

## 每个组件的测试步骤

1. 确认当前测试对象是 canonical 组件
2. 在组件版本管理页里执行测试
3. 记录失败位置：
   - 登录失败
   - 页面未就绪
   - 导出按钮未出现
   - 菜单未展开
   - 下载未触发
   - 文件未落盘
4. 只修改对应的 canonical 文件
5. 重新测试同一组件，直到通过
6. 通过后再推进下一个组件

## 推荐的实际执行批次

### 批次 1：先打通最短可用链路

- Shopee: `login + products_export`
- TikTok: `login + shop_switch + export`
- Miaoshou: `login + export`

目的：
- 先让三平台都具备一条可工作的 canonical 主链路

### 批次 2：补关键高风险导出

- Shopee: `services_export`
- Shopee: `analytics_export`

目的：
- 解决高风险任务型导出场景

### 批次 3：补次级数据域

- Shopee: `orders_export`
- Shopee: `finance_export`
- 其他平台后续按需要扩展

## 当前不建议直接投用的对象

以下内容不应作为当前默认优化对象：
- 非 canonical 内部实现
- 旧录制草稿
- 历史测试文件
- `*_config.py`
- 平台旧别名入口

## 判定“可以开始用”的标准

满足以下条件即可进入实际使用/继续优化阶段：
- 该组件属于 canonical 组件
- 组件版本管理页可稳定识别
- 对应最小链路已能测试
- 失败时你知道应该修改哪个唯一文件

换句话说：
- 现在已经可以开始用 canonical 组件做优化和测试
- 但仍建议按本清单逐步推进，而不是全量同时上线
