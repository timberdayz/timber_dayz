# 日期组件设计与开发指南

版本: v1.0
更新日期: 2026-04-02
适用范围:
- 采集组件中的日期控件开发
- 现有日期组件故障排查与重构
- 新平台日期控件建模
- Shopee 同平台不同页面或不同变体版本日期控件适配

---

## 1. 目标

这份文档用于沉淀一条高效、可复用的日期组件开发方法，避免后续工作继续陷入以下低效模式:

- 先录制动作，再从录制结果硬凑代码
- 在不了解控件真实结构时提前设计复杂兜底
- 把点击成功误判为日期已应用
- 把 popup 内部文本误判为页面最终成功信号
- 在按日、按周、按月之间混用同一套错误假设

核心原则只有一句:

`先基于证据建模控件状态，再写实现；不要基于想象为控件设计层级。`

---

## 2. 这次 Shopee 经验的关键结论

Shopee 商品概述页日期控件的稳定落地，证明了以下几点:

1. 快捷日期、按日、按周、按月应视为同一日期组件下的不同模式，而不是四段彼此独立的录制脚本。
2. 日期组件的核心不是“能点通”，而是“能判断当前状态、能推进到目标状态、能确认页面真的接受了目标状态”。
3. `pwcli/pwcap` 取证远比预设组件层级更可靠。真实页面结构必须以证据为准。
4. 按月这次最大的收获是: 真实控件是“年份切换 + 月份格子”，不是我们一开始假设的 `decade -> year -> month` 三层。
5. 最终成功信号不是 popup 内部的选中样式，而是页面外部 summary 的变化，例如 `按月 2026.03 (GMT+08)`。

---

## 3. 日期组件必须怎样分层

任何平台的日期组件，优先拆成以下能力层:

### 3.1 打开层

职责:
- 找到日期触发器
- 打开日期面板
- 确认面板真的已出现

推荐方法:
- `detect_date_picker_trigger()`
- `open_date_picker()`
- `wait_date_picker_open()`

### 3.2 模式层

职责:
- 判断当前是快捷、按日、按周还是按月
- 切换到目标模式
- 确认模式切换真的发生

推荐方法:
- `detect_current_date_mode()`
- `ensure_date_mode(mode)`
- `wait_date_mode_applied(mode)`

### 3.3 选择层

职责:
- 在目标模式下选择目标值
- 推进 popup 内部状态

推荐方法:
- `select_date_preset(preset)`
- `select_single_day(date)`
- `select_week_range(start_date, end_date)`
- `select_month_value(year, month)`

### 3.4 确认层

职责:
- 以页面最终业务信号确认日期已应用
- 避免“面板里看起来点了”却页面未生效

推荐方法:
- `detect_current_date_summary()`
- `parse_date_summary(summary)`
- `wait_date_selection_applied(target)`

---

## 4. 不同模式应该怎样建模

### 4.1 快捷日期

适合建模为枚举:

- `today_realtime`
- `yesterday`
- `last_7_days`
- `last_30_days`

要求:
- 优先点击明确的快捷项
- 成功标准不是按钮高亮，而是 summary 更新

### 4.2 按日

适合建模为单个日期值:

- `daily(date)`

要求:
- 先切到目标年月
- 再点目标日
- 最终通过 summary 或页面刷新结果确认

### 4.3 按周

适合建模为区间:

- `weekly(start_date, end_date)`

要求:
- 优先确认控件周选择逻辑是真正的“起止区间”还是“点某一天代表整周”
- 成功标准要能识别 summary 中的区间文本

### 4.4 按月

适合建模为年月:

- `monthly(year, month)`

要求:
- 先确认控件到底是:
  - 年份切换 + 月份格子
  - decade + year + month
  - 下拉年份 + 月份格子
  - 输入框 + 面板混合
- 不允许在未取证前直接假设控件层级

---

## 5. 先取证，再写代码

开发任何新日期控件前，至少收集这 5 份证据:

1. 初始状态
2. 面板打开后状态
3. 模式切换后状态
4. 值选择后状态
5. 页面最终 summary

推荐最小证据问题集:

1. 当前日期触发器长什么样
2. 面板打开后顶部 header 显示什么
3. 左右箭头切的到底是日、月、年还是年份段
4. 值是一次点击完成，还是需要二次确认
5. 页面外部哪个 summary 才是最终成功信号

如果这 5 个问题没回答清楚，不要开始写正式组件。

---

## 6. 这次最重要的反模式

### 6.1 不要提前发明层级

错误做法:
- “这看起来像先 decade 再 year 再 month”

正确做法:
- 先用 `pwcli/pwcap` 看真实页面到底怎么变化

### 6.2 不要把兜底变成主路径

错误做法:
- 点不到明确按钮就盲点 header 边缘
- 点最左 child、最右 child 试试看

正确做法:
- 主路径只允许明确 selector 或明确文本
- 找不到明确按钮时应失败并要求补证据

### 6.3 不要把 popup 内部状态当最终成功

错误做法:
- popup 里月份被点亮就当成功

正确做法:
- 只把页面 summary、页面数据刷新、或明确业务标签变化当作最终成功

### 6.4 不要让“点击成功”替代“状态成功”

错误做法:
- click 没报错就继续下一步

正确做法:
- 每一步都要有 `pre-check -> action -> post-check`

---

## 7. 通用设计模板

推荐所有日期组件都采用类似结构:

```python
async def ensure_date_selection(page, target):
    current = await detect_current_date_summary(page)
    if summary_matches_target(current, target):
        return

    await open_date_picker(page)
    await ensure_date_mode(page, target.mode)
    await navigate_to_target(page, target)
    await pick_target_value(page, target)

    if not await wait_date_selection_applied(page, target):
        raise RuntimeError("date selection did not apply")
```

其中:

- `summary_matches_target()` 是第一优先级
- `navigate_to_target()` 只做导航，不做最终成功判定
- `pick_target_value()` 只做选择动作
- `wait_date_selection_applied()` 只看页面最终信号

---

## 8. summary 解析应统一语义模型

后续所有平台建议统一把 summary 解析成语义对象，而不是直接做字符串包含。

推荐统一模型:

- `{"mode": "preset", "value": "last_7_days"}`
- `{"mode": "daily", "date": "2026-03-09"}`
- `{"mode": "weekly", "start_date": "2026-03-09", "end_date": "2026-03-15"}`
- `{"mode": "monthly", "year": 2026, "month": 3}`

这样带来的好处:

- 预检查可以判断“当前是否已经是目标状态”
- 确认逻辑可复用
- 不同平台只需要改 summary 解析器，不需要重写整个日期组件

---

## 9. Shopee 本次经验对后续工作的直接指导

### 9.1 对 Shopee 其他业务分析页

优先假设:
- 日期组件大概率同源
- 但不能默认完全一致

建议:
- 先复用当前建模骨架
- 再用证据确认以下差异:
  - 触发器文本是否一致
  - 按月 header 是否仍然是单一年份
  - summary 格式是否一致
  - 是否存在页面特有的确认动作

### 9.2 对其他平台

可直接复用的不是 selector，而是方法论:

- 统一取证
- 统一分层
- 统一目标语义模型
- 统一 summary 成功判定优先级

不要复用的内容:

- Shopee 的月份文本
- Shopee 的 header selector
- Shopee 的 summary 文本格式

---

## 10. 日期组件开发检查表

开始前:

- [ ] 是否已收集 5 份最小证据
- [ ] 是否已确认控件真实层级
- [ ] 是否已确认页面最终 summary 信号

实现时:

- [ ] 是否拆分为打开、模式、选择、确认四层
- [ ] 是否每个动作都有 post-check
- [ ] 是否避免了盲点坐标/边缘点击作为主路径

完成前:

- [ ] 是否能识别“当前已经是目标日期”
- [ ] 是否能区分“点到了”和“已应用”
- [ ] 是否能把 summary 解析成统一语义对象
- [ ] 是否已通过组件级测试
- [ ] 是否已通过真实页面复核

可直接复制的模板:
- 通用版:
  `docs/templates/DATE_COMPONENT_CHECKLIST_TEMPLATE.md`
- Shopee 专用版:
  `docs/templates/SHOPEE_DATE_COMPONENT_CHECKLIST_TEMPLATE.md`

选择建议:
- 做新平台或未知控件时，先用通用版
- 做 Shopee 业务分析页、Shopee 变体页面或 Shopee 老版本兼容时，优先用 Shopee 专用版

---

## 11. 一句话总结

高效开发日期组件的关键，不是增加更多兜底，而是尽快确认三件事:

1. 控件真实层级是什么
2. 当前目标值的最小导航单位是什么
3. 页面最终用什么业务信号承认这次选择已经生效

只要这三件事清楚，日期组件通常都能快速稳定落地。
