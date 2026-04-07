# 前端时间维度切换指南

**创建时间**: 2025-01-16  
**状态**: 📋 使用指南  
**目的**: 指导前端开发者如何正确使用时间维度参数，确保后端自动选择最优查询方式

---

## 📋 概述

前端在调用C类数据API时，只需要传递正确的时间维度参数（`granularity`、`start_date`、`end_date`），后端会自动选择最优查询方式（物化视图或实时计算）。前端无需关心查询方式，统一API接口。

---

## 🎯 核心原则

### 1. 前端只需传递参数，无需关心查询方式

**前端职责**：
- 传递正确的时间维度参数（`granularity`、`start_date`、`end_date`）
- 传递筛选参数（`platform_code`、`shop_id`等）
- 处理API响应数据

**后端职责**：
- 根据参数自动选择最优查询方式（物化视图或实时计算）
- 返回统一格式的响应数据

### 2. 时间维度参数规范

**标准粒度**：
- `daily` - 日度数据
- `weekly` - 周度数据
- `monthly` - 月度数据

**日期格式**：
- `start_date` / `end_date` - ISO 8601格式（YYYY-MM-DD）
- 例如：`"2025-01-01"`

---

## 📝 API调用示例

### 1. 健康度评分查询

**API**: `/api/store-analytics/health-scores`

**前端调用示例**：
```javascript
// 日度数据查询（最近30天）
const params = {
  start_date: '2025-01-01',
  end_date: '2025-01-31',
  granularity: 'daily',
  platform_code: 'shopee',
  shop_id: 'shop001',
  page: 1,
  page_size: 20
}

const data = await api.get('/store-analytics/health-scores', { params })
```

**后端自动选择**：
- 如果时间范围在2年内 + 标准粒度 + 小规模筛选 → 物化视图查询（<100ms）
- 否则 → 实时计算查询（1-3s）

### 2. 店铺排名查询

**API**: `/api/dashboard/business-overview/shop-racing`

**前端调用示例**：
```javascript
// 月度数据查询
const params = {
  granularity: 'monthly',
  date: '2025-01-15',  // 具体日期，后端会自动计算月份范围
  platforms: 'shopee,lazada',
  group_by: 'shop'
}

const data = await api.get('/dashboard/business-overview/shop-racing', { params })
```

**后端自动选择**：
- 根据时间范围和筛选条件自动选择最优查询方式

### 3. 达成率计算

**API**: `/api/target-management/{target_id}/calculate`

**前端调用示例**：
```javascript
// POST请求，计算目标达成情况
const result = await api.post(`/target-management/${targetId}/calculate`)
```

**后端自动选择**：
- 使用CClassDataService查询销售数据
- 根据时间范围自动选择最优查询方式

---

## 🔄 时间维度切换场景

### 场景1：标准粒度切换（日→周→月）

**前端实现**：
```javascript
// Vue组件示例
const granularityOptions = [
  { label: '日度', value: 'daily' },
  { label: '周度', value: 'weekly' },
  { label: '月度', value: 'monthly' }
]

const selectedGranularity = ref('daily')

// 切换粒度时，重新查询数据
watch(selectedGranularity, async (newGranularity) => {
  await loadData({
    granularity: newGranularity,
    start_date: startDate.value,
    end_date: endDate.value
  })
})
```

**后端处理**：
- 自动识别粒度类型（daily/weekly/monthly）
- 如果是标准粒度 + 2年内 → 物化视图查询
- 否则 → 实时计算查询

### 场景2：自定义时间范围

**前端实现**：
```javascript
// 用户选择自定义时间范围
const customDateRange = {
  start_date: '2024-06-01',  // 6个月前
  end_date: '2025-01-31'
}

await loadData({
  granularity: 'daily',
  start_date: customDateRange.start_date,
  end_date: customDateRange.end_date
})
```

**后端处理**：
- 检测到时间范围超出2年 → 自动使用实时计算
- 前端无需关心查询方式

### 场景3：多年对比查询

**前端实现**：
```javascript
// 对比今年和去年的数据
const thisYear = {
  start_date: '2025-01-01',
  end_date: '2025-01-31',
  granularity: 'monthly'
}

const lastYear = {
  start_date: '2024-01-01',
  end_date: '2024-01-31',
  granularity: 'monthly'
}

// 分别查询两个时间段的数据
const [thisYearData, lastYearData] = await Promise.all([
  api.get('/store-analytics/health-scores', { params: thisYear }),
  api.get('/store-analytics/health-scores', { params: lastYear })
])
```

**后端处理**：
- 今年数据（2年内）→ 可能使用物化视图查询
- 去年数据（2年内）→ 可能使用物化视图查询
- 更早的数据（>2年）→ 自动使用实时计算
- 前端无需关心查询方式

---

## ⚡ 性能优化建议

### 1. 优先使用标准粒度

**推荐**：
```javascript
// ✅ 推荐：使用标准粒度（daily/weekly/monthly）
granularity: 'daily'
```

**不推荐**：
```javascript
// ❌ 不推荐：使用非标准粒度（会导致实时计算）
granularity: 'custom'
```

### 2. 合理设置时间范围

**推荐**：
```javascript
// ✅ 推荐：查询最近30天（在2年内，可能使用物化视图）
start_date: '2025-01-01',
end_date: '2025-01-31'
```

**注意**：
```javascript
// ⚠️ 注意：查询3年前的数据（超出2年，自动使用实时计算）
start_date: '2022-01-01',
end_date: '2022-01-31'
```

### 3. 控制筛选规模

**推荐**：
```javascript
// ✅ 推荐：小规模筛选（≤10店铺、≤5账号、≤3平台）
platform_code: 'shopee',
shop_id: 'shop001,shop002,shop003'  // 3个店铺
```

**注意**：
```javascript
// ⚠️ 注意：大规模筛选（>10店铺，自动使用实时计算）
shop_id: 'shop001,shop002,...,shop015'  // 15个店铺
```

---

## 🧪 测试验证

### 测试场景1：标准粒度切换

**测试步骤**：
1. 前端切换粒度（daily → weekly → monthly）
2. 观察API响应时间
3. 验证数据正确性

**预期结果**：
- 2年内的标准粒度查询：响应时间 < 100ms（物化视图）
- 超出2年或自定义范围：响应时间 1-3s（实时计算）
- 数据格式统一，前端无需特殊处理

### 测试场景2：自定义时间范围

**测试步骤**：
1. 前端选择自定义时间范围（如6个月前）
2. 调用API查询数据
3. 验证数据正确性

**预期结果**：
- 后端自动使用实时计算
- 数据正确返回
- 前端无需关心查询方式

### 测试场景3：多年对比

**测试步骤**：
1. 前端同时查询多个时间段的数据
2. 对比数据正确性
3. 验证响应时间

**预期结果**：
- 2年内的数据：可能使用物化视图（快速）
- 2年以上的数据：自动使用实时计算（较慢但准确）
- 前端统一处理响应数据

---

## 📚 相关文档

- [C类数据查询策略实现指南](C_CLASS_DATA_QUERY_STRATEGY_GUIDE.md) - 后端查询策略详解
- [API契约开发指南](API_CONTRACTS.md) - API响应格式和调用规范
- [数据分类传输规范指南](DATA_CLASSIFICATION_API_GUIDE.md) - C类数据API规范

---

## ✅ 最佳实践总结

1. **使用标准粒度**：优先使用daily/weekly/monthly，避免自定义粒度
2. **合理设置时间范围**：2年内的数据查询性能最佳
3. **控制筛选规模**：小规模筛选（≤10店铺、≤5账号、≤3平台）性能最佳
4. **统一API接口**：前端无需关心查询方式，统一处理响应数据
5. **错误处理**：使用统一的错误处理工具（`errorHandler.js`）
6. **数据格式化**：使用统一的数据格式化工具（`dataFormatter.js`）

---

**最后更新**: 2025-01-16  
**维护**: AI Agent Team  
**状态**: 📋 使用指南，前端开发者参考

