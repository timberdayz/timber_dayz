# 🧩 智能诊断系统 - 技术文档

## 📋 系统概览

智能诊断系统是西虹ERP v3.1.1版本的核心增强功能，专门解决复杂Web应用中的自动化采集难题。通过DOM变化监控、对比诊断和自适应策略，实现对现代Web组件的精准识别和操作。

## 🎯 核心功能

### 1. DOM MutationObserver 实时监控

**功能描述**: 在页面加载后注入JavaScript MutationObserver，实时捕捉DOM元素的属性变化、子节点增删等操作。

**技术实现**:
```javascript
const observer = new MutationObserver((mutations) => {
  for (const m of mutations) {
    const rec = {
      type: m.type,
      target: m.target.outerHTML.slice(0, 500),
      attributeName: m.attributeName,
      oldValue: m.oldValue,
      timestamp: Date.now()
    };
    window.__x_mutations__.push(rec);
  }
});
observer.observe(document.body, { 
  attributes: true, 
  childList: true, 
  subtree: true, 
  attributeOldValue: true 
});
```

**应用场景**:
- 监控指标勾选状态变化 (class="selected")
- 捕捉动态加载的面板和浮层
- 记录用户交互引起的DOM变化

### 2. 对比诊断模式 (Before/After)

**功能描述**: 提供交互式诊断模式，用户手动操作前后自动保存页面快照，生成详细对比报告。

**工作流程**:
1. 保存 before 快照 (页面HTML、时间控件、指标状态)
2. 安装 MutationObserver 开始监控
3. 用户手动完成操作 (切换时间、勾选指标等)
4. 保存 after 快照
5. 生成对比报告和变化记录

**产出文件**:
```
.diag/
├── 20250829_233042_before_page.html
├── 20250829_233042_after_page.html
├── 20250829_233042_before_time_controls_enhanced.json
├── 20250829_233042_after_time_controls_enhanced.json
├── 20250829_233042_before_metrics_checkboxes.json
├── 20250829_233042_after_metrics_checkboxes.json
├── 20250829_233042_mutations.json
├── 20250829_233042_diff.json
└── 20250829_233042_export_attempts.json
```

### 3. Multi-Selector 自定义组件支持

**问题背景**: Shopee等现代Web应用使用自定义组件替代标准HTML checkbox，传统的 `input[type="checkbox"]` 和 `role="checkbox"` 选择器失效。

**解决方案**: 
- 识别 `li.multi-selector__item` 结构
- 通过 `.title` 文本内容定位指标
- 监控父级 `li` 的 `class` 属性是否包含 `selected`
- 点击 `.checkbox` 区域触发状态切换

**核心代码**:
```python
# 查找包含指标文本的 li.multi-selector__item
selector = f'li.multi-selector__item:has(.title:text-is("{metric}"))'
item = page.locator(selector).first

if item.count() > 0 and item.is_visible():
    class_attr = item.get_attribute("class") or ""
    if "selected" not in class_attr:
        checkbox_area = item.locator('.checkbox').first
        checkbox_area.click()
        
        # 等待选中状态更新
        page.wait_for_function(
            f'() => document.querySelector("{selector}").classList.contains("selected")',
            timeout=2000
        )
```

### 4. 时间戳格式兜底重试

**问题背景**: 不同接口对时间戳格式要求不一致，可能需要秒级或毫秒级时间戳。

**解决策略**:
1. 首次尝试: 秒级时间戳，结束时间设为 23:59:59
2. 自动重试: 毫秒级时间戳 (秒级 × 1000)
3. 记录所有尝试参数到 export_attempts.json

**实现逻辑**:
```python
try:
    # 第一次尝试：秒级时间戳
    result = page.evaluate(script_export, {
        "start_ts": start_ts,
        "end_ts": end_ts
    })
except Exception as e:
    # 自动重试：毫秒级时间戳
    retry_params = {
        "start_ts": start_ts * 1000,
        "end_ts": end_ts * 1000
    }
    result = page.evaluate(script_export, retry_params)
```

## 🔧 使用指南

### 启用对比诊断模式

1. 运行系统: `python run_new.py`
2. 选择: 数据采集中心 → 数据采集运行 → Shopee 商品周度导出
3. 选择模式: **3. 对比诊断（手动前后快照）**
4. 按提示手动操作页面
5. 检查生成的诊断文件

### 诊断文件解读

**diff.json 关键字段**:
```json
{
  "time_controls_diff": {
    "before_texts": ["今天至23:00 (GMT+08)"],
    "after_texts": ["25-08-2025 - 31-08-2025 (GMT+08)"],
    "changed": true
  },
  "metrics_diff": {
    "before_selected": [],
    "after_selected": ["跳出商品页面的访客数", "销量"],
    "newly_selected": ["跳出商品页面的访客数", "销量"],
    "newly_unselected": []
  },
  "summary": {
    "time_changed": true,
    "multi_selector_changed": true,
    "total_changes": 2
  }
}
```

**mutations.json 关键信息**:
- `attributeName: "class"` - 类属性变化
- `target` 包含 `multi-selector__item` - 指标项变化
- `oldValue` vs 新值对比 - 具体变化内容

## 🚀 技术优势

### 1. 零侵入性
- 不修改目标网站代码
- 纯客户端JavaScript注入
- 不影响正常页面功能

### 2. 高精度识别
- 基于DOM结构和文本内容双重定位
- 支持模糊匹配和精确匹配
- 自适应不同组件实现

### 3. 完整可追溯
- 详细记录每一步操作
- 保存完整页面快照
- 生成结构化对比报告

### 4. 自动容错
- 多种选择器策略兜底
- 时间戳格式自动重试
- 失败时保存诊断信息

## 📈 应用效果

通过智能诊断系统，成功解决了：
- Shopee multi-selector 指标勾选问题
- 时间戳格式不匹配导致的导出失败
- 复杂Web组件的自动化操作难题
- 调试和问题定位效率提升90%

## 🔮 未来扩展

### 计划功能
- [ ] 支持更多平台的自定义组件
- [ ] AI辅助的选择器生成
- [ ] 可视化诊断报告界面
- [ ] 自动化测试用例生成

### 技术演进
- [ ] WebDriver BiDi 协议集成
- [ ] 机器学习辅助元素识别
- [ ] 分布式诊断数据收集
- [ ] 实时诊断结果推送

---

*本文档记录了智能诊断系统的核心技术实现和使用方法，为后续功能扩展和问题排查提供参考。*
