# Canonical 组件优先测试清单

本文档用于给组件版本管理页里的实际测试提供一个最短执行顺序。

适用原则：
- 只测试 canonical 组件
- 只修改 canonical 组件
- 一次只推进一个组件，不扩大范围

## 批次 1：先打通三平台最短链路

| 优先级 | 平台 | 组件 | 用途 | 当前建议 |
|------|------|------|------|------|
| P0 | Shopee | `login` | 登录前置 | 先测 |
| P0 | Shopee | `products_export` | 首条主导出链路 | 先测 |
| P0 | TikTok | `login` | 登录前置 | 先测 |
| P0 | TikTok | `shop_switch` | 店铺/区域前置 | 先测 |
| P0 | TikTok | `export` | TikTok 统一导出入口 | 先测 |
| P0 | Miaoshou | `login` | 登录前置 | 先测 |
| P0 | Miaoshou | `export` | 妙手统一导出入口 | 先测 |

## 批次 2：补高风险导出

| 优先级 | 平台 | 组件 | 用途 | 当前建议 |
|------|------|------|------|------|
| P1 | Shopee | `services_export` | 任务型服务导出 | 第二批 |
| P1 | Shopee | `analytics_export` | 分析类导出 | 第二批 |

## 批次 3：补次级数据域

| 优先级 | 平台 | 组件 | 用途 | 当前建议 |
|------|------|------|------|------|
| P2 | Shopee | `orders_export` | 订单导出 | 第三批 |
| P2 | Shopee | `finance_export` | 财务导出 | 第三批 |
| P2 | Shopee | `navigation` | 页面导航前置 | 按需测 |
| P2 | Shopee | `date_picker` | 日期前置 | 按需测 |
| P2 | TikTok | `navigation` | 页面导航前置 | 按需测 |
| P2 | TikTok | `date_picker` | 日期前置 | 按需测 |
| P2 | Miaoshou | `navigation` | 页面导航前置 | 按需测 |
| P2 | Miaoshou | `date_picker` | 日期前置 | 按需测 |

## 组件版本管理页实际执行顺序

建议你在页面里按这个顺序点测：

1. `shopee/login`
2. `shopee/products_export`
3. `tiktok/login`
4. `tiktok/shop_switch`
5. `tiktok/export`
6. `miaoshou/login`
7. `miaoshou/export`
8. `shopee/services_export`
9. `shopee/analytics_export`
10. `shopee/orders_export`
11. `shopee/finance_export`

## 每测一个组件时只做这几件事

1. 看组件是否能进入主流程
2. 看页面是否真正到达目标状态
3. 看导出按钮/菜单/弹窗是否按预期出现
4. 看下载是否真正触发并落盘
5. 失败后只改当前 canonical 文件

## 当前不要作为默认测试对象的内容

- 非 canonical 别名组件
- 旧录制脚本
- `*_config.py`
- 平台内部辅助实现
- 历史测试文件

## 一句话使用建议

先按 `P0 -> P1 -> P2` 顺序推进。  
只要 `P0` 这一批能稳定测试，你就已经可以正式进入 canonical 组件优化阶段。
