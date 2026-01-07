# Dashboard Specification

## MODIFIED Requirements

### Requirement: Business Overview Dashboard with Metabase Question API
Business overview page SHALL use Metabase Question API to fetch data and render charts with ECharts.

#### Scenario: Load business overview page
- **WHEN** user navigates to `/business-overview`
- **THEN** Vue component SHALL:
  - Call Metabase Question API via backend proxy (`GET /api/metabase/question/{id}/query`)
  - Fetch data for each chart (GMV trend, order count, etc.)
  - Display filters (date range, platform, shop, granularity)
  - Show loading skeleton while data loads
  - Render charts using ECharts after data is loaded

#### Scenario: Render charts with ECharts
- **WHEN** `MetabaseChart.vue` component mounts
- **THEN** component SHALL:
  - Call backend API to get Question data: `GET /api/metabase/question/{question_id}/query?filters={filters}`
  - Receive JSON data from Metabase Question API
  - Initialize ECharts instance
  - Render chart with received data (line chart, bar chart, pie chart, etc.)
  - Apply filters from parent component as API parameters
  - Set chart height based on props (default: 400px)
  - Handle loading and error states

#### Scenario: Apply global filters
- **WHEN** user selects date range (2025-01-01 to 2025-01-31)
- **THEN** parent component SHALL:
  - Update filter state in Pinia store
  - Call Metabase Question API with new filter parameters
  - Reload all charts simultaneously with new data
  - Show loading indicator during reload

#### Scenario: Chart interaction
- **WHEN** user interacts with ECharts (zoom, tooltip, click, etc.)
- **THEN** ECharts SHALL:
  - Handle interaction natively (zoom, tooltip, drill-down, etc.)
  - Support custom event handlers for business logic
  - Update chart state based on user interaction

#### Scenario: Export chart data
- **WHEN** user clicks export button on chart
- **THEN** frontend SHALL:
  - Export chart as PNG/SVG (using ECharts export API)
  - Export data as CSV/Excel (using raw data from Metabase Question API)
  - Provide copy to clipboard functionality

#### Scenario: Granularity switching
- **WHEN** user switches granularity (daily/weekly/monthly) in frontend
- **THEN** frontend SHALL:
  - Pass `granularity` parameter to Metabase Question API
  - Call Question API with new granularity parameter
  - Update all charts with new data
  - Show loading indicator during update

### Requirement: Fallback to ECharts on Metabase Failure
Dashboard SHALL gracefully degrade to ECharts when Metabase is unavailable.

#### Scenario: Metabase health check failure
- **WHEN** backend detects Metabase is down (3 consecutive health check failures)
- **THEN** backend SHALL:
  - Set `metabase_available = false` flag in Redis
  - Return flag in API response

#### Scenario: Frontend fallback mode
- **WHEN** frontend receives `metabase_available = false`
- **THEN** Vue component SHALL:
  - Switch to fallback mode (use ECharts instead of iframe)
  - Display warning banner: "图表服务维护中，当前显示离线数据"
  - Fetch aggregated data from backend API (`GET /api/dashboard/kpis`)
  - Render charts using ECharts with cached data

#### Scenario: Auto-recovery from fallback mode
- **WHEN** in fallback mode
- **THEN** frontend SHALL:
  - Retry Metabase connection every 30 seconds
  - Check backend health endpoint (`GET /api/metabase/health`)
  - When Metabase recovers, reload page with success message
  - Clear warning banner

#### Scenario: Fallback data caching
- **WHEN** Metabase is available
- **THEN** frontend SHALL:
  - Cache last successful chart data in localStorage
  - Set cache TTL = 1 hour
  - Use cache if Metabase fails and backend data unavailable

---

## ADDED Requirements

### Requirement: MetabaseChart Vue Component
A reusable Vue 3 component SHALL be created for rendering Metabase Question data with ECharts.

#### Component API
```vue
<MetabaseChart
  :question-id="1"
  :filters="{ platform: 'shopee', date_range: '2025-01-01:2025-01-31', shop_id: 'shop001' }"
  :granularity="'daily'"
  :chart-type="'line'"
  :height="400"
  @loaded="onChartLoaded"
  @error="onChartError"
/>
```

#### Scenario: Component initialization
- **WHEN** `MetabaseChart` component is created
- **THEN** component SHALL:
  - Accept props: `questionId`, `filters`, `granularity`, `chartType`, `height`
  - Call backend API: `GET /api/metabase/question/{questionId}/query?filters={filters}`
  - Initialize ECharts instance with ref element
  - Render chart with received data
  - Show loading skeleton while data loads

#### Scenario: Filter update
- **WHEN** parent component updates `filters` or `granularity` prop
- **THEN** component SHALL:
  - Watch for filter and granularity changes
  - Call Metabase Question API with new filter parameters
  - Update chart data with new response
  - Re-render chart with new data
  - Emit `loading` event during update

#### Scenario: Error handling
- **WHEN** API call fails (timeout > 10s or 404/500 error)
- **THEN** component SHALL:
  - Emit `error` event with error details
  - Display error message: "图表加载失败，请刷新页面重试"
  - Provide retry button
  - Fallback to cached data if available

#### Scenario: Chart type support
- **WHEN** component receives `chartType` prop
- **THEN** component SHALL:
  - Support multiple chart types: `line`, `bar`, `pie`, `scatter`, etc.
  - Configure ECharts option based on chart type
  - Handle data format conversion for different chart types

### Requirement: Dashboard Filter Panel
Dashboard SHALL provide centralized filter panel for all charts.

#### Scenario: Date range filter
- **WHEN** user selects date range in filter panel
- **THEN** filter SHALL:
  - Use Element Plus DatePicker with range mode
  - Support shortcuts: "今天", "本周", "本月", "上月", "近30天", "近90天"
  - Validate end_date >= start_date
  - Default to "本月"
  - Emit `filter-change` event with ISO date strings

#### Scenario: Platform filter
- **WHEN** user selects platform(s)
- **THEN** filter SHALL:
  - Use Element Plus Select with multiple mode
  - Load platform options from `dim_platform` table
  - Support "全部平台" option (clears filter)
  - Emit `filter-change` event with platform_codes array

#### Scenario: Shop filter
- **WHEN** user selects shop(s)
- **THEN** filter SHALL:
  - Use cascading selector: Platform → Shop
  - Load shop options based on selected platform
  - Apply RLS filter (only show authorized shops)
  - Support "全部店铺" option
  - Emit `filter-change` event with shop_ids array

#### Scenario: Apply filters
- **WHEN** user clicks "应用" button
- **THEN** filter panel SHALL:
  - Validate all filters
  - Update Pinia store with new filter values (including granularity)
  - Emit `apply-filters` event to parent
  - Parent SHALL trigger API calls for ALL MetabaseChart components
  - All charts SHALL reload with new data

#### Scenario: Granularity switching
- **WHEN** user switches granularity (daily/weekly/monthly) in filter panel
- **THEN** filter panel SHALL:
  - Update granularity state in Pinia store
  - Emit `granularity-change` event
  - Parent SHALL update MetabaseChart component with new granularity
  - All charts SHALL call Metabase Question API with new granularity parameter
  - Charts SHALL update with new time-grouped data

#### Scenario: Reset filters
- **WHEN** user clicks "重置" button
- **THEN** filter panel SHALL:
  - Reset all filters to default values
  - Clear Pinia store filters
  - Trigger chart reload with default filters

### Requirement: Dashboard Layout Modes
Dashboard SHALL support multiple layout modes for different user preferences.

#### Scenario: Grid layout (default)
- **WHEN** user selects grid layout
- **THEN** dashboard SHALL:
  - Display charts in 2-column grid
  - Use CSS Grid for responsive layout
  - Chart order: Sales → Orders → Customers → Traffic → Inventory → Profit

#### Scenario: List layout
- **WHEN** user selects list layout
- **THEN** dashboard SHALL:
  - Display charts in single column
  - Full-width charts with more vertical space
  - Easier for scrolling on mobile

#### Scenario: Custom layout
- **WHEN** user drags and drops charts (Phase 4 feature)
- **THEN** dashboard SHALL:
  - Use vue-grid-layout for drag-and-drop
  - Save user layout preference to backend
  - Restore layout on next login

### Requirement: Real-Time Data Updates
Dashboard SHALL support real-time data refresh without full page reload.

#### Scenario: Auto-refresh data
- **WHEN** user enables auto-refresh toggle
- **THEN** dashboard SHALL:
  - Call Metabase Question API every 5 minutes
  - Invalidate Metabase query cache (if configured)
  - Reload all charts with fresh data
  - Show "最后更新: 2分钟前" timestamp

#### Scenario: Manual refresh
- **WHEN** user clicks refresh button
- **THEN** dashboard SHALL:
  - Call Metabase Question API immediately for all charts
  - Show loading indicator on all charts
  - Update timestamp when complete
  - Display success toast: "数据已更新"

#### Scenario: Refresh status indicator
- **WHEN** charts are refreshing
- **THEN** dashboard SHALL:
  - Display refresh indicator icon (spinning)
  - Show progress if multiple charts (e.g., "刷新中 2/5")
  - Disable refresh button during refresh
  - Enable button when complete

---

## REMOVED Requirements

### Requirement: ECharts for Chart Rendering
Dashboard SHALL use ECharts as primary charting solution, with data from Metabase Question API.

**Reason**: 
- Metabase Question API provides data query and calculation capabilities
- ECharts provides flexible and customizable chart rendering
- Avoids using Metabase's paid Embedding features
- Frontend has complete control over UI design

**Migration**:
- Replace existing ECharts charts with Metabase Question API data source
- Keep ECharts for chart rendering
- Preserve existing chart configurations and enhance with Metabase data

### Requirement: Backend KPI Calculation APIs
Backend SHALL NOT provide dedicated KPI calculation endpoints for dashboard.

**Reason**: KPI calculation moved to Metabase for better flexibility and non-technical user accessibility.

**Migration**:
- Remove `/api/dashboard/kpis` endpoint (except for fallback mode)
- Remove `/api/dashboard/sales-summary` endpoint
- Remove `/api/dashboard/product-ranking` endpoint
- Keep endpoints only for fallback data

---

## Component File Structure

```
frontend/src/
├── components/
│   ├── dashboard/
│   │   ├── MetabaseChart.vue           # 可复用Metabase仪表盘组件
│   │   ├── DashboardFilters.vue        # 仪表盘筛选器面板（包含粒度切换）
│   │   ├── ChartSkeleton.vue           # 图表加载骨架屏
│   │   ├── ChartErrorBoundary.vue      # 图表错误边界
│   │   └── FallbackChart.vue           # ECharts降级图表
├── views/
│   ├── BusinessOverview.vue            # 业务概览页面（集成Metabase）
│   ├── SalesAnalysis.vue               # 销售分析页面（可选）
│   └── InventoryDashboard.vue          # 库存仪表盘（可选）
├── stores/
│   └── dashboard.ts                    # Dashboard状态管理（Pinia）
```

## Component Implementation Guidelines

### MetabaseChart.vue Template
```vue
<template>
  <div class="metabase-chart-container">
    <!-- Loading Skeleton -->
    <ChartSkeleton v-if="loading" :height="height" />
    
    <!-- Error State -->
    <ChartErrorBoundary 
      v-else-if="error" 
      :error="error" 
      @retry="reloadChart"
    />
    
    <!-- ECharts Chart -->
    <div
      v-else
      ref="chartContainer"
      :style="{ height: height + 'px' }"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'

const props = defineProps<{
  dashboardId: number
  filters?: Record<string, any>
  granularity?: string
  height?: number
}>()

const emit = defineEmits<{
  loaded: []
  error: [error: Error]
}>()

const dashboardStore = useDashboardStore()
const loading = ref(true)
const error = ref<Error | null>(null)

const chartInstance = ref(null)

const loadChartData = async () => {
  try {
    loading.value = true
    error.value = null
    
    // Call Metabase Question API
    const response = await api.get(`/api/metabase/question/${props.questionId}/query`, {
      params: {
        filters: JSON.stringify({
          ...props.filters,
          granularity: props.granularity || 'daily'
        })
      }
    })
    
    // Initialize ECharts if not exists
    if (!chartInstance.value) {
      chartInstance.value = echarts.init(chartContainer.value)
    }
    
    // Render chart with data
    const option = buildChartOption(response.data, props.chartType)
    chartInstance.value.setOption(option)
    
    loading.value = false
    emit('loaded')
  } catch (err) {
    loading.value = false
    error.value = err
    emit('error', err)
  }
}

watch(() => [props.filters, props.granularity], () => {
  loadChartData()
}, { deep: true })

onMounted(() => {
  loadChartData()
})

onUnmounted(() => {
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
})

const reloadChart = () => {
  loadChartData()
}
</script>
```

### BusinessOverview.vue Structure
```vue
<template>
  <div class="business-overview">
    <!-- Page Header -->
    <el-page-header title="业务概览" />
    
    <!-- Filter Panel -->
    <DashboardFilters 
      v-model:filters="filters" 
      @apply="onFiltersApply"
    />
    
    <!-- Metabase Charts -->
    <div class="charts-grid">
      <MetabaseChart
        :question-id="1"
        :filters="chartFilters"
        :granularity="granularity"
        :chart-type="'line'"
        :height="400"
        @error="handleChartError"
      />
      <MetabaseChart
        :question-id="2"
        :filters="chartFilters"
        :granularity="granularity"
        :chart-type="'line'"
        :height="400"
        @error="handleChartError"
      />
    </div>
    
    <!-- Fallback Mode Warning -->
    <el-alert
      v-if="isFallbackMode"
      type="warning"
      :closable="false"
    >
      🔧 图表服务维护中，当前显示离线数据
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'

const dashboardStore = useDashboardStore()

const filters = ref({
  date_range: [new Date(), new Date()],
  platform: [],
  shop: []
})

const QUESTION_IDS = {
  GMV_TREND: 1,
  ORDER_COUNT: 2,
  ACHIEVEMENT_RATE: 3,
  SHOP_GMV: 4,
  PLATFORM_COMPARISON: 5
}

const granularity = ref('daily')

const chartFilters = computed(() => ({
  date_range: `${filters.value.date_range[0].toISOString().split('T')[0]}~${filters.value.date_range[1].toISOString().split('T')[0]}`,
  platform: filters.value.platform.join(','),
  shop_id: filters.value.shop.join(',')
}))

const isFallbackMode = computed(() => !dashboardStore.metabaseAvailable)

const onFiltersApply = () => {
  // Filters are reactive, charts will auto-reload
  console.log('Filters applied:', filters.value)
}

const handleChartError = (error: Error) => {
  console.error('Chart error:', error)
  // Could switch to fallback mode here
}
</script>

<style scoped>
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-top: 20px;
}

@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
```

---

## Testing Requirements

### Unit Tests
- [ ] Test MetabaseChart component initialization
- [ ] Test filter and granularity prop updates trigger iframe reload
- [ ] Test error handling and fallback mode
- [ ] Test height adjustment logic

### Integration Tests
- [ ] Test full dashboard load flow
- [ ] Test filter application (date range, shop, granularity)
- [ ] Test Metabase health check and fallback
- [ ] Test embedding token refresh
- [ ] Test granularity switching (daily/weekly/monthly)

### E2E Tests
- [ ] Test user can view business overview with Metabase dashboard
- [ ] Test user can apply filters and see updated dashboard
- [ ] Test user can switch granularity (daily/weekly/monthly)
- [ ] Test dashboard works when Metabase is down (fallback mode)
- [ ] Test auto-refresh functionality

---

## Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Initial page load | < 3s | Time to dashboard visible |
| Filter application | < 1s | Time to dashboard reloaded |
| Granularity switching | < 1s | Time to dashboard reloaded with new granularity |
| Dashboard interaction | < 500ms | Time to tooltip/zoom/drill-down response |
| Auto-refresh | < 2s | Time to refresh 5 Metabase Question queries (cache invalidation + query) |

---

## Accessibility Requirements

- [ ] All charts SHALL have descriptive `aria-label`
- [ ] Keyboard navigation SHALL work for filters and charts
- [ ] Color contrast SHALL meet WCAG AA standards
- [ ] Screen readers SHALL announce chart data changes

---

**Specification Version**: 1.0  
**Last Updated**: 2025-11-22  
**Status**: Proposed

