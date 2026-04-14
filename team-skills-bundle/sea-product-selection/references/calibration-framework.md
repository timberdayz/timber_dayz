# Calibration Framework

本文件定义如何把 V0 阈值校准成公司标准。

## Core Rule

V0 阈值是当前执行标准。  
校准只能让标准更贴近公司历史数据，不能让 agent 跳过标准。

## Required Historical Samples

至少收集以下样本：

- 成功精品
- 普通可做品
- 失败测试品
- 高搜索低转化品
- 高销量低利润品
- 滞销库存品
- TikTok 内容强但 Shopee 搜索弱的品
- Shopee 搜索强但 TikTok 内容弱的品

## Calibration Fields

每个历史样本记录：

- 产品
- 国家
- 平台
- 类目
- 价格带
- 搜索量
- 销量
- 搜索销售比
- 竞品数量
- 头部评价数
- 转化率
- 贡献利润率
- 内容表现力评分
- 差异化评分
- 供应链风险
- 最终结果

## Calibration Output

每次校准必须输出：

- 哪些阈值保持不变
- 哪些阈值上调
- 哪些阈值下调
- 哪些类目需要独立阈值
- 哪些平台需要独立阈值
- 哪些指标仍标记为 `needs-calibration`

## Agent Rule

如果没有历史校准数据：

- 使用 `threshold-standards.md` 的 V0 标准
- 标记 `needs-calibration`
- 不得自创阈值

如果有已校准数据：

- 优先使用 `calibrated` 阈值
- 输出引用的样本范围
- 说明该阈值适用的平台、国家、类目和价格带
