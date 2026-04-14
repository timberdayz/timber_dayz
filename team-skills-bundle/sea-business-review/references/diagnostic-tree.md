# Diagnostic Tree

## Case 1: GMV 下滑

- 如果 `traffic` 下滑：
  - 优先判断流量获取问题
- 如果 `traffic` 稳定但 `conversion_rate` 下滑：
  - 优先判断页面、价格、评价、信任问题
- 如果 `traffic` 和 `conversion_rate` 稳定但 `avg_order_value` 下滑：
  - 优先判断低价单、促销结构、套装结构问题

## Case 2: GMV 增长但利润不增

- 检查 `profit` / `estimated_gross_profit`
- 若利润不增或下降：
  - 优先判断成本、费用、低质量订单结构
- 不允许直接把原因归结为“投放问题”，除非有单独成本证据

## Case 3: 达成率落后时间进度

- 检查 `monthly_achievement_rate` 与 `time_gap`
- 若 `time_gap < 0`：
  - 说明当前落后进度
- 再回到 `traffic / conversion_rate / avg_order_value` 找主因

## Case 4: 库存风险高

- 若 `inventory_backlog_60d_value` 或 `inventory_backlog_90d_value` 高：
  - 先识别清理优先 SKU
  - 再判断是否影响现金流和新品节奏

## 禁止跳步

- 不允许跳过 GMV 拆解直接给动作
- 不允许跳过利润判断直接说“经营改善”
- 不允许跳过库存检查就说“只要继续冲销量”
