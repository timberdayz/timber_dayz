# BI Layer Specification

## ADDED Requirements

### Requirement: Metabase Integration
The system SHALL integrate Metabase as the core BI and visualization layer.

#### Scenario: Metabase deployment
- **WHEN** system is deployed
- **THEN** Metabase SHALL run in Docker container
- **AND** SHALL be accessible at `http://localhost:3000`
- **AND** SHALL connect to PostgreSQL database

#### Scenario: PostgreSQL data source configuration
- **WHEN** Metabase is initialized
- **THEN** administrator SHALL configure PostgreSQL connection:
  - Host: `postgres` (Docker network) or `localhost`
  - Port: `5432`
  - Database: `xihong_erp`
  - Connection pool: max_connections=50
- **AND** connection test SHALL succeed

### Requirement: Database Configuration
The system SHALL configure Metabase databases and tables based on PostgreSQL raw data tables.

#### Scenario: Core database and table registration
- **WHEN** BI layer is initialized
- **THEN** the following tables SHALL be registered in Metabase:
  - B-class data tables (raw data with JSONB):
    - `fact_raw_data_orders_daily/weekly/monthly` - Order data by granularity
    - `fact_raw_data_products_daily/weekly/monthly` - Product metrics by granularity
    - `fact_raw_data_traffic_daily/weekly/monthly` - Traffic data by granularity
    - `fact_raw_data_services_daily/weekly/monthly` - Services data by granularity
    - `fact_raw_data_inventory_snapshot` - Inventory snapshot data
    - `entity_aliases` - Unified entity alignment table
  - A-class data tables (user-configured, Chinese column names):
    - `sales_targets_a` - Sales targets
    - `sales_campaigns_a` - Campaign targets
    - `operating_costs` - Operating costs
    - `employees` - Employee profiles
    - `employee_targets` - Employee targets
    - `attendance_records` - Attendance records
  - C-class data tables (Metabase calculated, Chinese column names):
    - `employee_performance` - Employee performance metrics
    - `employee_commissions` - Employee commissions
    - `shop_commissions` - Shop commissions
    - `performance_scores_c` - Shop performance scores

#### Scenario: Table metadata refresh
- **WHEN** database schema changes (new columns added)
- **THEN** administrator SHALL refresh table metadata via Metabase UI
- **AND** new columns SHALL be available for question creation

### Requirement: Custom Fields (Calculated Columns)
Metabase SHALL support custom fields for KPI computation using formula expressions.

#### Scenario: Conversion rate calculation
- **WHEN** question is created based on `fact_raw_data_orders_daily` and `fact_raw_data_traffic_daily` tables
- **THEN** custom field `conversion_rate` SHALL be defined as:
  - Formula: `([订单数] / [客流量]) * 100` (类似Excel公式)
  - Or SQL Expression: `(raw_data->>'订单数')::numeric / NULLIF((raw_data->>'客流量')::numeric, 0) * 100`
  - Data Type: Number
  - Display Format: `0.00%`
  - **Note**: Uses JSONB field access with Chinese column names

#### Scenario: Attachment rate calculation
- **WHEN** question is created based on `fact_raw_data_orders_daily` table
- **THEN** custom field `attachment_rate` SHALL be defined as:
  - Formula: `[订单项数] / [订单数]` (类似Excel公式)
  - Or SQL Expression: `(raw_data->>'订单项数')::numeric / NULLIF((raw_data->>'订单数')::numeric, 0)`
  - Data Type: Number
  - Display Format: `0.00`
  - **Note**: Uses JSONB field access with Chinese column names

#### Scenario: Stock days calculation
- **WHEN** question is created based on `fact_raw_data_products_daily` table
- **THEN** custom field `stock_days` SHALL be defined as:
  - Formula: `[可用库存] / [日均销量]` (类似Excel公式)
  - Or SQL Expression: `(raw_data->>'可用库存')::numeric / NULLIF((raw_data->>'日均销量')::numeric, 0)`
  - Data Type: Number
  - Display Format: `0.0 days`
  - **Note**: Uses JSONB field access with Chinese column names

### Requirement: Business Overview Dashboard
The system SHALL provide a "Business Overview" dashboard with core KPI questions.

#### Scenario: Dashboard creation
- **WHEN** BI admin creates business overview dashboard
- **THEN** dashboard SHALL include minimum 5 questions:
  1. GMV Trend (Line Chart)
  2. Order Count Trend (Line Chart)
  3. Conversion Rate Trend (Line Chart)
  4. Inventory Health (Pie Chart)
  5. Profit Margin Comparison (Bar Chart)

#### Scenario: GMV trend question
- **WHEN** user views GMV trend question
- **THEN** question SHALL display:
  - Table: `fact_raw_data_orders_daily` (or weekly/monthly based on granularity)
  - X-axis: `metric_date` (Time dimension)
  - Y-axis: `raw_data->>'销售额'` (Metric, Sum aggregation, JSONB field with Chinese column name)
  - Filters: Platform (platform_code), Shop (shop_id), Date Range (metric_date)
  - Granularity: Day/Week/Month (user selectable via Dashboard parameter, determines which table to query)
  - **Note**: Query appropriate table based on granularity (daily/weekly/monthly)

#### Scenario: Order count trend question
- **WHEN** user views order count trend
- **THEN** question SHALL display:
  - Table: `fact_raw_data_orders_daily` (or weekly/monthly based on granularity)
  - X-axis: `metric_date`
  - Y-axis: `raw_data->>'订单数'` (Sum aggregation, JSONB field with Chinese column name)
  - Comparison: YoY, MoM, WoW available (Metabase native feature)

#### Scenario: Conversion rate trend question
- **WHEN** user views conversion rate trend
- **THEN** question SHALL display:
  - Tables: `fact_raw_data_orders_daily` JOIN `fact_raw_data_traffic_daily` (or appropriate granularity tables)
  - X-axis: `metric_date`
  - Y-axis: Custom Field `conversion_rate` (formula: `订单数 / 客流量 * 100`, using JSONB fields)
  - Format: Percentage (0.00%)

#### Scenario: Inventory health pie question
- **WHEN** user views inventory health
- **THEN** question SHALL display:
  - Table: `fact_raw_data_inventory_snapshot`
  - Dimension: Custom Field `stock_health` (calculated from `raw_data->>'当前库存'` and `raw_data->>'安全库存'`)
  - Metric: `Count of rows`
  - Colors: Red (Out of Stock), Yellow (Low), Green (Healthy)

#### Scenario: Profit margin bar question
- **WHEN** user views profit margin comparison
- **THEN** question SHALL display:
  - Tables: `fact_raw_data_orders_daily` JOIN `operating_costs` (via shop_id and year_month)
  - X-axis: `entity_aliases.target_name` (Chinese shop name, via JOIN with entity_aliases)
  - Y-axis: Custom Field `profit_margin` (formula: `(销售额 - 运营成本) / 销售额 * 100`, using JSONB fields and A-class data)
  - Sort: Descending by profit margin

### Requirement: Dashboard Filters and Interactions
Metabase dashboards SHALL support global filters and question interactions.

#### Scenario: Global date range filter
- **WHEN** user selects date range in dashboard filter
- **THEN** ALL questions SHALL update to show data for selected period
- **AND** date range SHALL be preserved across page navigation
- **AND** filter SHALL support relative dates (Last 30 days, Last 12 weeks, etc.)

#### Scenario: Global platform filter
- **WHEN** user selects platform(s) in dashboard filter
- **THEN** ALL questions SHALL filter to selected platforms
- **AND** filter SHALL support multi-select (Shopee + TikTok)

#### Scenario: Global shop filter
- **WHEN** user selects shop(s) in dashboard filter
- **THEN** ALL questions SHALL filter to selected shops
- **AND** filter SHALL support multi-select

#### Scenario: Granularity switching (Day/Week/Month)
- **WHEN** user switches granularity (daily/weekly/monthly) in frontend
- **THEN** frontend SHALL pass granularity parameter via URL
- **AND** Metabase dashboard SHALL update time grouping accordingly
- **AND** ALL questions SHALL refresh with new granularity

#### Scenario: Question drill-down
- **WHEN** user clicks on shop name in bar chart
- **THEN** dashboard SHALL apply shop filter
- **AND** ALL questions SHALL update to show that shop's data

#### Scenario: Question cross-filtering
- **WHEN** user clicks on data point in line chart
- **THEN** related questions SHALL highlight corresponding data
- **AND** user SHALL be able to clear selection

### Requirement: Query Caching
Metabase SHALL cache query results to improve performance.

#### Scenario: Query result caching
- **WHEN** user runs a question
- **THEN** Metabase SHALL cache results
- **AND** cache TTL SHALL be 300 seconds (5 minutes) by default
- **AND** subsequent identical queries SHALL use cache

#### Scenario: Cache invalidation after data ingestion
- **WHEN** new data is ingested into B-class data tables
- **THEN** backend SHALL invalidate Metabase query cache via API
- **AND** next query SHALL fetch fresh data
- **AND** cache invalidation SHALL be scoped to affected tables (e.g., only `fact_raw_data_orders_daily` if orders data was ingested)

### Requirement: User Authentication Integration
Metabase SHALL integrate with existing ERP user authentication system via JWT.

#### Scenario: SSO login via JWT
- **WHEN** user logs into ERP frontend
- **THEN** frontend SHALL obtain JWT token from ERP backend (`POST /api/auth/login`)
- **AND** SHALL use token to request Metabase session token (`POST /api/metabase/session-token`)
- **AND** backend SHALL validate JWT signature before generating session token
- **AND** session token SHALL include user_id, roles, shop_access

#### Scenario: Session token generation
- **WHEN** backend generates Metabase session token
- **THEN** token SHALL include:
  - `username`: `user@example.com`
  - `first_name`: `张`
  - `last_name`: `三`
  - `group_ids`: `[1, 2]` (Metabase group IDs)
  - `exp`: Unix timestamp (24 hours from now)
- **AND** SHALL call Metabase session API: `POST /api/session`

#### Scenario: User role mapping
- **WHEN** Metabase session token is generated
- **THEN** system SHALL map ERP roles to Metabase groups:
  - `Admin` → Metabase `Admin` group (full access)
  - `Manager` → Metabase `Analyst` group (read-only + SQL queries)
  - `Operator` → Metabase `Viewer` group (read-only dashboards)
  - `Finance` → Metabase `Finance` group (financial tables only)

#### Scenario: API authentication
- **WHEN** frontend calls Metabase Question API via backend proxy
- **THEN** backend SHALL use Metabase API Key for authentication
- **AND** SHALL handle authentication errors gracefully
- **AND** SHALL return appropriate error messages to frontend

### Requirement: Security and Permissions
Metabase SHALL enforce Row Level Security (RLS) and role-based access control.

#### Scenario: Row level security by shop
- **WHEN** non-admin user accesses dashboard
- **THEN** Metabase SHALL apply RLS filter:
  - SQL: `shop_id IN ({{ current_user_shop_ids }})`
  - Example: `shop_id IN ('shop_001', 'shop_002')`
- **AND** user SHALL only see data for authorized shops
- **AND** RLS filter SHALL be enforced at SQL query level (not client-side)

#### Scenario: RLS configuration per table
- **WHEN** table is added to Metabase (e.g., `fact_raw_data_orders_daily`)
- **THEN** admin SHALL configure RLS rule:
  - Table: `fact_raw_data_orders_daily` (and other B-class data tables)
  - Filter Type: SQL WHERE clause
  - Clause: `shop_id IN ({{ current_user_shop_ids() }})`
  - Groups: `Analyst`, `Viewer`, `Finance`
- **AND** Admin group SHALL be exempt from RLS (see all shops)
- **AND** RLS SHALL apply to all B-class data tables (`fact_raw_data_*`)

#### Scenario: RLS filter caching
- **WHEN** user accesses dashboard
- **THEN** Metabase SHALL:
  - Evaluate `current_user_shop_ids()` template variable
  - Cache result for session duration
  - Refresh when user permissions change (force re-login)

#### Scenario: Multi-table RLS consistency
- **WHEN** dashboard uses multiple tables with RLS
- **THEN** SAME RLS filter SHALL apply to ALL tables:
  - `fact_raw_data_orders_daily`: `shop_id IN (...)`
  - `fact_raw_data_products_daily`: `shop_id IN (...)`
  - `fact_raw_data_traffic_daily`: `shop_id IN (...)`
  - `fact_raw_data_services_daily`: `shop_id IN (...)`
- **AND** filter values SHALL be consistent across all queries
- **AND** A-class data tables (e.g., `sales_targets_a`) SHALL also apply RLS based on `shop_id` (using Chinese column name `"店铺ID"`)

#### Scenario: Role-based dashboard access
- **WHEN** user has "Analyst" group
- **THEN** user SHALL have read-only access to dashboards
- **AND** SHALL NOT be able to edit questions or tables
- **AND** SHALL have access to SQL queries for ad-hoc analysis

#### Scenario: Role-based table access
- **WHEN** user has "Finance" group
- **THEN** user SHALL access financial tables:
  - `fact_raw_data_orders_daily/weekly/monthly` (sales data, JSONB field `raw_data->>'销售额'`)
  - `operating_costs` (operating costs, A-class data with Chinese column names)
  - `employee_commissions` and `shop_commissions` (C-class calculated data)
- **AND** SHALL NOT access product performance tables:
  - `fact_raw_data_products_daily/weekly/monthly` (product metrics)
  - `fact_raw_data_traffic_daily/weekly/monthly` (traffic data)

#### Scenario: Permission inheritance
- **WHEN** user is assigned multiple groups
- **THEN** Metabase SHALL grant union of all group permissions
- **AND** RLS filters SHALL be combined with OR logic
- **Example**: User with `Analyst` (shop_001) + `Finance` (shop_002) sees BOTH shops

### Requirement: Metabase Question API Support
Metabase SHALL provide REST API for querying Question results, which frontend can use to render charts.

#### Scenario: Question API access
- **WHEN** frontend requests Question query result via backend proxy
- **THEN** backend SHALL call Metabase REST API:
  - Endpoint: `POST /api/card/{question_id}/query`
  - Authentication: API Key or Session Token
  - Parameters: filters, granularity, etc.
- **AND** SHALL return query result in JSON format

#### Scenario: Question data format
- **WHEN** Metabase Question API returns query result
- **THEN** response SHALL include:
  - `columns`: Array of column definitions (name, type)
  - `rows`: Array of data rows
  - `row_count`: Total number of rows

#### Scenario: Filter synchronization
- **WHEN** user changes filter in Vue frontend (date range, shop, granularity)
- **THEN** frontend SHALL call Metabase Question API with new filter parameters
- **AND** Metabase SHALL return filtered query result
- **AND** Frontend SHALL update charts with new data

#### Scenario: Granularity switching
- **WHEN** user switches granularity (daily/weekly/monthly) in frontend
- **THEN** frontend SHALL pass `granularity` parameter via URL
- **AND** Metabase dashboard SHALL update time grouping for all questions
- **AND** questions SHALL refresh with new time granularity

### Requirement: Native Query Support
Metabase SHALL provide native query editor for analysts to run ad-hoc queries.

#### Scenario: Ad-hoc query execution
- **WHEN** analyst runs native SQL query in Metabase
- **THEN** Metabase SHALL execute against PostgreSQL
- **AND** SHALL return results in tabular format
- **AND** SHALL support export to CSV/Excel

#### Scenario: Query timeout
- **WHEN** query exceeds 60 seconds
- **THEN** Metabase SHALL terminate query
- **AND** SHALL return timeout error message

### Requirement: Asynchronous Query Execution
Metabase SHALL support asynchronous execution for long-running queries.

#### Scenario: Long query async execution
- **WHEN** query is estimated to take > 10 seconds
- **THEN** Metabase SHALL execute asynchronously
- **AND** SHALL display progress indicator
- **AND** SHALL notify user when complete

#### Scenario: Query result download
- **WHEN** async query completes
- **THEN** user SHALL download results as CSV
- **AND** SHALL store results for 24 hours

### Requirement: Dashboard Export and Import
Metabase SHALL support exporting and importing dashboard configurations.

#### Scenario: Dashboard export
- **WHEN** admin exports dashboard
- **THEN** Metabase SHALL generate JSON file containing:
  - Dashboard metadata
  - Question configurations
  - Table definitions
  - Filter settings

#### Scenario: Dashboard import
- **WHEN** admin imports dashboard JSON
- **THEN** Metabase SHALL recreate dashboard
- **AND** SHALL validate table existence
- **AND** SHALL prompt for missing tables

### Requirement: Metabase Scheduled Calculation Tasks
The system SHALL use Metabase scheduled tasks to calculate C-class data (performance, commissions) and store results in PostgreSQL tables.

#### Scenario: Employee performance calculation task
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  1. Create a Metabase Question that:
     - Queries `fact_raw_data_orders_daily/weekly/monthly` tables
     - JOINs with `employees` table (via employee_id mapping)
     - Aggregates by `employee_id` and `year_month`
     - Calculates metrics: `实际销售额`, `实际订单数`, `达成率` (using Custom Fields)
  2. Configure Question as "Scheduled Question" with:
     - Schedule: Every 20 minutes
     - Action: Write results to PostgreSQL table `employee_performance`
     - Upsert strategy: Update existing records or insert new records
  3. Store results with Chinese column names:
     - `"员工编号"`, `"年月"`, `"实际销售额"`, `"实际订单数"`, `"达成率"`, `"排名"`
- **AND** SHALL handle missing targets gracefully (set achievement_rate to NULL)

#### Scenario: Employee commission calculation task
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  1. Create a Metabase Question that:
     - Queries `employee_performance` table
     - JOINs with commission rules (from `performance_config_a` table or hardcoded rules)
     - Calculates commission: `提成金额 = 销售额 * 提成率`
  2. Configure Question as "Scheduled Question" with:
     - Schedule: Every 20 minutes
     - Action: Write results to PostgreSQL table `employee_commissions`
     - Upsert strategy: Update existing records or insert new records
  3. Store results with Chinese column names:
     - `"员工编号"`, `"年月"`, `"销售额"`, `"提成率"`, `"提成金额"`

#### Scenario: Shop commission calculation task
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  1. Create a Metabase Question that:
     - Queries `fact_raw_data_orders_daily/weekly/monthly` tables
     - Aggregates by `shop_id` and `year_month`
     - Calculates shop-level commission based on shop sales
  2. Configure Question as "Scheduled Question" with:
     - Schedule: Every 20 minutes
     - Action: Write results to PostgreSQL table `shop_commissions`
     - Upsert strategy: Update existing records or insert new records
  3. Store results with Chinese column names:
     - `"店铺ID"`, `"年月"`, `"销售额"`, `"提成率"`, `"提成金额"`

#### Scenario: Scheduled task error handling
- **WHEN** scheduled task fails (e.g., database connection error, calculation error)
- **THEN** the system SHALL:
  - Log error to Metabase task log
  - Send alert to administrator (if configured)
  - Retry task on next schedule (every 20 minutes)
  - **NOT** block other scheduled tasks from running

#### Scenario: Scheduled task monitoring
- **WHEN** administrator monitors scheduled tasks
- **THEN** Metabase SHALL provide:
  - Task execution history (last 100 runs)
  - Success/failure status
  - Execution time
  - Records updated/inserted count
  - Error messages (if any)

**Implementation Notes**:
- Metabase Scheduled Questions can be configured via Metabase UI (Admin → Schedules)
- Alternatively, use Metabase API to create scheduled questions programmatically
- Results are written to PostgreSQL using Metabase's "Action" feature or custom SQL
- For complex calculations, use Metabase Native Query (SQL) instead of Query Builder

### Requirement: Performance Monitoring
Metabase SHALL provide query performance monitoring and optimization suggestions.

#### Scenario: Slow query logging
- **WHEN** query exceeds 5 seconds
- **THEN** Metabase SHALL log to slow query log:
  - Query SQL
  - Execution time
  - User
  - Table
- **AND** admin SHALL review logs weekly

#### Scenario: Query optimization suggestions
- **WHEN** admin reviews slow queries
- **THEN** Metabase SHALL suggest:
  - Missing indexes (especially GIN indexes on JSONB `raw_data` fields)
  - Query rewrite opportunities (e.g., using JSONB operators more efficiently)
  - Table partitioning candidates (if data volume is large)
  - **Note**: Metabase SHALL NOT suggest materialized views (DSS architecture queries raw tables directly)

## MODIFIED Requirements

None. This is a new capability being added to the system.

## REMOVED Requirements

None. No existing BI functionality to remove.

## Implementation Notes

### Metabase Configuration
```yaml
# docker-compose.metabase.yml
version: '3.8'
services:
  metabase:
    image: metabase/metabase:latest
    container_name: metabase
    environment:
      - MB_DB_TYPE=postgres
      - MB_DB_DBNAME=xihong_erp
      - MB_DB_PORT=5432
      - MB_DB_USER=erp_user
      - MB_DB_PASS=erp_pass_2025
      - MB_DB_HOST=postgres
      - MB_API_KEY=${METABASE_API_KEY}
    ports:
      - "3000:3000"
    depends_on:
      - postgres
    networks:
      - xihong_erp_erp_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Vue.js Metabase Chart Component
```vue
<template>
  <div class="metabase-chart">
    <div
      v-if="loading"
      class="loading"
    >
      <el-spinner />
      <p>加载图表中...</p>
    </div>
    <div
      v-else-if="error"
      class="error"
    >
      <p>图表加载失败: {{ error }}</p>
      <el-button @click="reloadChart">重试</el-button>
    </div>
    <div
      v-else
      ref="chartContainer"
      :style="{ height: height + 'px' }"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import * as echarts from 'echarts';
import { getQuestionData } from '@/services/metabase';

const props = defineProps({
  questionId: Number,
  filters: Object,
  granularity: { type: String, default: 'daily' },
  chartType: { type: String, default: 'line' },
  height: { type: Number, default: 400 }
});

const chartContainer = ref(null);
const chartInstance = ref(null);
const loading = ref(true);
const error = ref(null);

const loadChart = async () => {
  try {
    loading.value = true
    error.value = null
    
    // Call Metabase Question API
    const data = await getQuestionData(props.questionId, {
      ...props.filters,
      granularity: props.granularity
    })
    
    // Initialize ECharts if not exists
    if (!chartInstance.value) {
      chartInstance.value = echarts.init(chartContainer.value)
    }
    
    // Build chart option based on chartType
    const option = buildChartOption(data, props.chartType)
    chartInstance.value.setOption(option)
    
    loading.value = false
  } catch (err) {
    loading.value = false
    error.value = err.message
  }
}

const reloadChart = () => {
  loadChart()
}

const buildChartOption = (data, chartType) => {
  // Build ECharts option based on data and chartType
  return {
    xAxis: {
      type: 'category',
      data: data.data.rows.map(r => r[0])
    },
    yAxis: { type: 'value' },
    series: [{
      data: data.data.rows.map(r => r[1]),
      type: chartType
    }]
  }
}

watch(() => [props.filters, props.granularity], () => {
  loadChart()
}, { deep: true })

onMounted(() => {
  loadChart()
})

onUnmounted(() => {
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
})
</script>
```

### Performance Targets
- Dashboard load time: < 3 seconds
- Question render time: < 1 second
- Query execution: < 5 seconds (P95)
- Cache hit rate: > 70%
- Concurrent users: 50+ without degradation

### Training and Documentation
- Metabase User Guide (Chinese): 30-minute training for non-technical users
- Dashboard Creation Guide: Step-by-step tutorials (拖拽式操作)
- Question Creation Guide: How to create questions using query builder (类似Excel)
- Custom Field Guide: How to create calculated fields (类似Excel公式)
- Troubleshooting Guide: Common issues and solutions

