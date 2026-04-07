# Metabase Question API集成指南

## 概述

本文档说明如何使用Metabase Question API（方式2）替代Dashboard嵌入，实现前端完全控制UI设计，同时避免使用Metabase收费的Embedding功能。

## 架构设计

### 数据流

```
Metabase（免费版）
  ↓ 创建Question（查询）
  ↓ 保存Question ID
  ↓
后端代理API（可选，推荐）
  ↓ 调用Metabase REST API
  ↓ 获取Question结果
  ↓
前端Vue.js
  ↓ 调用后端API或直接调用Metabase API
  ↓ 获取JSON数据
  ↓ 使用ECharts/Chart.js自己渲染图表
```

## 配置步骤

### 1. Metabase中创建Question

1. 登录Metabase
2. 创建新的Question（查询）
   - 选择数据源（PostgreSQL）
   - 选择表（如`b_class.fact_raw_data_orders_daily`）
   - 使用拖拽式查询构建器创建查询
   - 保存Question，记录Question ID

**示例Question**：
- Question 1（ID: 1）：GMV趋势（折线图）
- Question 2（ID: 2）：订单数趋势（折线图）
- Question 3（ID: 3）：销售达成率趋势（折线图）
- Question 4（ID: 4）：店铺GMV对比（柱状图）
- Question 5（ID: 5）：平台对比（饼图）

### 2. 创建Metabase API密钥

1. 在Metabase中：Settings → Admin → API Keys
2. 创建新的API密钥
3. 复制API密钥
4. 配置到环境变量：`METABASE_API_KEY`

### 3. 后端代理API实现

#### 3.1 扩展Metabase代理API

```python
# backend/routers/metabase_proxy.py

@router.get("/question/{question_id}/query")
async def get_question_data(
    question_id: int,
    filters: Optional[Dict] = Query(None, description="筛选器JSON字符串"),
    db: Session = Depends(get_db)
):
    """
    获取Metabase Question的查询结果
    
    使用Metabase REST API（免费）
    API文档：https://www.metabase.com/docs/latest/api/card#execute-a-question-query
    """
    try:
        # 解析筛选器
        import json
        filter_dict = {}
        if filters:
            filter_dict = json.loads(filters)
        
        # 调用Metabase API
        metabase_url = os.getenv("METABASE_URL", "http://localhost:3000")
        api_key = os.getenv("METABASE_API_KEY")
        
        # 构建查询参数
        query_params = {
            "parameters": []
        }
        
        # 添加筛选器参数
        if "date_range" in filter_dict:
            query_params["parameters"].append({
                "type": "date/range",
                "value": filter_dict["date_range"]
            })
        if "platform" in filter_dict:
            query_params["parameters"].append({
                "type": "string/=",
                "value": filter_dict["platform"]
            })
        if "granularity" in filter_dict:
            query_params["parameters"].append({
                "type": "string/=",
                "value": filter_dict["granularity"]
            })
        
        # 调用Metabase API
        response = requests.post(
            f"{metabase_url}/api/card/{question_id}/query",
            headers={
                "X-Metabase-Session": api_key,  # 或使用JWT token
                "Content-Type": "application/json"
            },
            json=query_params,
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Metabase API调用失败: {response.text}"
            )
        
        data = response.json()
        
        # 转换数据格式（Metabase格式 → 前端友好格式）
        return {
            "success": True,
            "data": {
                "columns": data.get("data", {}).get("cols", []),
                "rows": data.get("data", {}).get("rows", []),
                "row_count": len(data.get("data", {}).get("rows", []))
            },
            "question_id": question_id
        }
        
    except Exception as e:
        logger.error(f"获取Metabase Question数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取Metabase Question数据失败: {str(e)}"
        )
```

### 4. 前端实现

#### 4.1 创建Metabase服务

```javascript
// frontend/src/services/metabase.js

import api from '@/api'

/**
 * 获取Metabase Question的查询结果
 * @param {number} questionId - Question ID
 * @param {object} filters - 筛选器参数
 * @returns {Promise<object>} 查询结果
 */
export async function getQuestionData(questionId, filters = {}) {
  try {
    const response = await api.get(`/api/metabase/question/${questionId}/query`, {
      params: {
        filters: JSON.stringify(filters)
      }
    })
    
    return response.data
  } catch (error) {
    console.error(`获取Question ${questionId}数据失败:`, error)
    throw error
  }
}
```

#### 4.2 在Vue组件中使用

```vue
<!-- frontend/src/views/Dashboard.vue -->
<template>
  <div class="dashboard">
    <!-- 自定义筛选器 -->
    <el-card class="filter-card">
      <el-date-picker v-model="dateRange" type="daterange" />
      <el-select v-model="platform" />
      <el-radio-group v-model="granularity">
        <el-radio-button label="daily">日度</el-radio-button>
        <el-radio-button label="weekly">周度</el-radio-button>
        <el-radio-button label="monthly">月度</el-radio-button>
      </el-radio-group>
    </el-card>

    <!-- 图表区域 -->
    <div class="chart-grid">
      <div ref="gmvChart" style="width: 100%; height: 400px;"></div>
      <div ref="orderChart" style="width: 100%; height: 400px;"></div>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { getQuestionData } from '@/services/metabase'

export default {
  data() {
    return {
      dateRange: null,
      platform: null,
      granularity: 'daily',
      charts: {}
    }
  },
  
  async mounted() {
    await this.loadCharts()
  },
  
  watch: {
    dateRange() {
      this.loadCharts()
    },
    platform() {
      this.loadCharts()
    },
    granularity() {
      this.loadCharts()
    }
  },
  
  methods: {
    async loadCharts() {
      const filters = {
        date_range: this.dateRange,
        platform: this.platform,
        granularity: this.granularity
      }
      
      // 加载GMV趋势（Question ID: 1）
      await this.loadGmvChart(filters)
      
      // 加载订单数趋势（Question ID: 2）
      await this.loadOrderChart(filters)
    },
    
    async loadGmvChart(filters) {
      try {
        const data = await getQuestionData(1, filters)
        
        // 初始化ECharts
        if (!this.charts.gmv) {
          this.charts.gmv = echarts.init(this.$refs.gmvChart)
        }
        
        // 渲染图表
        this.charts.gmv.setOption({
          title: { text: 'GMV趋势' },
          xAxis: {
            type: 'category',
            data: data.data.rows.map(r => r[0]) // 第一列是日期
          },
          yAxis: { type: 'value' },
          series: [{
            data: data.data.rows.map(r => r[1]), // 第二列是GMV
            type: 'line',
            smooth: true
          }]
        })
      } catch (error) {
        console.error('加载GMV图表失败:', error)
      }
    },
    
    async loadOrderChart(filters) {
      try {
        const data = await getQuestionData(2, filters)
        
        // 初始化ECharts
        if (!this.charts.order) {
          this.charts.order = echarts.init(this.$refs.orderChart)
        }
        
        // 渲染图表
        this.charts.order.setOption({
          title: { text: '订单数趋势' },
          xAxis: {
            type: 'category',
            data: data.data.rows.map(r => r[0])
          },
          yAxis: { type: 'value' },
          series: [{
            data: data.data.rows.map(r => r[1]),
            type: 'line',
            smooth: true
          }]
        })
      } catch (error) {
        console.error('加载订单图表失败:', error)
      }
    }
  },
  
  beforeUnmount() {
    // 销毁图表
    Object.values(this.charts).forEach(chart => {
      if (chart) {
        chart.dispose()
      }
    })
  }
}
</script>
```

## 优势

### 1. 避免收费功能
- ✅ 使用免费的REST API
- ✅ 不使用收费的Embedding功能

### 2. 完全控制UI
- ✅ 前端完全控制图表样式
- ✅ 可以自定义交互逻辑
- ✅ 可以使用任何图表库（ECharts、Chart.js等）

### 3. 灵活性高
- ✅ 可以根据业务需求自定义图表类型
- ✅ 可以组合多个Question的数据
- ✅ 可以实现复杂的交互逻辑

## 注意事项

### 1. API认证
- Metabase API可以使用Session Token或API Key
- 推荐使用API Key（更安全）

### 2. 性能优化
- 可以添加缓存（Redis）提升性能
- 可以批量获取多个Question的数据

### 3. 错误处理
- 需要处理Metabase服务不可用的情况
- 需要处理API调用失败的情况
- 需要提供降级策略（显示静态图表或错误提示）

## 参考文档

- [Metabase REST API文档](https://www.metabase.com/docs/latest/api)
- [Metabase Question API](https://www.metabase.com/docs/latest/api/card#execute-a-question-query)
- [ECharts文档](https://echarts.apache.org/zh/index.html)

