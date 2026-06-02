<template>
  <div class="business-overview erp-page-container erp-page--dashboard">
    <PageHeader
      title="业务概览"
      subtitle="实时监控核心业务指标，洞察业务发展趋势。页面级刷新保留在页面本身，不走全局壳层刷新。"
      family="dashboard"
    >
      <template #actions>
        <el-button type="primary" @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="dashboardAssetNotice"
      :title="dashboardAssetNotice.title"
      :description="dashboardAssetNotice.description"
      :type="dashboardAssetNotice.type"
      show-icon
      :closable="false"
      class="dashboard-asset-alert"
    />

    <!-- 全局日期（页面级主控，各模块可跟随或手动覆盖） -->
    <div class="global-date-bar">
      <span class="global-date-label">全局日期</span>
      <el-radio-group v-model="globalGranularity" size="small" @change="onGlobalGranularityChange">
        <el-radio-button label="daily">日</el-radio-button>
        <el-radio-button label="weekly">周</el-radio-button>
        <el-radio-button label="monthly">月</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="globalDate"
        :type="globalDatePickerType"
        :format="globalDatePickerFormat"
        :value-format="globalDatePickerValueFormat"
        :placeholder="globalDatePickerPlaceholder"
        size="small"
        class="global-date-picker"
        @change="onGlobalDateChange"
      />
    </div>

    <!-- 核心KPI指标卡片 -->
    <div class="kpi-section">
      <!-- KPI 筛选器 -->
      <div class="kpi-filters">
        <span class="filter-label">核心KPI指标</span>
        <el-tooltip
          :content="
            useGlobalDate.kpi
              ? '已跟随全局日期'
              : '点击恢复跟随全局'
          "
        >
          <el-button
            :type="useGlobalDate.kpi ? 'primary' : 'default'"
            link
            size="small"
            @click="syncModuleToGlobal('kpi')"
          >
            <el-icon><Link /></el-icon>
            {{ useGlobalDate.kpi ? '跟随' : '恢复' }}
          </el-button>
        </el-tooltip>
        <el-radio-group
          v-model="kpiGranularity"
          size="small"
          @change="onKpiGranularityChange"
        >
          <el-radio-button label="daily">日</el-radio-button>
          <el-radio-button label="weekly">周</el-radio-button>
          <el-radio-button label="monthly">月</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="kpiMonth"
          :type="kpiDatePickerType"
          :format="kpiDatePickerFormat"
          :value-format="kpiDatePickerValueFormat"
          :placeholder="kpiDatePickerPlaceholder"
          size="small"
          class="control-w-140"
          @change="onKpiMonthChange"
        />
        <el-select
          v-model="kpiPlatform"
          placeholder="全部平台"
          clearable
          size="small"
          class="control-w-120"
          @change="onKpiFilterChange"
        >
          <el-option label="全部平台" value="" />
          <el-option label="Shopee" value="shopee" />
          <el-option label="TikTok" value="tiktok" />
          <el-option label="妙手" value="miaoshou" />
        </el-select>
        <el-button
          size="small"
          @click="onKpiFilterChange"
          :loading="loadingKPI"
        >
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <!-- KPI 卡片（7 张等分一行：转化率、客流量、客单价、GMV、订单数、连带率、人效） -->
      <div class="kpi-cards" v-loading="loadingKPI">
        <el-row :gutter="20" class="kpi-cards-row">
          <el-col
            :xs="24"
            :sm="12"
            :md="8"
            :lg="4"
            v-for="kpi in kpiData"
            :key="kpi.key"
          >
            <el-card class="kpi-card" shadow="hover">
              <div class="kpi-content">
                <div class="kpi-icon" :class="kpi.iconClass">
                  <el-icon><component :is="kpi.icon" /></el-icon>
                </div>
                <div class="kpi-info">
                  <div class="kpi-title">{{ kpi.title }}</div>
                  <div class="kpi-value">{{ kpi.value }}</div>
                  <div class="kpi-change" :class="kpi.changeType">
                    <el-icon><component :is="kpi.changeIcon" /></el-icon>
                    {{ kpi.change }}
                  </div>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </div>

    <!-- 经营指标表格（门店经营） -->
    <div class="operational-metrics-section">
      <el-card class="chart-card" shadow="hover">
            <template #header>
          <div class="card-header">
            <span>经营指标</span>
            <div class="header-controls">
              <el-tooltip :content="useGlobalDate.operational ? '已跟随全局日期' : '点击恢复跟随全局'">
                <el-button
                  :type="useGlobalDate.operational ? 'primary' : 'default'"
                  link
                  size="small"
                  @click="syncModuleToGlobal('operational')"
                >
                  <el-icon><Link /></el-icon>
                  {{ useGlobalDate.operational ? '跟随' : '恢复' }}
                </el-button>
              </el-tooltip>
              <el-date-picker
                v-model="operationalDate"
                type="month"
                format="YYYY-MM"
                value-format="YYYY-MM-01"
                placeholder="????"
                size="small"
                class="control-w-140"
                @change="onOperationalDateChange"
              />
              <el-button
                size="small"
                @click="loadOperationalMetrics"
                :loading="loadingOperational"
              >
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>
        </template>
        <div class="operational-metrics-grid" v-loading="loadingOperational">
          <!-- 第一行：月目标、当月总达成、今日销售额、月达成率 -->
          <div class="metrics-row">
            <div class="metric-item">
              <div class="metric-label">月目标</div>
              <div class="metric-value">
                {{ formatNumber(operationalMetrics.monthly_target) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">当月总达成</div>
              <div class="metric-value">
                {{ formatNumber(operationalMetrics.monthly_total_achieved) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">
                {{ operationalDateLabel }}销售额
              </div>
              <div class="metric-value">
                {{ formatNumber(operationalMetrics.today_sales) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">月达成率</div>
              <div class="metric-value">
                <el-tag
                  :type="
                    getAchievementRateTagType(
                      operationalMetrics.monthly_achievement_rate,
                    )
                  "
                  size="small"
                >
                  {{ formatNullablePercent(operationalMetrics.monthly_achievement_rate) }}
                </el-tag>
              </div>
            </div>
            <!-- 经营结果：最右侧竖状，跨两行 -->
            <div class="metric-item metric-result-vertical">
              <div class="metric-label">经营结果</div>
              <div class="metric-value">
                <el-tag
                  :type="getOperatingResultTagType(operationalMetrics.operating_result)"
                  size="small"
                >
                  {{ operationalMetrics.operating_result_text }}
                </el-tag>
              </div>
            </div>
          </div>
          <!-- 第二行：时间GAP、预估毛利、预估费用、今日销售单数 -->
          <div class="metrics-row">
            <div class="metric-item">
              <div class="metric-label">时间GAP</div>
              <div class="metric-value">
                <el-tag
                  :type="getTimeGapTagType(operationalMetrics.time_gap)"
                  size="small"
                >
                  {{ operationalMetrics.time_gap != null && operationalMetrics.time_gap > 0 ? "+" : ""
                  }}{{ formatNullablePercent(operationalMetrics.time_gap) }}
                </el-tag>
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">
                <el-tooltip
                  content="来源：订单导出字段（利润/毛利/profit）聚合；口径可能因平台报表不同而不一致，需业务确认。"
                  placement="top"
                >
                  <span>预估利润</span>
                </el-tooltip>
              </div>
              <div class="metric-value">
                {{ formatNumber(operationalMetrics.estimated_gross_profit) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">
                <el-tooltip
                  :content="operationalExpensesTooltip"
                  placement="top"
                >
                  <span>预估费用</span>
                </el-tooltip>
              </div>
              <div class="metric-value">
                {{ operationalMetrics.estimated_expenses == null ? '--' : formatNumber(operationalMetrics.estimated_expenses) }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">{{ operationalDateLabel }}销售单数</div>
              <div class="metric-value">
                {{ formatInteger(operationalMetrics.today_order_count) }}
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 数据对比和店铺赛马区域 -->
    <div class="comparison-section">
      <el-row :gutter="20">
        <!-- 左侧：数据对比图表 -->
        <el-col :xs="24" :lg="14">
          <el-card class="chart-card" shadow="hover">
            <template #header>
                <div class="card-header">
                <span>数据对比分析</span>
                <div class="header-controls">
                  <el-tooltip :content="useGlobalDate.comparison ? '已跟随全局日期' : '点击恢复跟随全局'">
                    <el-button
                      :type="useGlobalDate.comparison ? 'primary' : 'default'"
                      link
                      size="small"
                      @click="syncModuleToGlobal('comparison')"
                    >
                      <el-icon><Link /></el-icon>
                      {{ useGlobalDate.comparison ? '跟随' : '恢复' }}
                    </el-button>
                  </el-tooltip>
                  <el-radio-group
                    v-model="comparisonGranularity"
                    size="small"
                    @change="onComparisonGranularityChange"
                  >
                    <el-radio-button label="daily">日</el-radio-button>
                    <el-radio-button label="weekly">周</el-radio-button>
                    <el-radio-button label="monthly">月</el-radio-button>
                  </el-radio-group>
                  <el-date-picker
                    v-model="comparisonDate"
                    :type="datePickerType"
                    :format="datePickerFormat"
                    :value-format="datePickerValueFormat"
                    :placeholder="datePickerPlaceholder"
                    size="small"
                    class="control-offset control-w-150"
                    @change="onComparisonDateChange"
                  />
                </div>
              </div>
            </template>
            <div class="chart-container">
              <!-- 目标达成率进度条 -->
              <div
                class="target-progress-section"
                v-loading="loadingComparison"
              >
                <div class="target-progress-item">
                  <div class="target-label">{{ targetProgressLabel }}</div>
                  <el-progress
                    :percentage="targetAchievementRate"
                    :color="getTargetProgressColor(targetAchievementRate ?? 0)"
                    :stroke-width="20"
                    :format="(percentage) => (percentage != null && !Number.isNaN(Number(percentage))) ? `${Number(percentage).toFixed(1)}%` : '0.0%'"
                  />
                  <div class="target-details">
                    <span
                      >目标: {{ formatNumber(targetValue)
                      }}{{ targetUnit }}</span
                    >
                    <span
                      >达成: {{ formatNumber(achievedValue)
                      }}{{ targetUnit }}</span
                    >
                  </div>
                </div>
              </div>

              <!-- 数据对比表格 -->
              <div class="comparison-table-container">
                <el-table
                  :data="comparisonTableData"
                  stripe
                  class="erp-w-full"
                  size="small"
                  border
                  :show-header="true"
                  empty-text="暂无数据"
                >
                  <el-table-column
                    prop="metric"
                    label="指标"
                    width="120"
                    align="left"
                    fixed="left"
                  />
                  <el-table-column
                    :label="currentPeriodLabel"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      <span :class="row.todayClass">{{ row.today }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="previousPeriodLabel"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ row.yesterday }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="averageLabel"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      {{ row.average }}
                    </template>
                  </el-table-column>
                  <el-table-column label="环比" width="100" align="center">
                    <template #default="{ row }">
                      <div class="change-indicator">
                        <el-icon
                          v-if="row.changeType === 'increase'"
                          class="increase-icon"
                        >
                          <ArrowUp />
                        </el-icon>
                        <el-icon
                          v-else-if="row.changeType === 'decrease'"
                          class="decrease-icon"
                        >
                          <ArrowDown />
                        </el-icon>
                        <el-icon v-else class="neutral-icon">
                          <Minus />
                        </el-icon>
                        <span :class="row.changeClass">{{ row.change }}</span>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：店铺赛马（日/周/月 + 日期 + 筛选维度：店铺或账号） -->
        <el-col :xs="24" :lg="10">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>店铺赛马</span>
                <div class="header-controls">
                  <el-tooltip :content="useGlobalDate.shopRacing ? '已跟随全局日期' : '点击恢复跟随全局'">
                    <el-button
                      :type="useGlobalDate.shopRacing ? 'primary' : 'default'"
                      link
                      size="small"
                      @click="syncModuleToGlobal('shopRacing')"
                    >
                      <el-icon><Link /></el-icon>
                      {{ useGlobalDate.shopRacing ? '跟随' : '恢复' }}
                    </el-button>
                  </el-tooltip>
                  <el-radio-group
                    v-model="shopRacingGranularity"
                    size="small"
                    @change="onShopRacingGranularityChange"
                  >
                    <el-radio-button label="daily">日</el-radio-button>
                    <el-radio-button label="weekly">周</el-radio-button>
                    <el-radio-button label="monthly">月</el-radio-button>
                  </el-radio-group>
                <el-radio-group
                  v-model="racingGroupBy"
                  size="small"
                  class="control-offset"
                  @change="loadShopRacingData"
                >
                    <el-radio-button label="shop">店铺</el-radio-button>
                    <el-radio-button label="account">账号</el-radio-button>
                  </el-radio-group>
                  <el-date-picker
                    v-model="shopRacingDate"
                    :type="shopRacingDatePickerType"
                    :format="shopRacingDatePickerFormat"
                    :value-format="shopRacingDatePickerValueFormat"
                    :placeholder="shopRacingDatePickerPlaceholder"
                    size="small"
                    class="control-offset control-w-150"
                    @change="onShopRacingDateChange"
                  />
                  <el-button
                    size="small"
                    @click="loadShopRacingData"
                    :loading="loadingShopRacing"
                    class="control-offset"
                  >
                    <el-icon><Refresh /></el-icon>
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            <div class="racing-container" v-loading="loadingShopRacing">
              <el-table
                :data="shopRacingData"
                stripe
                class="erp-w-full"
                size="small"
              >
                <el-table-column prop="name" label="名称" width="160" show-overflow-tooltip>
                  <template #default="{ row }">
                    <el-button
                      v-if="isUnmatchedShopRow(row)"
                      link
                      type="warning"
                      @click="showUnmatchedAliasDialog(row)"
                    >
                      {{ row.name }}
                    </el-button>
                    <div v-else class="shop-display-cell">
                      <div>{{ row.name }}</div>
                      <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="target" label="目标" width="80">
                  <template #default="{ row }">
                    {{ formatCurrency(row.target) }}
                  </template>
                </el-table-column>
                <el-table-column prop="achieved" label="完成" width="80">
                  <template #default="{ row }">
                    {{ formatCurrency(row.achieved) }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="achievement_rate"
                  label="完成率"
                  width="100"
                >
                  <template #default="{ row }">
                    <el-progress
                      :percentage="Math.round(row.achievement_rate * 100)"
                      :color="getAchievementColor(row.achievement_rate)"
                      :stroke-width="8"
                    />
                  </template>
                </el-table-column>
                <el-table-column
                  prop="rank"
                  label="排名"
                  width="60"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag
                      :type="row.rank <= 3 ? 'success' : 'info'"
                      size="small"
                    >
                      {{ row.rank }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 流量排名模块 -->
    <div class="traffic-ranking-section">
      <el-card class="chart-card" shadow="hover">
            <template #header>
          <div class="card-header">
            <span>流量排名</span>
            <div class="header-controls">
              <el-tooltip :content="useGlobalDate.trafficRanking ? '已跟随全局日期' : '点击恢复跟随全局'">
                <el-button
                  :type="useGlobalDate.trafficRanking ? 'primary' : 'default'"
                  link
                  size="small"
                  @click="syncModuleToGlobal('trafficRanking')"
                >
                  <el-icon><Link /></el-icon>
                  {{ useGlobalDate.trafficRanking ? '跟随' : '恢复' }}
                </el-button>
              </el-tooltip>
              <el-radio-group
                v-model="trafficRankingGranularity"
                size="small"
                @change="onTrafficRankingGranularityChange"
              >
                <el-radio-button label="daily">日</el-radio-button>
                <el-radio-button label="weekly">周</el-radio-button>
                <el-radio-button label="monthly">月</el-radio-button>
              </el-radio-group>
              <el-radio-group
                v-model="trafficRankingDimension"
                size="small"
                class="control-offset"
                @change="loadTrafficRanking"
              >
                <el-radio-button label="shop">店铺</el-radio-button>
                <el-radio-button label="account">账号</el-radio-button>
              </el-radio-group>
              <el-date-picker
                v-model="trafficRankingDate"
                :type="trafficRankingDatePickerType"
                :format="trafficRankingDatePickerFormat"
                :value-format="trafficRankingDatePickerValueFormat"
                :placeholder="trafficRankingDatePickerPlaceholder"
                size="small"
                class="control-offset control-w-150"
                @change="onTrafficRankingDateChange"
              />
              <el-button
                size="small"
                @click="loadTrafficRanking"
                class="control-offset"
              >
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>
        </template>
        <div
          v-if="trafficRankingData.length && trafficRankingData.every((r) => (r.name === r.platform_code) || r.name === '平台汇总')"
          class="traffic-ranking-hint"
        >
          当前数据未关联店铺，显示为平台汇总；关联店铺后可按店铺查看排名。
        </div>
        <el-table
          :data="trafficRankingData"
          stripe
          class="erp-w-full erp-table"
          size="small"
          v-loading="loadingTrafficRanking"
        >
          <el-table-column
            prop="rank"
            label="排名"
            width="80"
            fixed="left"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="
                  row.rank === 1
                    ? 'success'
                    : row.rank === 2
                      ? 'warning'
                      : row.rank === 3
                        ? 'info'
                        : 'primary'
                "
                size="small"
              >
                {{ row.rank }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="name"
            label="名称"
            width="200"
            fixed="left"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <el-button
                v-if="isUnmatchedShopRow(row)"
                link
                type="warning"
                @click="showUnmatchedAliasDialog(row)"
              >
                {{ row.name }}
              </el-button>
              <div v-else class="shop-display-cell">
                <div>{{ row.name }}</div>
                <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="platform_code"
            label="平台"
            width="120"
            v-if="trafficRankingDimension === 'shop'"
          />
          <el-table-column
            prop="visitor_count"
            label="访客数(UV)"
            width="150"
            align="right"
            sortable
          >
            <template #default="{ row }">
              {{ formatNumber(row.visitor_count) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="page_views"
            label="浏览量(PV)"
            width="150"
            align="right"
            sortable
          >
            <template #default="{ row }">
              {{ formatNumber(row.page_views) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="uv_change_rate"
            label="UV环比"
            width="120"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span
                :class="
                  (row.uv_change_rate ?? 0) >= 0 ? 'text-success' : 'text-danger'
                "
              >
                {{
                  row.uv_change_rate != null && !Number.isNaN(Number(row.uv_change_rate))
                    ? (row.uv_change_rate >= 0 ? '+' : '') + Number(row.uv_change_rate).toFixed(2) + '%'
                    : '--'
                }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            prop="pv_change_rate"
            label="PV环比"
            width="120"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span
                :class="
                  (row.pv_change_rate ?? 0) >= 0 ? 'text-success' : 'text-danger'
                "
              >
                {{
                  row.pv_change_rate != null && !Number.isNaN(Number(row.pv_change_rate))
                    ? (row.pv_change_rate >= 0 ? '+' : '') + Number(row.pv_change_rate).toFixed(2) + '%'
                    : '--'
                }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            prop="compare_visitor_count"
            label="对比期UV"
            width="150"
            align="right"
          >
            <template #default="{ row }">
              {{ row.compare_visitor_count != null ? formatNumber(row.compare_visitor_count) : '--' }}
            </template>
          </el-table-column>
          <el-table-column
            prop="compare_page_views"
            label="对比期PV"
            width="150"
            align="right"
          >
            <template #default="{ row }">
              {{ row.compare_page_views != null ? formatNumber(row.compare_page_views) : '--' }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-dialog
      v-model="unmatchedAliasDialogVisible"
      :title="`未匹配店铺别名${unmatchedAliasPlatform ? ` - ${unmatchedAliasPlatform}` : ''}`"
      width="720px"
    >
      <el-table
        v-loading="unmatchedAliasDialogLoading"
        :data="unmatchedAliasRows"
        stripe
        border
        max-height="420"
        empty-text="当前平台暂无未匹配原始别名"
      >
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="site" label="站点" width="120">
          <template #default="{ row }">
            {{ row.site || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="store_label_raw" label="原始别名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="order_count" label="订单数" width="100" align="right" />
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            {{ Number(row.paid_amount || 0).toFixed(2) }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="unmatchedAliasDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 库存滞销情况 -->
    <div class="inventory-section">
      <el-card class="chart-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>库存积压与滞销风险</span>
            <div class="header-controls">
              <el-button size="small" @click="loadInventoryBacklog">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>
        </template>

        <!-- 库存汇总 -->
        <div class="inventory-summary" v-loading="loadingInventory">
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">总库存价值</div>
                <div class="summary-value">
                  {{ formatCurrency(inventorySummary.total_value) }}
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">30天+预计周转库存</div>
                <div class="summary-value danger">
                  {{ formatCurrency(inventorySummary.backlog_30d_value) }}
                </div>
                <div class="summary-ratio">
                  {{ inventorySummary.backlog_30d_ratio }}%
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">60天+预计周转库存</div>
                <div class="summary-value warning">
                  {{ formatCurrency(inventorySummary.backlog_60d_value) }}
                </div>
                <div class="summary-ratio">
                  {{ inventorySummary.backlog_60d_ratio }}%
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">90天+预计周转库存</div>
                <div class="summary-value danger">
                  {{ formatCurrency(inventorySummary.backlog_90d_value) }}
                </div>
                <div class="summary-ratio">
                  {{ inventorySummary.backlog_90d_ratio }}%
                </div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 高积压风险产品Top20 -->
        <div class="inventory-table">
          <el-table
            :data="inventoryBacklogProducts"
            stripe
            class="erp-w-full"
            size="small"
          >
            <el-table-column
              type="index"
              label="排名"
              width="60"
              align="center"
            />
            <el-table-column
              prop="product_name"
              label="产品名称"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column prop="platform_sku" label="SKU" width="120" />
            <el-table-column
              prop="available_stock"
              label="可用库存"
              width="100"
              align="right"
            />
            <el-table-column
              prop="estimated_turnover_days"
              label="预计周转天数"
              width="100"
              align="right"
            >
              <template #default="{ row }">
                <el-tag :type="getAgeTagType(row.estimated_turnover_days)" size="small">
                  {{ row.estimated_turnover_days }}天
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="estimated_stagnant_days"
              label="估算积压天数"
              width="120"
              align="right"
            />
            <el-table-column
              prop="stagnant_snapshot_count"
              label="连续积压快照数"
              width="120"
              align="right"
            />
            <el-table-column
              prop="inventory_value"
              label="积压价值"
              width="120"
              align="right"
            >
              <template #default="{ row }">
                {{ formatCurrency(row.inventory_value) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="risk_level"
              label="风险等级"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                <el-tag
                  :type="getCategoryTagType(row.risk_level)"
                  size="small"
                >
                  {{ row.risk_level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="clearance_priority_score"
              label="清理优先级"
              width="120"
              align="right"
            >
              <template #default="{ row }">
                {{ Number(row.clearance_priority_score || 0).toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </div>

    <!-- 滞销清理排名模块 -->
    <div class="clearance-ranking-section">
      <el-row :gutter="20">
        <!-- 月度排名 -->
        <el-col :span="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
                <div class="card-header">
                <span>滞销清理排名（月度）</span>
                <div class="header-controls">
                  <el-tooltip
                    :content="
                      globalGranularity === 'monthly' || globalGranularity === 'weekly'
                        ? useGlobalDate.clearance
                          ? '已跟随全局日期（月/周粒度）'
                          : '点击恢复跟随全局'
                        : '仅月/周粒度时跟随，当前全局为日'
                    "
                  >
                    <el-button
                      :type="useGlobalDate.clearance && (globalGranularity === 'monthly' || globalGranularity === 'weekly') ? 'primary' : 'default'"
                      link
                      size="small"
                      :disabled="globalGranularity === 'daily'"
                      @click="syncModuleToGlobal('clearance')"
                    >
                      <el-icon><Link /></el-icon>
                      {{ useGlobalDate.clearance ? '跟随' : '恢复' }}
                    </el-button>
                  </el-tooltip>
                  <el-date-picker
                    v-model="clearanceMonth"
                    type="month"
                    format="YYYY-MM"
                    value-format="YYYY-MM"
                    placeholder="选择月份"
                    size="small"
                    class="control-w-150"
                    @change="onClearanceMonthChange"
                  />
                  <el-button
                    size="small"
                    @click="loadClearanceRanking('monthly')"
                  >
                    <el-icon><Refresh /></el-icon>
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            <el-table
              :data="monthlyClearanceRanking"
              stripe
              class="erp-w-full erp-table"
              size="small"
              v-loading="loadingClearanceRanking"
            >
              <el-table-column
                prop="rank"
                label="排名"
                width="80"
                fixed="left"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="
                      row.rank === 1
                        ? 'success'
                        : row.rank === 2
                          ? 'warning'
                          : row.rank === 3
                            ? 'info'
                            : 'primary'
                    "
                    size="small"
                  >
                    {{ row.rank }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="shop_name"
                label="店铺名称"
                width="200"
                fixed="left"
                show-overflow-tooltip
              />
              <el-table-column
                prop="clearance_amount"
                label="清理金额"
                width="150"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.clearance_amount) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="clearance_quantity"
                label="清理数量"
                width="120"
                align="right"
                sortable
              />
              <el-table-column
                prop="incentive_amount"
                label="激励金额"
                width="120"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.incentive_amount) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="total_incentive"
                label="总计激励"
                width="120"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.total_incentive) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <!-- 周度排名 -->
        <el-col :span="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
                <div class="card-header">
                <span>滞销清理排名（周度）</span>
                <div class="header-controls">
                  <el-tooltip
                    :content="
                      globalGranularity === 'monthly' || globalGranularity === 'weekly'
                        ? useGlobalDate.clearance
                          ? '已跟随全局日期（月/周粒度）'
                          : '点击恢复跟随全局'
                        : '仅月/周粒度时跟随，当前全局为日'
                    "
                  >
                    <el-button
                      :type="useGlobalDate.clearance && (globalGranularity === 'monthly' || globalGranularity === 'weekly') ? 'primary' : 'default'"
                      link
                      size="small"
                      :disabled="globalGranularity === 'daily'"
                      @click="syncModuleToGlobal('clearance')"
                    >
                      <el-icon><Link /></el-icon>
                      {{ useGlobalDate.clearance ? '跟随' : '恢复' }}
                    </el-button>
                  </el-tooltip>
                  <el-date-picker
                    v-model="clearanceWeek"
                    type="week"
                    format="YYYY 第 ww 周"
                    placeholder="选择周"
                    size="small"
                    class="control-w-160"
                    @change="onClearanceWeekChange"
                  />
                  <el-button
                    size="small"
                    @click="loadClearanceRanking('weekly')"
                  >
                    <el-icon><Refresh /></el-icon>
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            <el-table
              :data="weeklyClearanceRanking"
              stripe
              class="erp-w-full erp-table"
              size="small"
              v-loading="loadingClearanceRanking"
            >
              <el-table-column
                prop="rank"
                label="排名"
                width="80"
                fixed="left"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="
                      row.rank === 1
                        ? 'success'
                        : row.rank === 2
                          ? 'warning'
                          : row.rank === 3
                            ? 'info'
                            : 'primary'
                    "
                    size="small"
                  >
                    {{ row.rank }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="shop_name"
                label="店铺名称"
                width="200"
                fixed="left"
                show-overflow-tooltip
              />
              <el-table-column
                prop="clearance_amount"
                label="清理金额"
                width="150"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.clearance_amount) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="clearance_quantity"
                label="清理数量"
                width="120"
                align="right"
                sortable
              />
              <el-table-column
                prop="incentive_amount"
                label="激励金额"
                width="120"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.incentive_amount) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="total_incentive"
                label="总计激励"
                width="120"
                align="right"
                sortable
              >
                <template #default="{ row }">
                  {{ formatCurrency(row.total_incentive) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api from '@/api'
import accountsApi from '@/api/accounts'
import {
  formatCurrency,
  formatNumber as formatNumberUtil,
  formatPercent as formatPercentUtil,
  formatInteger as formatIntegerUtil
} from '@/utils/dataFormatter'
import {
  showError as showApiError,
  handleApiError,
  getDashboardAssetUnavailableInfo
} from '@/utils/errorHandler'
import { normalizeClearanceRankingResponse } from '@/utils/businessOverviewData'
import { buildShopAccountLookup, resolveShopDisplay } from '@/utils/shopDisplay'
import PageHeader from '@/components/common/PageHeader.vue'

// 响应式数据
const loading = ref(false)
const dashboardAssetNotice = ref(null)
const loadingKPI = ref(false)
const loadingComparison = ref(false)
const loadingInventory = ref(false)
let shopAccountLookup = new Map()

// 全局日期（页面级主控）
const globalGranularity = ref('monthly')
const globalDate = ref(
  (() => {
    const t = new Date()
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`
  })()
)

function clearDashboardAssetNotice() {
  dashboardAssetNotice.value = null
}

function setDashboardAssetNotice({ moduleName = '', status = 'warning', message = '', hint = null }) {
  const labels = {
    business_overview: '业务概览',
    clearance_ranking: '滞销清理排名'
  }
  dashboardAssetNotice.value = {
    title:
      status === 'refreshing'
        ? `${labels[moduleName] || 'Dashboard 模块'}数据刷新中`
        : `${labels[moduleName] || 'Dashboard 模块'}暂不可用`,
    description: [message, hint?.bootstrap_command ? `建议命令: ${hint.bootstrap_command}` : '']
      .filter(Boolean)
      .join(' '),
    type: status === 'refreshing' ? 'warning' : 'error'
  }
}

function consumeDashboardAssetError(error, fallbackModuleName = 'business_overview') {
  const info = getDashboardAssetUnavailableInfo(error)
  if (!info) return false
  setDashboardAssetNotice({
    moduleName: info.moduleName || fallbackModuleName,
    status: info.status,
    message: info.message,
    hint: info.hint
  })
  return true
}

async function refreshDashboardAssetNotice() {
  try {
    const payload = await api.getDashboardAssetsStatus()
    const modules = payload?.report?.modules || {}
    const blocked = [modules.business_overview, modules.clearance_ranking].filter(
      (moduleReport) => moduleReport && moduleReport.status && moduleReport.status !== 'ready'
    )
    if (!blocked.length) {
      clearDashboardAssetNotice()
      return
    }
    const primary = blocked[0]
    setDashboardAssetNotice({
      moduleName: primary.module_name,
      status: primary.status,
      message:
        primary.status === 'refreshing'
          ? 'Dashboard SQL 资产正在刷新，页面可能展示旧数据或局部空态。'
          : 'Dashboard SQL 资产未就绪，当前页面会降级展示。'
    })
  } catch (_error) {
    // Best-effort only; page can still rely on API-level error fallback.
  }
}
const useGlobalDate = ref({
  comparison: true,
  shopRacing: true,
  trafficRanking: true,
  inventory: true,
  operational: true,
  kpi: true, // 仅当全局为月时同步
  clearance: true // 月/周分别对齐
})
const _syncingFromGlobal = ref(false)
const _globalAutoRefreshReady = ref(false)

// 全局日期选择器类型与格式
const globalDatePickerType = computed(() => {
  if (globalGranularity.value === 'monthly') return 'month'
  if (globalGranularity.value === 'weekly') return 'week'
  return 'date'
})
const globalDatePickerFormat = computed(() => {
  if (globalGranularity.value === 'monthly') return 'YYYY-MM'
  if (globalGranularity.value === 'weekly') return 'YYYY 第 ww 周'
  return 'YYYY-MM-DD'
})
const globalDatePickerValueFormat = computed(() => {
  if (globalGranularity.value === 'monthly') return 'YYYY-MM'
  if (globalGranularity.value === 'weekly') return undefined
  return 'YYYY-MM-DD'
})
const globalDatePickerPlaceholder = computed(() => {
  if (globalGranularity.value === 'monthly') return '选择月份'
  if (globalGranularity.value === 'weekly') return '选择周'
  return '选择日期'
})

// 将全局日期转为 YYYY-MM-DD（用于数据对比、店铺赛马、流量排名）
function globalToDateStr() {
  const val = globalDate.value
  if (globalGranularity.value === 'monthly') {
    const s = typeof val === 'string' ? val : ''
    return s.length >= 7 ? `${s}-01` : ''
  }
  if (globalGranularity.value === 'weekly') {
    if (val instanceof Date && !Number.isNaN(val.getTime())) {
      const d = val
      const dayOfWeek = d.getDay()
      const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
      const mon = new Date(d)
      mon.setDate(d.getDate() + diff)
      const y = mon.getFullYear()
      const m = String(mon.getMonth() + 1).padStart(2, '0')
      const day = String(mon.getDate()).padStart(2, '0')
      return `${y}-${m}-${day}`
    }
    return ''
  }
  if (typeof val === 'string' && val.length >= 10) return val.substring(0, 10)
  if (val instanceof Date && !Number.isNaN(val.getTime())) {
    const y = val.getFullYear()
    const m = String(val.getMonth() + 1).padStart(2, '0')
    const d = String(val.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return ''
}

// 经营指标映射：日→所选日；周→周一；月→1日
function globalToOperationalDateStr() {
  const val = globalDate.value
  if (globalGranularity.value === 'monthly') {
    const s = typeof val === 'string' ? val : ''
    return s.length >= 7 ? `${s}-01` : ''
  }
  if (globalGranularity.value === 'weekly') {
    if (val instanceof Date && !Number.isNaN(val.getTime())) {
      const d = val
      const dayOfWeek = d.getDay()
      const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
      const mon = new Date(d)
      mon.setDate(d.getDate() + diff)
      const y = mon.getFullYear()
      const m = String(mon.getMonth() + 1).padStart(2, '0')
      const day = String(mon.getDate()).padStart(2, '0')
      return `${y}-${m}-${day}`
    }
    return ''
  }
  return globalToDateStr()
}

function normalizeAnchorDate(value, granularity) {
  const normalizedGranularity = String(granularity || '').trim().toLowerCase()
  if (typeof value === 'string') {
    if (normalizedGranularity === 'monthly') {
      return value.length >= 7 ? `${value.substring(0, 7)}-01` : ''
    }
    return value.length >= 10 ? value.substring(0, 10) : value
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const normalizedDate = new Date(value)
    if (normalizedGranularity === 'weekly') {
      const dayOfWeek = normalizedDate.getDay()
      const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
      normalizedDate.setDate(normalizedDate.getDate() + diff)
    } else if (normalizedGranularity === 'monthly') {
      normalizedDate.setDate(1)
    }
    const y = normalizedDate.getFullYear()
    const m = String(normalizedDate.getMonth() + 1).padStart(2, '0')
    const d = String(normalizedDate.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return ''
}

// 应用全局日期到各跟随模块
function applyGlobalToModules() {
  _syncingFromGlobal.value = true
  const dateStr = globalToDateStr()
  const opDateStr = globalToOperationalDateStr()
  const gr = globalGranularity.value

  if (useGlobalDate.value.comparison && dateStr) {
    comparisonGranularity.value = gr
    if (gr === 'monthly') {
      comparisonDate.value = globalDate.value
    } else if (gr === 'weekly') {
      const [y, m, d] = dateStr.split('-').map(Number)
      comparisonDate.value = new Date(y, m - 1, d)
    } else {
      comparisonDate.value = dateStr
    }
  }
  if (useGlobalDate.value.shopRacing && dateStr) {
    shopRacingGranularity.value = gr
    if (gr === 'monthly') {
      shopRacingDate.value = globalDate.value
    } else if (gr === 'weekly') {
      const [y, m, d] = dateStr.split('-').map(Number)
      shopRacingDate.value = new Date(y, m - 1, d)
    } else {
      shopRacingDate.value = dateStr
    }
  }
  if (useGlobalDate.value.trafficRanking && dateStr) {
    trafficRankingGranularity.value = gr
    if (gr === 'monthly') {
      trafficRankingDate.value = globalDate.value
    } else if (gr === 'weekly') {
      const [y, m, d] = dateStr.split('-').map(Number)
      trafficRankingDate.value = new Date(y, m - 1, d)
    } else {
      trafficRankingDate.value = dateStr
    }
  }
  if (useGlobalDate.value.operational && opDateStr) {
    operationalDate.value = opDateStr
  }
  if (useGlobalDate.value.kpi && dateStr) {
    kpiGranularity.value = gr
    if (gr === 'monthly') {
      const monthVal = globalDate.value
      if (typeof monthVal === 'string' && monthVal.length >= 7) {
        kpiMonth.value = `${monthVal}-01`
      }
    } else if (gr === 'weekly') {
      const [y, m, d] = dateStr.split('-').map(Number)
      kpiMonth.value = new Date(y, m - 1, d)
    } else {
      kpiMonth.value = dateStr
    }
  }
  // 清仓排名：仅当全局为月或周时同步（与 KPI 类似）
  if (useGlobalDate.value.clearance && (gr === 'monthly' || gr === 'weekly')) {
    if (gr === 'monthly' && dateStr) {
      const [y, m] = dateStr.split('-').map(Number)
      clearanceMonth.value = `${y}-${String(m).padStart(2, '0')}`
      clearanceWeek.value = new Date(y, m - 1, 1) // 月初 = 该月第一周
    } else if (gr === 'weekly' && dateStr) {
      const [y, m, d] = dateStr.split('-').map(Number)
      clearanceWeek.value = new Date(y, m - 1, d)
      clearanceMonth.value = `${y}-${String(m).padStart(2, '0')}`
    }
  }

  nextTick(() => {
    _syncingFromGlobal.value = false
  })
}

// 加载跟随全局的模块数据（防抖后调用）
let _globalDebounceTimer = null
function loadModulesAfterGlobalChange() {
  if (_globalDebounceTimer) clearTimeout(_globalDebounceTimer)
  _globalDebounceTimer = setTimeout(() => {
    _globalDebounceTimer = null
    const tasks = []
    const criticalFollowed =
      useGlobalDate.value.kpi &&
      useGlobalDate.value.comparison &&
      useGlobalDate.value.operational

    if (criticalFollowed) {
      tasks.push(loadCriticalTierBootstrap())
    } else {
      if (useGlobalDate.value.kpi) tasks.push(loadKPIData())
      if (useGlobalDate.value.comparison) tasks.push(loadComparisonData())
      if (useGlobalDate.value.operational) tasks.push(loadOperationalMetrics())
    }
    if (useGlobalDate.value.shopRacing) tasks.push(loadShopRacingData())
    if (useGlobalDate.value.trafficRanking) tasks.push(loadTrafficRanking())
    if (useGlobalDate.value.inventory) tasks.push(loadInventoryBacklog())
    if (useGlobalDate.value.clearance && (globalGranularity.value === 'monthly' || globalGranularity.value === 'weekly')) {
      tasks.push(loadClearanceRanking('monthly'))
      tasks.push(loadClearanceRanking('weekly'))
    }
    if (tasks.length) Promise.all(tasks).catch(() => {})
  }, 250)
}

async function refreshFollowedModules() {
  applyGlobalToModules()
  await nextTick()
  const tasks = []
  const criticalFollowed =
    useGlobalDate.value.kpi &&
    useGlobalDate.value.comparison &&
    useGlobalDate.value.operational

  if (criticalFollowed) {
    tasks.push(loadCriticalTierBootstrap())
  } else {
    if (useGlobalDate.value.kpi) tasks.push(loadKPIData())
    if (useGlobalDate.value.operational) tasks.push(loadOperationalMetrics())
    if (useGlobalDate.value.comparison) tasks.push(loadComparisonData())
  }
  if (useGlobalDate.value.shopRacing) tasks.push(loadShopRacingData())
  if (useGlobalDate.value.trafficRanking) tasks.push(loadTrafficRanking())
  if (useGlobalDate.value.inventory) tasks.push(loadInventoryBacklog())
  if (useGlobalDate.value.clearance && (globalGranularity.value === 'monthly' || globalGranularity.value === 'weekly')) {
    tasks.push(loadClearanceRanking('monthly'))
    tasks.push(loadClearanceRanking('weekly'))
  }
  if (tasks.length) {
    await Promise.allSettled(tasks)
  }
}

async function onGlobalGranularityChange() {
  useGlobalDate.value = {
    comparison: true,
    shopRacing: true,
    trafficRanking: true,
    inventory: true,
    operational: true,
    kpi: true,
    clearance: true
  }
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  if (globalGranularity.value === 'monthly') {
    globalDate.value = `${y}-${m}`
  } else if (globalGranularity.value === 'weekly') {
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(today)
    mon.setDate(today.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    globalDate.value = mon
  } else {
    globalDate.value = `${y}-${m}-${d}`
  }
  await refreshFollowedModules()
}

async function onGlobalDateChange() {
  useGlobalDate.value = {
    comparison: true,
    shopRacing: true,
    trafficRanking: true,
    inventory: true,
    operational: true,
    kpi: true,
    clearance: true
  }
  await refreshFollowedModules()
}

function syncModuleToGlobal(module) {
  useGlobalDate.value[module] = true
  applyGlobalToModules()
  if (module === 'comparison') loadComparisonData()
  else if (module === 'shopRacing') loadShopRacingData()
  else if (module === 'trafficRanking') loadTrafficRanking()
  else if (module === 'operational') loadOperationalMetrics()
  else if (module === 'kpi') loadKPIData()
  else if (module === 'clearance' && (globalGranularity.value === 'monthly' || globalGranularity.value === 'weekly')) {
    loadClearanceRanking('monthly')
    loadClearanceRanking('weekly')
  }
}

// KPI 筛选参数（默认与全局一致：当前月 YYYY-MM-01）
const kpiMonth = ref(
  (() => {
    const t = new Date()
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-01`
  })()
)
const kpiGranularity = ref('monthly')

const kpiDatePickerType = computed(() => {
  if (kpiGranularity.value === 'monthly') return 'month'
  if (kpiGranularity.value === 'weekly') return 'week'
  return 'date'
})
const kpiDatePickerFormat = computed(() => {
  if (kpiGranularity.value === 'monthly') return 'YYYY-MM'
  if (kpiGranularity.value === 'weekly') return 'YYYY 第 ww 周'
  return 'YYYY-MM-DD'
})
const kpiDatePickerPlaceholder = computed(() => {
  if (kpiGranularity.value === 'monthly') return '选择月份'
  if (kpiGranularity.value === 'weekly') return '选择周'
  return '选择日期'
})
const kpiDatePickerValueFormat = computed(() => {
  if (kpiGranularity.value === 'monthly') return 'YYYY-MM-01'
  if (kpiGranularity.value === 'weekly') return undefined
  return 'YYYY-MM-DD'
})
const kpiPlatform = ref('') // 默认全部平台

// KPI数据（7 张卡片：转化率、客流量、客单价、GMV、订单数、连带率、人效）
const kpiData = ref([
  {
    key: 'conversion_rate',
    title: '转化率',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'DataBoard',
    iconClass: 'kpi-conversion'
  },
  {
    key: 'traffic',
    title: '客流量',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'User',
    iconClass: 'kpi-traffic'
  },
  {
    key: 'average_order_value',
    title: '客单价',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'Money',
    iconClass: 'kpi-aov'
  },
  {
    key: 'gmv',
    title: 'GMV',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'Wallet',
    iconClass: 'kpi-gmv'
  },
  {
    key: 'order_count',
    title: '订单数',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'Document',
    iconClass: 'kpi-orders'
  },
  {
    key: 'attach_rate',
    title: '连带率',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'ShoppingCart',
    iconClass: 'kpi-attach'
  },
  {
    key: 'labor_efficiency',
    title: '人效',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'UserFilled',
    iconClass: 'kpi-labor'
  }
])

// 数据对比（默认跟随全局：月）
const comparisonChart = ref(null)
const comparisonGranularity = ref('monthly')
const comparisonDate = ref(
  (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })()
)
const comparisonData = ref({
  metrics: {},
  today: {},
  yesterday: {},
  average: {}
})

// 对比表格数据
const comparisonTableData = ref([])

// 目标达成率相关数据
const targetValue = ref(0)
const achievedValue = ref(0)
const targetAchievementRate = ref(0)
const targetUnit = ref("")

// 根据粒度计算列标题
const currentPeriodLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '本月'
  } else if (comparisonGranularity.value === 'weekly') {
    return '本周'
  } else {
    return '今日'
  }
})

const previousPeriodLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '上月'
  } else if (comparisonGranularity.value === 'weekly') {
    return '上周'
  } else {
    return '昨日'
  }
})

const averageLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '本月平均'
  } else if (comparisonGranularity.value === 'weekly') {
    return '本周平均'
  } else {
    return '本月平均'
  }
})

const targetProgressLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '月度目标达成率'
  } else if (comparisonGranularity.value === 'weekly') {
    return '周度目标达成率'
  } else {
    return '日度目标达成率'
  }
})

// 获取目标进度条颜色
const getTargetProgressColor = (percentage) => {
  if (percentage >= 100) return '#67C23A'
  if (percentage >= 80) return '#E6A23C'
  return '#F56C6C'
}

// 经营指标日期标签（动态显示）
const operationalDateLabel = computed(() => {
  if (!operationalDate.value) return '当月'
  const parts = operationalDate.value.split('-')
  if (parts.length >= 2) {
    const month = parseInt(parts[1], 10)
    return `${month}月`
  }
  return '当月'
})

// 根据粒度计算日期选择器类型和格式
const datePickerType = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return 'month' // 月份选择器
  } else if (comparisonGranularity.value === 'weekly') {
    return 'week' // 周选择器
  } else {
    return 'date' // 日期选择器
  }
})

const datePickerFormat = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return 'YYYY-MM'
  } else if (comparisonGranularity.value === 'weekly') {
    return 'YYYY 第 ww 周'
  } else {
    return 'YYYY-MM-DD'
  }
})

const datePickerPlaceholder = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '选择月份'
  } else if (comparisonGranularity.value === 'weekly') {
    return '选择周'
  } else {
    return '选择日期'
  }
})

// 数据对比日期 value-format：避免 toISOString() 的 UTC 偏差，传参使用本地 YYYY-MM-DD
// 注意：Element Plus 周选择器 (type="week") 不支持 YYYY-MM-DD 格式，需要特殊处理
const datePickerValueFormat = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return 'YYYY-MM'
  }
  // 周选择器：不设置 value-format，让它返回 Date 对象，在 loadComparisonData 中处理
  if (comparisonGranularity.value === 'weekly') {
    return undefined
  }
  return 'YYYY-MM-DD'
})

// 流量排名日期选择器类型和格式
const trafficRankingDatePickerType = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return 'month'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return 'week'
  } else {
    return 'date'
  }
})

const trafficRankingDatePickerFormat = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return 'YYYY-MM'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return 'YYYY-WW'
  } else {
    return 'YYYY-MM-DD'
  }
})

const trafficRankingDatePickerPlaceholder = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return '选择月份'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return '选择周'
  } else {
    return '选择日期'
  }
})
// 流量排名 value-format：避免 toISOString UTC 偏差
const trafficRankingDatePickerValueFormat = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') return 'YYYY-MM'
  if (trafficRankingGranularity.value === 'weekly') return undefined
  return 'YYYY-MM-DD'
})

// 数据对比：粒度/日期变更（用户手动修改时取消跟随全局）
const onComparisonGranularityChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.comparison = false
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  if (comparisonGranularity.value === 'monthly') {
    comparisonDate.value = `${y}-${m}`
  } else if (comparisonGranularity.value === 'weekly') {
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(today)
    mon.setDate(today.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    comparisonDate.value = mon
  } else {
    comparisonDate.value = `${y}-${m}-${d}`
  }
  loadComparisonData()
}
const onComparisonDateChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.comparison = false
  loadComparisonData()
}

const loadComparisonData = async () => {
  loadingComparison.value = true
  try {
    const dateStr = normalizeAnchorDate(comparisonDate.value, comparisonGranularity.value)
    if (!dateStr) {
      comparisonData.value = { metrics: {}, today: {}, yesterday: {}, average: {} }
      comparisonTableData.value = []
      targetValue.value = 0
      achievedValue.value = 0
      targetAchievementRate.value = 0
      targetUnit.value = ''
      return
    }

    const response = await api.getBusinessOverviewComparison({
      granularity: comparisonGranularity.value,
      period_key: dateStr,
      platform_code: kpiPlatform.value || undefined
    })

    const normalizedResponse = response || { metrics: {}, target: {} }
    comparisonData.value = normalizedResponse
    targetValue.value = Number(normalizedResponse.target?.sales_amount ?? 0)
    achievedValue.value = Number(normalizedResponse.metrics?.sales_amount?.today ?? 0)
    targetAchievementRate.value = Number(normalizedResponse.target?.achievement_rate ?? 0)
    targetUnit.value = ''
    updateComparisonTable()
  } catch (error) {
    console.error('加载数据对比失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
    comparisonData.value = { metrics: {}, today: {}, yesterday: {}, average: {} }
    comparisonTableData.value = []
    targetValue.value = 0
    achievedValue.value = 0
    targetAchievementRate.value = 0
    targetUnit.value = ''
  } finally {
    loadingComparison.value = false
  }
}

// 店铺赛马（独立日/周/月 + 日期，与数据对比约定一致）
const shopRacingGranularity = ref('monthly')
const shopRacingDate = ref(
  (() => {
    const t = new Date()
    const y = t.getFullYear()
    const m = String(t.getMonth() + 1).padStart(2, '0')
    return `${y}-${m}`
  })()
)
const shopRacingDatePickerType = computed(() => {
  if (shopRacingGranularity.value === 'monthly') return 'month'
  if (shopRacingGranularity.value === 'weekly') return 'week'
  return 'date'
})
const shopRacingDatePickerFormat = computed(() => {
  if (shopRacingGranularity.value === 'monthly') return 'YYYY-MM'
  if (shopRacingGranularity.value === 'weekly') return 'YYYY-WW'
  return 'YYYY-MM-DD'
})
const shopRacingDatePickerPlaceholder = computed(() => {
  if (shopRacingGranularity.value === 'monthly') return '选择月份'
  if (shopRacingGranularity.value === 'weekly') return '选择周'
  return '选择日期'
})
// 店铺赛马 value-format：避免 toISOString() 的 UTC 偏差，传参使用本地日期
const shopRacingDatePickerValueFormat = computed(() => {
  if (shopRacingGranularity.value === 'monthly') return 'YYYY-MM'
  if (shopRacingGranularity.value === 'weekly') return undefined // 周选择器返回 Date，在 loadShopRacingData 中处理
  return 'YYYY-MM-DD'
})
const onShopRacingGranularityChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.shopRacing = false
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  if (shopRacingGranularity.value === 'monthly') {
    shopRacingDate.value = `${y}-${m}`
  } else if (shopRacingGranularity.value === 'weekly') {
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(today)
    mon.setDate(today.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    shopRacingDate.value = mon
  } else {
    shopRacingDate.value = `${y}-${m}-${d}`
  }
  loadShopRacingData()
}
const onShopRacingDateChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.shopRacing = false
  loadShopRacingData()
}
const racingGroupBy = ref('shop')
const shopRacingData = ref([])
const loadingShopRacing = ref(false)
const unmatchedAliasDialogVisible = ref(false)
const unmatchedAliasDialogLoading = ref(false)
const unmatchedAliasRows = ref([])
const unmatchedAliasPlatform = ref('')

// 库存滞销
const inventorySummary = ref({
  total_value: 0,
  backlog_30d_value: 0,
  backlog_30d_ratio: 0,
  backlog_60d_value: 0,
  backlog_60d_ratio: 0,
  backlog_90d_value: 0,
  backlog_90d_ratio: 0,
  total_quantity: 0,
  backlog_30d_quantity: 0,
  backlog_60d_quantity: 0,
  backlog_90d_quantity: 0
})
const inventoryBacklogProducts = ref([])

// 流量排名数据（默认跟随全局：月）
const trafficRankingGranularity = ref('monthly')
const trafficRankingDimension = ref('shop')
const trafficRankingDate = ref(
  (() => {
    const t = new Date()
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`
  })()
)
const trafficRankingData = ref([])
const loadingTrafficRanking = ref(false)

const onTrafficRankingGranularityChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.trafficRanking = false
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  if (trafficRankingGranularity.value === 'monthly') {
    trafficRankingDate.value = `${y}-${m}`
  } else if (trafficRankingGranularity.value === 'weekly') {
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(today)
    mon.setDate(today.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    trafficRankingDate.value = mon
  } else {
    trafficRankingDate.value = `${y}-${m}-${d}`
  }
  loadTrafficRanking()
}
const onTrafficRankingDateChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.trafficRanking = false
  loadTrafficRanking()
}

// 滞销清理排名数据（默认与全局一致）
const loadingClearanceRanking = ref(false)
const monthlyClearanceRanking = ref([])
const weeklyClearanceRanking = ref([])
const clearanceMonth = ref(
  (() => {
    const t = new Date()
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`
  })()
)
const clearanceWeek = ref(
  (() => {
    const t = new Date()
    const dayOfWeek = t.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(t)
    mon.setDate(t.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    return mon
  })()
)

const onClearanceMonthChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.clearance = false
  loadClearanceRanking('monthly')
}
const onClearanceWeekChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.clearance = false
  loadClearanceRanking('weekly')
}

// 经营指标
const loadingOperational = ref(false)
// 经营指标日期选择器（默认今天，格式 YYYY-MM-DD 与 value-format 一致）
const operationalDate = ref(
  (() => {
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    return `${year}-${month}-01`
  })()
)
const operationalMetrics = ref({
  monthly_target: null,
  monthly_total_achieved: null,
  today_sales: null,
  monthly_achievement_rate: null,
  time_gap: null,
  estimated_gross_profit: null,
  estimated_expenses: null,
  operating_result: null,
  operating_result_text: '--',
  monthly_order_count: null,
  today_order_count: null
})
const operationalMeta = ref({
  expenses_source: null,
  warnings: []
})

// 图表实例
let comparisonChartInstance = null

// 使用统一的格式化函数（从dataFormatter导入）
const formatNumber = formatNumberUtil
const formatInteger = formatIntegerUtil
// formatPercent需要特殊处理：如果输入是0-1的小数，需要设置isDecimal=true
const formatPercent = (value, isDecimal = true) => {
  return formatPercentUtil(value, 2, '-', isDecimal)
}

const operationalExpensesTooltip = computed(() => {
  const source = operationalMeta.value?.expenses_source
  const warnings = Array.isArray(operationalMeta.value?.warnings)
    ? operationalMeta.value.warnings
    : []
  const hasPlatformExpenseGap = warnings.some((warning) =>
    String(warning).includes('estimated_expenses_missing_for_platform')
  )
  const sourceLabel =
    source === 'shop_month_rows_sum'
      ? '来源：经营成本表按平台+店铺+月份汇总。'
      : source === 'company_month_fallback_sum'
        ? '来源：经营成本表公司级月汇总兜底。'
        : source === null
          ? '来源：经营成本表。'
          : `来源：${source}。`
  const warningLabel = hasPlatformExpenseGap
    ? ' 警告：当前平台筛选下缺少费用归属数据，系统不会回退到全公司费用。'
    : warnings.length
      ? ` 警告：${warnings.join('；')}`
      : ''
  return `${sourceLabel} 口径：租金+营销费用+水电费+AI Token费用+其他成本。${warningLabel}`
})

// 获取变化类型
const getChangeType = (change) => {
  if (change === null || change === undefined) return 'neutral'
  const num = Number(change)
  if (num > 0) return 'increase'
  if (num < 0) return 'decrease'
  return 'neutral'
}

// 获取变化图标
const getChangeIcon = (change) => {
  const num = Number(change)
  if (num > 0) return 'ArrowUp'
  if (num < 0) return 'ArrowDown'
  return 'Minus'
}

// 获取完成率颜色
const getAchievementColor = (rate) => {
  if (rate >= 1.0) return '#67C23A'
  if (rate >= 0.8) return '#E6A23C'
  return '#F56C6C'
}

// 获取滞销天数标签类型
const getAgeTagType = (days) => {
  if (days >= 90) return 'danger'
  if (days >= 60) return 'warning'
  return 'info'
}

// 获取分类标签类型
const getCategoryTagType = (category) => {
  if (category === '90天+') return 'danger'
  if (category === '60-90天') return 'warning'
  if (category === '30-60天') return 'info'
  return 'primary'
}

// 获取达成率标签类型
const getAchievementRateTagType = (rate) => {
  if (rate === null || rate === undefined || Number.isNaN(Number(rate))) return 'info'
  if (rate >= 100) return 'success'
  if (rate >= 80) return 'warning'
  return 'danger'
}

// 获取时间GAP标签类型
const getTimeGapTagType = (gap) => {
  if (gap === null || gap === undefined || Number.isNaN(Number(gap))) return 'info'
  if (gap > 0) return 'success'
  if (gap < 0) return 'danger'
  return 'info'
}

const getOperatingResultTagType = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'info'
  return Number(value) >= 0 ? 'success' : 'danger'
}

const formatNullablePercent = (value, decimals = 2) =>
  value != null && !Number.isNaN(Number(value)) ? `${Number(value).toFixed(decimals)}%` : '--'

// 核心KPI 筛选变化时同时刷新 KPI 与经营指标
const onKpiMonthChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.kpi = false
  loadKPIData()
}

const onKpiGranularityChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.kpi = false
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  if (kpiGranularity.value === 'monthly') {
    kpiMonth.value = `${y}-${m}-01`
  } else if (kpiGranularity.value === 'weekly') {
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const mon = new Date(today)
    mon.setDate(today.getDate() + diff)
    mon.setHours(0, 0, 0, 0)
    kpiMonth.value = mon
  } else {
    kpiMonth.value = `${y}-${m}-${d}`
  }
  loadKPIData()
}

const onKpiFilterChange = () => {
  loadKPIData()
}

// 加载KPI数据
const loadKPIData = async () => {
  loadingKPI.value = true
  try {
    let kpiDateStr = ''
    if (kpiMonth.value) {
      if (typeof kpiMonth.value === 'string') {
        kpiDateStr = kpiMonth.value
      } else if (kpiMonth.value instanceof Date && !Number.isNaN(kpiMonth.value.getTime())) {
        let date = kpiMonth.value
        if (kpiGranularity.value === 'weekly') {
          const dayOfWeek = date.getDay()
          const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
          date = new Date(date)
          date.setDate(date.getDate() + diff)
        }
        const year = date.getFullYear()
        const month = String(date.getMonth() + 1).padStart(2, '0')
        const day = String(date.getDate()).padStart(2, '0')
        kpiDateStr = `${year}-${month}-${day}`
      }
    }
    if (kpiGranularity.value === 'monthly' && kpiDateStr.length === 7) {
      kpiDateStr = `${kpiDateStr}-01`
    }

    const response = await api.getBusinessOverviewKPI({
      granularity: kpiGranularity.value,
      period_key: kpiDateStr,
      platform_code: kpiPlatform.value || undefined
    })

    if (response) {
      const data = response
      const formatChange = (num) => {
        if (num === null || num === undefined) return '--'
        const n = Number(num)
        if (Number.isNaN(n)) return '--'
        return (n > 0 ? '+' : '') + n.toFixed(2) + '%'
      }
      const showValue = (v, formatter) =>
        v != null && v !== '' ? formatter(Number(v)) : '--'

      const conversionRate = data.conversion_rate
      kpiData.value[0].value = showValue(conversionRate, (n) => `${n.toFixed(2)}%`)
      kpiData.value[0].change = formatChange(data.conversion_rate_change)
      kpiData.value[0].changeType = getChangeType(data.conversion_rate_change)
      kpiData.value[0].changeIcon = getChangeIcon(data.conversion_rate_change)

      const visitorCount = data.visitor_count ?? data.traffic?.current
      kpiData.value[1].value = showValue(visitorCount, (n) => formatInteger(n))
      kpiData.value[1].change = formatChange(data.visitor_count_change)
      kpiData.value[1].changeType = getChangeType(data.visitor_count_change)
      kpiData.value[1].changeIcon = getChangeIcon(data.visitor_count_change)

      const avgOrderValue = data.avg_order_value ?? data.average_order_value?.current
      kpiData.value[2].value = showValue(avgOrderValue, (n) => formatCurrency(n))
      kpiData.value[2].change = formatChange(data.avg_order_value_change)
      kpiData.value[2].changeType = getChangeType(data.avg_order_value_change)
      kpiData.value[2].changeIcon = getChangeIcon(data.avg_order_value_change)

      const gmv = data.gmv
      kpiData.value[3].value = showValue(gmv, (n) => formatCurrency(n))
      kpiData.value[3].change = formatChange(data.gmv_change)
      kpiData.value[3].changeType = getChangeType(data.gmv_change)
      kpiData.value[3].changeIcon = getChangeIcon(data.gmv_change)

      const orderCount = data.order_count
      kpiData.value[4].value = showValue(orderCount, (n) => formatInteger(n))
      kpiData.value[4].change = formatChange(data.order_count_change)
      kpiData.value[4].changeType = getChangeType(data.order_count_change)
      kpiData.value[4].changeIcon = getChangeIcon(data.order_count_change)

      const attachRate = data.attach_rate ?? data.attach_rate_obj?.current
      kpiData.value[5].value = showValue(attachRate, (n) => n.toFixed(2))
      kpiData.value[5].change = formatChange(data.attach_rate_change ?? data.attach_rate_obj?.change)
      kpiData.value[5].changeType = getChangeType(data.attach_rate_change ?? data.attach_rate_obj?.change)
      kpiData.value[5].changeIcon = getChangeIcon(data.attach_rate_change ?? data.attach_rate_obj?.change)

      const laborEfficiency = data.labor_efficiency ?? data.labor_efficiency_obj?.current
      kpiData.value[6].value = showValue(laborEfficiency, (n) => formatCurrency(n))
      kpiData.value[6].change = formatChange(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
      kpiData.value[6].changeType = getChangeType(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
      kpiData.value[6].changeIcon = getChangeIcon(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
    }
  } catch (error) {
    console.error('??KPI????:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    loadingKPI.value = false
  }
}

function getMetric(metricsObj, key) {
  if (!metricsObj || typeof metricsObj !== 'object') return {}
  if (Object.prototype.hasOwnProperty.call(metricsObj, key)) return metricsObj[key] || {}
  const lower = key.toLowerCase()
  for (const [k, v] of Object.entries(metricsObj)) {
    if (k != null && String(k).toLowerCase() === lower) return v || {}
  }
  return {}
}

// 更新对比表格
const updateComparisonTable = () => {
  const data = comparisonData.value || {}
  const tableData = []

  // 即使数据为空，也显示所有指标行（前端设计优先）
  const metrics =
    data && typeof data.metrics === 'object' && !Array.isArray(data.metrics)
      ? data.metrics
      : {}

  // 环比百分比安全格式化（null/NaN 显示 --，避免 .toFixed 报错）
  const safeChangePct = (v) => {
    if (v == null || Number.isNaN(Number(v))) return '--'
    const n = Number(v)
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
  }
  // 数值安全格式化后 toFixed（null/NaN 显示 --）
  const safeToFixed = (v, decimals = 2) =>
    v != null && !Number.isNaN(Number(v)) ? Number(v).toFixed(decimals) : '--'

  // 销售额
  const salesAmount = getMetric(metrics, 'sales_amount')
  tableData.push({
    metric: '销售额',
    today:
      salesAmount.today !== undefined && salesAmount.today !== null ? formatNumber(salesAmount.today) : '--',
    yesterday:
      salesAmount.yesterday !== undefined && salesAmount.yesterday !== null
        ? formatNumber(salesAmount.yesterday)
        : '--',
    average:
      salesAmount.average !== undefined && salesAmount.average !== null
        ? formatNumber(salesAmount.average)
        : '--',
    change: safeChangePct(salesAmount.change),
    changeType: salesAmount.change_type || 'neutral',
    changeClass: salesAmount.change_type || 'neutral',
    todayClass: ''
  })

  // 出库数量
  const salesQty = getMetric(metrics, 'sales_quantity')
  tableData.push({
    metric: '出库数量',
    today: salesQty.today != null ? formatInteger(salesQty.today) : '--',
    yesterday:
      salesQty.yesterday != null ? formatInteger(salesQty.yesterday) : '--',
    average: salesQty.average != null ? formatInteger(salesQty.average) : '--',
    change: safeChangePct(salesQty.change),
    changeType: salesQty.change_type || 'neutral',
    changeClass: salesQty.change_type || 'neutral',
    todayClass: ''
  })

  // 客流量
  const traffic = getMetric(metrics, 'traffic')
  tableData.push({
    metric: '客流量',
    today: traffic.today != null ? formatInteger(traffic.today) : '--',
    yesterday: traffic.yesterday != null ? formatInteger(traffic.yesterday) : '--',
    average: traffic.average != null ? formatInteger(traffic.average) : '--',
    change: safeChangePct(traffic.change),
    changeType: traffic.change_type || 'neutral',
    changeClass: traffic.change_type || 'neutral',
    todayClass: ''
  })

  // 转化率（百分比需带 %）
  const conversion = getMetric(metrics, 'conversion_rate')
  const conversionToday = conversion.today
  const conversionAvg = conversion.average
  const pct = (v) => (v != null && !Number.isNaN(Number(v))) ? `${Number(v).toFixed(2)}%` : '--'
  tableData.push({
    metric: '转化率',
    today: pct(conversionToday),
    yesterday: pct(conversion.yesterday),
    average: pct(conversionAvg),
    change: safeChangePct(conversion.change),
    changeType: conversion.change_type || 'neutral',
    changeClass: conversion.change_type || 'neutral',
    todayClass: conversionToday > conversionAvg ? 'highlight-positive' : ''
  })

  // 客单价
  const aov = getMetric(metrics, 'avg_order_value')
  const aovToday = aov.today
  const aovAvg = aov.average
  tableData.push({
    metric: '客单价',
    today: aovToday != null ? formatInteger(aovToday) : '--',
    yesterday: aov.yesterday != null ? formatInteger(aov.yesterday) : '--',
    average: aovAvg != null ? formatInteger(aovAvg) : '--',
    change: safeChangePct(aov.change),
    changeType: aov.change_type || 'neutral',
    changeClass: aov.change_type || 'neutral',
    todayClass: aovToday > aovAvg ? 'highlight-positive' : ''
  })

  // 连带率
  const attach = getMetric(metrics, 'attach_rate')
  const attachToday = attach.today
  const attachAvg = attach.average
  tableData.push({
    metric: '连带率',
    today: safeToFixed(attachToday),
    yesterday: safeToFixed(attach.yesterday),
    average: safeToFixed(attachAvg),
    change: safeChangePct(attach.change),
    changeType: attach.change_type || 'neutral',
    changeClass: attach.change_type || 'neutral',
    todayClass: attachToday > attachAvg ? 'highlight-positive' : ''
  })

  // 利润
  const profit = getMetric(metrics, 'profit')
  tableData.push({
    metric: '利润',
    today: profit.today != null ? formatNumber(profit.today) : '--',
    yesterday: profit.yesterday != null ? formatNumber(profit.yesterday) : '--',
    average: profit.average != null ? formatNumber(profit.average) : '--',
    change: safeChangePct(profit.change),
    changeType: profit.change_type || 'neutral',
    changeClass: profit.change_type || 'neutral',
    todayClass: ''
  })

  console.log('表格数据:', tableData) // 调试信息
  console.log('表格数据长度:', tableData.length) // 调试信息
  comparisonTableData.value = tableData
  console.log(
    'comparisonTableData.value 已设置:',
    comparisonTableData.value.length,
    '行'
  )
}

// 更新对比图表（保留，但暂时不使用）
const updateComparisonChart = () => {
  // 暂时不使用图表，使用表格展示
  updateComparisonTable()
}

// 加载店铺赛马数据（使用独立粒度+日期，与数据对比约定一致）
// 使用本地日期拼接，避免 toISOString() 的 UTC 偏差
const loadShopRacingData = async () => {
  loadingShopRacing.value = true
  try {
    let dateStr = ''
    const val = shopRacingDate.value
    if (typeof val === 'string') {
      dateStr = val.length === 7 ? `${val}-01` : val
    } else if (val instanceof Date && !Number.isNaN(val.getTime())) {
      // 周选择器返回 Date（无 value-format），用本地日期拼接避免 UTC 偏差
      let d = val
      if (shopRacingGranularity.value === 'weekly') {
        const dayOfWeek = d.getDay()
        const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
        d = new Date(d)
        d.setDate(d.getDate() + diff)
      }
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      dateStr = `${y}-${m}-${day}`
    }
    if (!dateStr) {
      shopRacingData.value = []
      return
    }

    const response = await api.getBusinessOverviewShopRacing({
      granularity: shopRacingGranularity.value,
      period_key: dateStr,
      group_by: racingGroupBy.value,
      platform_code: kpiPlatform.value || undefined
    })

    // 后端已转为 { name, target, achieved, achievement_rate, rank } 数组
    if (response && Array.isArray(response)) {
      shopRacingData.value = response.map((row) => {
        const displayMeta = resolveShopDisplay(row, shopAccountLookup)
        return {
          ...row,
          name: displayMeta.display_name,
          secondary_name: displayMeta.secondary_name,
          target: row.target_amount ?? null,
          achieved: row.gmv ?? null,
          achievement_rate:
            row.achievement_rate == null
              ? 0
              : Number(row.achievement_rate) > 1
                ? Number(row.achievement_rate) / 100
                : Number(row.achievement_rate)
        }
      })
    } else {
      shopRacingData.value = []
    }
  } catch (error) {
    console.error('加载店铺赛马数据失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
    shopRacingData.value = []
  } finally {
    loadingShopRacing.value = false
  }
}

function isUnmatchedShopRow(row) {
  return Boolean(row && (row.is_unmatched || row.name === '未匹配店铺'))
}

async function showUnmatchedAliasDialog(row) {
  unmatchedAliasDialogVisible.value = true
  unmatchedAliasDialogLoading.value = true
  unmatchedAliasPlatform.value = row?.platform_code || ''
  try {
    const response = await accountsApi.getUnmatchedShopAliases()
    const items = Array.isArray(response?.items) ? response.items : []
    unmatchedAliasRows.value = items.filter((item) => {
      if (!unmatchedAliasPlatform.value) return true
      return String(item.platform || '').toLowerCase() === String(unmatchedAliasPlatform.value || '').toLowerCase()
    })
  } catch (error) {
    console.error('加载未匹配店铺别名失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
    unmatchedAliasRows.value = []
  } finally {
    unmatchedAliasDialogLoading.value = false
  }
}

async function loadShopDisplayLookup() {
  try {
    const response = await accountsApi.listShopAccounts({ enabled: true })
    shopAccountLookup = buildShopAccountLookup(Array.isArray(response) ? response : [])
  } catch (error) {
    console.error('加载店铺显示映射失败:', error)
    shopAccountLookup = new Map()
  }
}

const onOperationalDateChange = () => {
  if (!_syncingFromGlobal.value) useGlobalDate.value.operational = false
  loadOperationalMetrics()
}

// 加载经营指标数据（使用独立的日期选择器）
const loadOperationalMetrics = async () => {
  loadingOperational.value = true
  try {
    // operationalDate 已经是 YYYY-MM-DD 格式的字符串（由 value-format 保证）
    const response = await api.getBusinessOverviewOperationalMetrics({
      granularity: 'monthly',
      period_key: operationalDate.value || undefined,
      platform_code: kpiPlatform.value || undefined
    })

    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      operationalMeta.value = {
        expenses_source: response.meta?.expenses_source ?? null,
        warnings: Array.isArray(response.meta?.warnings) ? response.meta.warnings : []
      }
      operationalMetrics.value = {
        monthly_target: response.monthly_target ?? null,
        monthly_total_achieved: response.monthly_total_achieved ?? null,
        today_sales: response.today_sales ?? response.monthly_total_achieved ?? null,
        monthly_achievement_rate: response.monthly_achievement_rate ?? null,
        time_gap: response.time_gap ?? null,
        estimated_gross_profit: response.estimated_gross_profit ?? null,
        estimated_expenses: response.estimated_expenses ?? null,
        operating_result: response.operating_result ?? null,
        operating_result_text: response.operating_result_text ?? '--',
        monthly_order_count: response.monthly_order_count ?? null,
        today_order_count: response.today_order_count ?? response.monthly_order_count ?? null
      }
    }
  } catch (error) {
    console.error('加载经营指标数据失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    loadingOperational.value = false
  }
}

// 加载流量排名（使用本地日期拼接，避免 toISOString UTC 偏差）
const loadTrafficRanking = async () => {
  loadingTrafficRanking.value = true
  try {
    let dateStr = ''
    const val = trafficRankingDate.value
    const gr = trafficRankingGranularity.value
    if (typeof val === 'string') {
      dateStr = val.length === 7 ? `${val}-01` : val.substring(0, 10)
    } else if (val instanceof Date && !Number.isNaN(val.getTime())) {
      let d = val
      if (gr === 'weekly') {
        const dayOfWeek = d.getDay()
        const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
        d = new Date(d)
        d.setDate(d.getDate() + diff)
      }
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      dateStr = `${y}-${m}-${day}`
    }
    if (!dateStr) {
      trafficRankingData.value = []
      return
    }

    const params = {
      granularity: gr,
      dimension: trafficRankingDimension.value,
      period_key: dateStr
    }
    if (kpiPlatform.value) params.platform_code = kpiPlatform.value

    const response = await api.getBusinessOverviewTrafficRanking(params)

    // 响应拦截器已处理 success 字段，后端已转英文 key；兜底映射兼容中文列名
    const raw = response || []
    const rows = Array.isArray(raw) ? raw : (raw.data || [])
    trafficRankingData.value = rows.map((row, index) => {
      const displayMeta = resolveShopDisplay(row, shopAccountLookup)
      return {
        rank: row.rank ?? row['排名'] ?? index + 1,
        name: displayMeta.display_name,
        secondary_name: displayMeta.secondary_name,
        platform_code: row.platform_code ?? row['平台'],
        shop_id: row.shop_id ?? null,
        shop_account_id: row.shop_account_id ?? null,
        main_account_id: row.main_account_id ?? null,
        main_account_name: row.main_account_name ?? null,
        is_unmatched: Boolean(row.is_unmatched),
        visitor_count: row.visitor_count ?? row.unique_visitors ?? row['访客数'] ?? 0,
        page_views: row.page_views ?? row['浏览量'] ?? 0,
        uv_change_rate: row.uv_change_rate ?? null,
        pv_change_rate: row.pv_change_rate ?? null,
        compare_visitor_count: row.compare_visitor_count ?? row.compare_unique_visitors ?? null,
        compare_page_views: row.compare_page_views ?? null
      }
    })
  } catch (error) {
    console.error('加载流量排名失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    loadingTrafficRanking.value = false
  }
}

// 加载库存滞销数据
const loadInventoryBacklog = async () => {
  loadingInventory.value = true
  try {
    const targetDate = normalizeAnchorDate(globalDate.value, globalGranularity.value)
    const response = await api.getBusinessOverviewInventoryBacklog({
      limit: 20,
      granularity: globalGranularity.value,
      date: targetDate || undefined
    })

    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      inventorySummary.value = response.summary || inventorySummary.value
      inventoryBacklogProducts.value = response.top_products || []
    }
  } catch (error) {
    console.error('加载库存滞销数据失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    loadingInventory.value = false
  }
}

// 加载滞销清理排名（clearanceMonth 支持 YYYY-MM 字符串，clearanceWeek 支持 YYYY-MM-DD 字符串或 Date）
const loadClearanceRanking = async (granularity) => {
  loadingClearanceRanking.value = true
  try {
    const params = {}
    if (granularity === 'monthly' && clearanceMonth.value) {
      params.date = normalizeAnchorDate(clearanceMonth.value, 'monthly')
    }
    if (granularity === 'weekly' && clearanceWeek.value) {
      params.date = normalizeAnchorDate(clearanceWeek.value, 'weekly')
    }

    params.granularity = granularity
    params.limit = 10

    // 响应拦截器已处理success字段，直接使用data
    const response = await api.getClearanceRanking(params)

    const rankingRows = normalizeClearanceRankingResponse(response)

    if (granularity === 'monthly') {
      monthlyClearanceRanking.value = rankingRows
    } else {
      weeklyClearanceRanking.value = rankingRows
    }
  } catch (error) {
    console.error('加载滞销清理排名失败:', error)
    if (!consumeDashboardAssetError(error, 'clearance_ranking')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    loadingClearanceRanking.value = false
  }
}

// 获取周数辅助函数
const getWeekNumber = (date) => {
  const d = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  )
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7)
}

const loadCriticalTierBootstrap = async () => {
  loadingKPI.value = true
  loadingComparison.value = true
  loadingOperational.value = true
  try {
    const dateStr = globalToDateStr()
    const monthStr = globalToOperationalDateStr()
    const periodKey = dateStr || monthStr
    const payload = await api.getBusinessOverviewBootstrap({
      granularity: globalGranularity.value,
      period_key: periodKey || undefined,
      platform_code: kpiPlatform.value || undefined
    })

    const applyKpiPayload = (data) => {
      if (!data) return
      const formatChange = (num) => {
        if (num === null || num === undefined) return '--'
        const n = Number(num)
        if (Number.isNaN(n)) return '--'
        return (n > 0 ? '+' : '') + n.toFixed(2) + '%'
      }
      const showValue = (v, formatter) =>
        v != null && v !== '' ? formatter(Number(v)) : '--'

      const conversionRate = data.conversion_rate
      kpiData.value[0].value = showValue(conversionRate, (n) => `${n.toFixed(2)}%`)
      kpiData.value[0].change = formatChange(data.conversion_rate_change)
      kpiData.value[0].changeType = getChangeType(data.conversion_rate_change)
      kpiData.value[0].changeIcon = getChangeIcon(data.conversion_rate_change)

      const visitorCount = data.visitor_count ?? data.traffic?.current
      kpiData.value[1].value = showValue(visitorCount, (n) => formatInteger(n))
      kpiData.value[1].change = formatChange(data.visitor_count_change)
      kpiData.value[1].changeType = getChangeType(data.visitor_count_change)
      kpiData.value[1].changeIcon = getChangeIcon(data.visitor_count_change)

      const avgOrderValue = data.avg_order_value ?? data.average_order_value?.current
      kpiData.value[2].value = showValue(avgOrderValue, (n) => formatCurrency(n))
      kpiData.value[2].change = formatChange(data.avg_order_value_change)
      kpiData.value[2].changeType = getChangeType(data.avg_order_value_change)
      kpiData.value[2].changeIcon = getChangeIcon(data.avg_order_value_change)

      const gmv = data.gmv
      kpiData.value[3].value = showValue(gmv, (n) => formatCurrency(n))
      kpiData.value[3].change = formatChange(data.gmv_change)
      kpiData.value[3].changeType = getChangeType(data.gmv_change)
      kpiData.value[3].changeIcon = getChangeIcon(data.gmv_change)

      const orderCount = data.order_count
      kpiData.value[4].value = showValue(orderCount, (n) => formatInteger(n))
      kpiData.value[4].change = formatChange(data.order_count_change)
      kpiData.value[4].changeType = getChangeType(data.order_count_change)
      kpiData.value[4].changeIcon = getChangeIcon(data.order_count_change)

      const attachRate = data.attach_rate ?? data.attach_rate_obj?.current
      kpiData.value[5].value = showValue(attachRate, (n) => n.toFixed(2))
      kpiData.value[5].change = formatChange(data.attach_rate_change ?? data.attach_rate_obj?.change)
      kpiData.value[5].changeType = getChangeType(data.attach_rate_change ?? data.attach_rate_obj?.change)
      kpiData.value[5].changeIcon = getChangeIcon(data.attach_rate_change ?? data.attach_rate_obj?.change)

      const laborEfficiency = data.labor_efficiency ?? data.labor_efficiency_obj?.current
      kpiData.value[6].value = showValue(laborEfficiency, (n) => formatCurrency(n))
      kpiData.value[6].change = formatChange(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
      kpiData.value[6].changeType = getChangeType(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
      kpiData.value[6].changeIcon = getChangeIcon(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
    }

    const applyComparisonPayload = (data) => {
      if (!data) return
      const normalizedResponse = data || { metrics: {}, target: {} }
      comparisonData.value = normalizedResponse
      targetValue.value = Number(normalizedResponse.target?.sales_amount ?? 0)
      achievedValue.value = Number(normalizedResponse.metrics?.sales_amount?.today ?? 0)
      targetAchievementRate.value = Number(normalizedResponse.target?.achievement_rate ?? 0)
      targetUnit.value = ''
      updateComparisonTable()
    }

    const applyOperationalPayload = (data) => {
      if (!data) return
      operationalMeta.value = {
        expenses_source: data.meta?.expenses_source ?? null,
        warnings: Array.isArray(data.meta?.warnings) ? data.meta.warnings : []
      }
      operationalMetrics.value = {
        monthly_target: data.monthly_target ?? null,
        monthly_total_achieved: data.monthly_total_achieved ?? null,
        today_sales: data.today_sales ?? data.monthly_total_achieved ?? null,
        monthly_achievement_rate: data.monthly_achievement_rate ?? null,
        time_gap: data.time_gap ?? null,
        estimated_gross_profit: data.estimated_gross_profit ?? null,
        estimated_expenses: data.estimated_expenses ?? null,
        operating_result: data.operating_result ?? null,
        operating_result_text: data.operating_result_text ?? '--',
        monthly_order_count: data.monthly_order_count ?? null,
        today_order_count: data.today_order_count ?? data.monthly_order_count ?? null
      }
    }

    applyKpiPayload(payload?.kpi)
    applyComparisonPayload(payload?.comparison)
    applyOperationalPayload(payload?.operational_metrics)
  } catch (error) {
    console.error('[BusinessOverview] bootstrap 加载失败:', error)
    if (!consumeDashboardAssetError(error, 'business_overview')) {
      handleApiError(error, { showMessage: true, logError: true })
    }
    await Promise.allSettled([
      loadKPIData(),
      loadComparisonData(),
      loadOperationalMetrics()
    ])
  } finally {
    loadingKPI.value = false
    loadingComparison.value = false
    loadingOperational.value = false
  }
}

const refreshData = async () => {
  loading.value = true
  try {
    await refreshDashboardAssetNotice()
    applyGlobalToModules()
    await loadCriticalTierBootstrap()
    const results = await Promise.allSettled([
      loadShopRacingData(),
      loadTrafficRanking(),
      loadInventoryBacklog(),
      loadClearanceRanking('monthly'),
      loadClearanceRanking('weekly')
    ])

    const failedResults = results.filter((result) => result.status === 'rejected')
    if (failedResults.length > 0) {
      console.warn('[BusinessOverview] 部分模块刷新失败，但页面已保留可用数据', failedResults)
      if (!dashboardAssetNotice.value) {
        ElMessage.warning('部分模块刷新失败，已显示可用数据')
      }
      return
    }

    ElMessage.success('数据刷新成功')
  } finally {
    loading.value = false
  }
}

// 生命周期：先应用全局日期到各模块，再加载数据（避免默认值加载后又被全局覆盖导致重复请求）
onMounted(() => {
  updateComparisonTable()
  applyGlobalToModules()
  _globalAutoRefreshReady.value = true
  loadShopDisplayLookup().finally(() => {
    refreshData()
  })
})

watch(
  () => globalGranularity.value,
  async () => {
    if (!_globalAutoRefreshReady.value) return
    useGlobalDate.value = {
      comparison: true,
      shopRacing: true,
      trafficRanking: true,
      inventory: true,
      operational: true,
      kpi: true,
      clearance: true
    }
    await nextTick()
    refreshData()
  }
)

watch(
  () => globalDate.value,
  async () => {
    if (!_globalAutoRefreshReady.value) return
    useGlobalDate.value = {
      comparison: true,
      shopRacing: true,
      trafficRanking: true,
      inventory: true,
      operational: true,
      kpi: true,
      clearance: true
    }
    await nextTick()
    refreshData()
  }
)
</script>

<style scoped>
.business-overview {
  background-color: #f5f7fa;
  min-height: calc(100vh - var(--header-height));
}

.global-date-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding: 12px 16px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.dashboard-asset-alert {
  margin-bottom: 16px;
}

.global-date-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-right: 4px;
}

.global-date-picker {
  width: 150px;
}

.control-w-120 {
  width: 120px;
}

.control-w-140 {
  width: 140px;
}

.control-w-150 {
  width: 150px;
}

.control-w-160 {
  width: 160px;
}

.control-offset {
  margin-left: 12px;
}

.kpi-section {
  margin-bottom: 24px;
}

.kpi-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.filter-label {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-right: 8px;
}

.kpi-cards {
  /* margin-bottom: 24px; */
}

/* 大屏下 5 张 KPI 卡片等分一行，避免右侧留空（与 el-col :lg 断点一致） */
@media (min-width: 1200px) {
  .kpi-cards-row.el-row {
    display: flex;
    flex-wrap: nowrap;
  }
  .kpi-cards-row .el-col {
    flex: 1 1 0%;
    min-width: 0;
    max-width: none;
  }
}

.kpi-card {
  border: none;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
}

.kpi-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
}

.kpi-icon.kpi-conversion {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.kpi-icon.kpi-traffic {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.kpi-icon.kpi-aov {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.kpi-icon.kpi-attach {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.kpi-icon.kpi-labor {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.kpi-icon.kpi-orders {
  background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
}

.kpi-icon.kpi-gmv {
  background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
}

.kpi-info {
  flex: 1;
}

.kpi-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.kpi-change {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.kpi-change.increase {
  color: #67c23a;
}

.kpi-change.decrease {
  color: #f56c6c;
}

.kpi-change.neutral {
  color: #909399;
}

.comparison-section {
  margin-bottom: 24px;
}

.chart-card {
  border: none;
  border-radius: 12px;
  overflow: hidden;
}

.traffic-ranking-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chart-container {
  min-height: 400px;
}

.target-progress-section {
  margin-bottom: 20px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.target-progress-item {
  width: 100%;
}

.target-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.target-details {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.comparison-table-container {
  padding: 10px 0;
}

.change-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.increase-icon {
  color: #67c23a;
}

.decrease-icon {
  color: #f56c6c;
}

.neutral-icon {
  color: #909399;
}

.change-indicator .increase {
  color: #67c23a;
}

.change-indicator .decrease {
  color: #f56c6c;
}

.change-indicator .neutral {
  color: #909399;
}

.highlight-positive {
  color: #67c23a;
  font-weight: 600;
}

.chart {
  width: 100%;
  height: 100%;
}

.racing-container {
  max-height: 400px;
  overflow-y: auto;
}

.shop-display-cell {
  line-height: 1.4;
}

.shop-display-secondary {
  font-size: 12px;
  color: #909399;
}

.operational-metrics-section {
  margin-bottom: 24px;
}

.operational-metrics-grid {
  padding: 10px 0;
  display: grid;
  grid-template-columns: repeat(4, 1fr) 88px;
  grid-template-rows: auto auto;
  gap: 16px;
}

.metrics-row {
  display: contents;
}

.metrics-row .metric-item {
  margin-bottom: 0;
}

.metric-item {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  text-align: center;
}

/* 经营结果：最右侧竖状，跨两行 */
.metric-item.metric-result-vertical {
  grid-column: 5;
  grid-row: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.metric-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

@media (max-width: 1200px) {
  .operational-metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .metric-item.metric-result-vertical {
    grid-column: 1 / -1;
    grid-row: auto;
    min-height: auto;
  }
}

@media (max-width: 768px) {
  .operational-metrics-grid {
    grid-template-columns: 1fr;
  }
  .metric-item.metric-result-vertical {
    grid-column: 1;
    grid-row: auto;
  }
}

.inventory-summary {
  margin-bottom: 20px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
}

.summary-item {
  text-align: center;
}

.summary-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.summary-value.danger {
  color: #f56c6c;
}

.summary-value.warning {
  color: #e6a23c;
}

.summary-ratio {
  font-size: 12px;
  color: #909399;
}

.inventory-table {
  margin-top: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .kpi-content {
    flex-direction: column;
    text-align: center;
  }

  .kpi-icon {
    width: 50px;
    height: 50px;
    font-size: 20px;
  }

  .header-controls {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
