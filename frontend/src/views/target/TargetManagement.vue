<template>
  <div class="target-management erp-page-container erp-page--admin">
    <PageHeader
      title="目标管理"
      subtitle="维护月度目标、产品目标与战役目标。目标拆分和详情逻辑保持不变，本轮只统一页面结构与样式基线。"
      family="admin"
    />

    <el-tabs v-model="activeTab" type="card" class="main-tabs">
      <!-- 常规月度目标 -->
      <el-tab-pane label="常规月度目标" name="shop">
        <div class="month-bar">
          <el-date-picker
            v-model="monthStr"
            type="month"
            value-format="YYYY-MM"
            placeholder="选择月份"
            class="month-picker"
            @change="loadMonthlyTarget"
          />
          <el-button
            v-if="!monthlyTarget.target && !monthlyTarget.loading && !monthlyTarget.error"
            type="primary"
            :icon="Plus"
            @click="openCreateForMonth"
            >创建本月目标</el-button
          >
          <el-button
            v-if="monthlyTarget.target && hasPermission('target:update')"
            type="primary"
            plain
            @click="handleEdit(monthlyTarget.target)"
            >编辑目标</el-button
          >
          <el-button :icon="Refresh" @click="loadMonthlyTarget">刷新</el-button>
        </div>
        <div v-if="monthlyTarget.error" class="error-state">
          <el-result icon="error" :title="monthlyTarget.error">
            <template #extra>
              <el-button type="primary" @click="loadMonthlyTarget">重新加载</el-button>
            </template>
          </el-result>
        </div>
        <div v-else-if="monthlyTarget.loading" class="loading-state">
          <el-icon class="is-loading loading-icon"><Loading /></el-icon>
          加载中…
        </div>
        <div
          v-else-if="!monthlyTarget.target"
          class="empty-state"
        >
          <el-empty description="该月暂无目标">
            <el-button type="primary" @click="openCreateForMonth"
              >创建本月目标</el-button
            >
          </el-empty>
        </div>
        <template v-else>
          <!-- 目标摘要 -->
          <el-card class="summary-card" shadow="never">
            <template #header>
              <span>{{ monthlyTarget.target.target_name }}</span>
            </template>
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="目标金额"
                >¥{{ (Number(monthlyTarget.target.target_amount) || 0).toFixed(2) }}</el-descriptions-item
              >
              <el-descriptions-item label="目标数量">{{
                monthlyTarget.target.target_quantity
              }}</el-descriptions-item>
              <el-descriptions-item label="达成率">
                <el-tag
                  :type="
                    (Number(monthlyTarget.target.achievement_rate) || 0) >= 90
                      ? 'success'
                      : (Number(monthlyTarget.target.achievement_rate) || 0) >= 80
                        ? 'warning'
                        : 'danger'
                  "
                  size="small"
                >
                  {{ (Number(monthlyTarget.target.achievement_rate) || 0).toFixed(1) }}%
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
          <!-- 周一到周日比例 + 一键生成日度 -->
          <el-card class="ratios-card" shadow="never">
            <template #header>
              <span>周一到周日拆分比例</span>
              <el-button
                type="primary"
                size="small"
                class="header-action-right header-action-gap"
                :loading="dailyGenerateLoading"
                @click="handleGenerateDailyMonthly"
              >
                一键生成日度
              </el-button>
              <el-button
                type="primary"
                size="small"
                class="header-action-right"
                :loading="weekdayRatiosSaving"
                :disabled="Math.abs(weekdayRatiosSum - 1) > 0.001"
                @click="saveWeekdayRatiosMonthly"
              >
                保存比例
              </el-button>
            </template>
            <div class="weekday-ratios-hint">
              修改某天比例后，仅未修改的天会重新均分剩余比例；全部改完后点击「保存比例」，再点击「一键生成日度」；和为 100%。
            </div>
            <div class="weekday-ratios-row">
              <template v-for="(label, key) in weekdayLabels" :key="key">
                <div class="weekday-ratio-item">
                  <label>{{ label }}</label>
                  <el-input-number
                    v-model="weekdayRatiosForm[key]"
                    :min="0"
                    :max="1"
                    :step="0.01"
                    :precision="2"
                    size="small"
                    controls-position="right"
                    class="weekday-ratio-input"
                    @change="() => applyBalanceWeekdayRatios(key)"
                  />
                  <span class="weekday-pct">{{ (weekdayRatiosForm[key] * 100).toFixed(1) }}%</span>
                </div>
              </template>
            </div>
            <div class="weekday-ratios-sum">当前合计：{{ (weekdayRatiosSum * 100).toFixed(1) }}%</div>
          </el-card>
          <!-- 店铺拆分表（只读展示） -->
          <el-card
            v-if="shopBreakdownFromMonthly.length > 0"
            class="shop-breakdown-card"
            shadow="never"
          >
            <template #header>按店铺拆分</template>
            <el-table :data="shopBreakdownFromMonthly" border size="small">
              <el-table-column prop="shop_name" label="店铺" width="180" />
              <el-table-column prop="target_amount" label="目标金额" width="140" align="right">
                <template #default="{ row }">¥{{ (Number(row.target_amount) || 0).toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" />
            </el-table>
          </el-card>
          <!-- 本月日度目标（汇总）日历 -->
          <el-card class="daily-calendar-card" shadow="never">
            <template #header>本月日度目标（汇总）</template>
            <el-calendar v-model="monthlyCalendarDate">
              <template #date-cell="{ data }">
                <div
                  class="daily-cell"
                  :class="{
                    'in-range': isDayInMonthlyRange(data.day),
                    'out-range': data.type === 'current-month' && !isDayInMonthlyRange(data.day),
                  }"
                  @click="
                    data.type === 'current-month' &&
                    isDayInMonthlyRange(data.day) &&
                    handleMonthlyDayClick(data.day)
                  "
                >
                  <span class="day-num">{{ getDayNumber(data.day) }}</span>
                  <template v-if="data.type === 'current-month' && getMonthlyDailyBreakdown(data.day)">
                    <div class="daily-target">
                      ¥{{ (getMonthlyDailyBreakdown(data.day).target_amount || 0).toFixed(0) }}
                    </div>
                    <div class="daily-achieved">
                      达 ¥{{ (getMonthlyDailyBreakdown(data.day).achieved_amount || 0).toFixed(0) }}
                    </div>
                    <el-tag
                      :type="
                        (Number(getMonthlyDailyBreakdown(data.day).achievement_rate) || 0) >= 90
                          ? 'success'
                          : (Number(getMonthlyDailyBreakdown(data.day).achievement_rate) || 0) >= 80
                            ? 'warning'
                            : 'danger'
                      "
                      size="small"
                      class="daily-rate"
                    >
                      {{ (Number(getMonthlyDailyBreakdown(data.day).achievement_rate) || 0).toFixed(0) }}%
                    </el-tag>
                  </template>
                </div>
              </template>
            </el-calendar>
            <div class="daily-hint">点击目标范围内的日期可编辑该日目标；系统将自动调整其余日以保持月度总额不变。</div>
          </el-card>
          <!-- 店铺选择 + 该店铺的日度目标 -->
          <el-card class="shop-daily-card" shadow="never">
            <template #header>按店铺查看/编辑日度目标</template>
            <el-select
              v-model="selectedShopKey"
              placeholder="选择店铺"
              clearable
              class="shop-selector"
              @change="onSelectedShopChange"
            >
              <el-option
                v-for="s in shopOptionsForMonthly"
                :key="getShopKey(s)"
                :label="s.shop_name"
                :value="getShopKey(s)"
              />
            </el-select>
            <template v-if="selectedShopKey">
              <el-calendar v-model="shopDailyCalendarDate">
                <template #date-cell="{ data }">
                  <div
                    class="daily-cell shop-daily-cell"
                    :class="{
                      'in-range': isDayInMonthlyRange(data.day),
                      'out-range': data.type === 'current-month' && !isDayInMonthlyRange(data.day),
                    }"
                    @click="
                      data.type === 'current-month' &&
                      isDayInMonthlyRange(data.day) &&
                      handleShopDayClick(data.day)
                    "
                  >
                    <span class="day-num">{{ getDayNumber(data.day) }}</span>
                    <template v-if="data.type === 'current-month' && getShopDailyBreakdown(data.day)">
                      <div class="daily-target">
                        ¥{{ (getShopDailyBreakdown(data.day).target_amount || 0).toFixed(0) }}
                      </div>
                      <el-tag size="small" class="daily-rate">量 {{ getShopDailyBreakdown(data.day).target_quantity || 0 }}</el-tag>
                    </template>
                  </div>
                </template>
              </el-calendar>
              <div class="daily-hint">点击日期可编辑该店铺当日目标金额与数量。</div>
            </template>
            <div v-else class="shop-daily-placeholder">请先选择店铺</div>
          </el-card>
        </template>
      </el-tab-pane>

      <!-- 产品目标 -->
      <el-tab-pane label="产品目标" name="product">
        <div class="list-action-bar">
          <el-button
            type="primary"
            :icon="Plus"
            @click="handleCreate"
            v-if="hasPermission('target:create')"
          >
            创建目标
          </el-button>
          <el-button :icon="Refresh" @click="loadTargets">刷新</el-button>
          <el-button
            :icon="Download"
            @click="handleExport"
            v-if="hasPermission('target:export')"
            >导出</el-button
          >
          <div class="erp-flex-spacer"></div>
          <el-select
            v-model="filters.status"
            placeholder="状态"
            clearable
            size="small"
            class="erp-w-120"
            @change="loadTargets"
          >
            <el-option label="全部状态" value="" />
            <el-option label="进行中" value="active" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </div>
        <el-card>
          <div v-if="targets.error && !targets.loading" class="error-state">
            <el-result icon="error" :title="targets.error.message">
              <template #sub-title><span>{{ targets.error.recovery }}</span></template>
              <template #extra><el-button type="primary" @click="loadTargets">重新加载</el-button></template>
            </el-result>
          </div>
          <el-table
            v-if="!targets.error"
            :data="targets.data"
            stripe
            v-loading="targets.loading"
            class="erp-table"
          >
            <el-table-column prop="target_name" label="目标名称" width="250" fixed="left" show-overflow-tooltip />
            <el-table-column prop="target_type" label="目标类型" width="120">
              <template #default="{ row }">
                <el-tag :type="getTargetTypeTagType(row.target_type)" size="small">{{ getTargetTypeLabel(row.target_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="period_start" label="开始时间" width="120" />
            <el-table-column prop="period_end" label="结束时间" width="120" />
            <el-table-column prop="target_amount" label="目标金额" width="150" align="right" sortable>
              <template #default="{ row }">¥{{ (Number(row.target_amount) || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" sortable />
            <el-table-column prop="achieved_amount" label="达成金额" width="150" align="right" sortable>
              <template #default="{ row }">¥{{ (Number(row.achieved_amount) || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="achieved_quantity" label="达成数量" width="120" align="right" sortable />
            <el-table-column prop="achievement_rate" label="达成率" width="120" sortable>
              <template #default="{ row }">
                <el-tag :type="(Number(row.achievement_rate) || 0) >= 90 ? 'success' : (Number(row.achievement_rate) || 0) >= 80 ? 'warning' : 'danger'" size="small">
                  {{ (Number(row.achievement_rate) || 0).toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusTagType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleView(row)">查看</el-button>
                <el-button size="small" type="primary" @click="handleEdit(row)" v-if="hasPermission('target:update')">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDelete(row)" v-if="hasPermission('target:delete')">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="!targets.error"
            v-model:current-page="targets.page"
            v-model:page-size="targets.pageSize"
            :total="targets.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            class="target-pagination"
            @size-change="loadTargets"
            @current-change="loadTargets"
          />
        </el-card>
      </el-tab-pane>

      <!-- 战役目标 -->
      <el-tab-pane label="战役目标" name="campaign">
        <div class="list-action-bar">
          <el-button
            type="primary"
            :icon="Plus"
            @click="handleCreate"
            v-if="hasPermission('target:create')"
          >
            创建目标
          </el-button>
          <el-button :icon="Refresh" @click="loadTargets">刷新</el-button>
          <el-button
            :icon="Download"
            @click="handleExport"
            v-if="hasPermission('target:export')"
            >导出</el-button
          >
          <div class="erp-flex-spacer"></div>
          <el-select
            v-model="filters.status"
            placeholder="状态"
            clearable
            size="small"
            class="erp-w-120"
            @change="loadTargets"
          >
            <el-option label="全部状态" value="" />
            <el-option label="进行中" value="active" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </div>
        <el-card>
          <div v-if="targets.error && !targets.loading" class="error-state">
            <el-result icon="error" :title="targets.error.message">
              <template #sub-title><span>{{ targets.error.recovery }}</span></template>
              <template #extra><el-button type="primary" @click="loadTargets">重新加载</el-button></template>
            </el-result>
          </div>
          <el-table
            v-if="!targets.error"
            :data="targets.data"
            stripe
            v-loading="targets.loading"
            class="erp-table"
          >
            <el-table-column prop="target_name" label="目标名称" width="250" fixed="left" show-overflow-tooltip />
            <el-table-column prop="target_type" label="目标类型" width="120">
              <template #default="{ row }">
                <el-tag :type="getTargetTypeTagType(row.target_type)" size="small">{{ getTargetTypeLabel(row.target_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="period_start" label="开始时间" width="120" />
            <el-table-column prop="period_end" label="结束时间" width="120" />
            <el-table-column prop="target_amount" label="目标金额" width="150" align="right" sortable>
              <template #default="{ row }">¥{{ (Number(row.target_amount) || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="target_quantity" label="目标数量" width="120" align="right" sortable />
            <el-table-column prop="achieved_amount" label="达成金额" width="150" align="right" sortable>
              <template #default="{ row }">¥{{ (Number(row.achieved_amount) || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="achieved_quantity" label="达成数量" width="120" align="right" sortable />
            <el-table-column prop="achievement_rate" label="达成率" width="120" sortable>
              <template #default="{ row }">
                <el-tag :type="(Number(row.achievement_rate) || 0) >= 90 ? 'success' : (Number(row.achievement_rate) || 0) >= 80 ? 'warning' : 'danger'" size="small">
                  {{ (Number(row.achievement_rate) || 0).toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusTagType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleView(row)">查看</el-button>
                <el-button size="small" type="primary" @click="handleEdit(row)" v-if="hasPermission('target:update')">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDelete(row)" v-if="hasPermission('target:delete')">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="!targets.error"
            v-model:current-page="targets.page"
            v-model:page-size="targets.pageSize"
            :total="targets.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            class="target-pagination"
            @size-change="loadTargets"
            @current-change="loadTargets"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="900px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item
          v-if="form.target_type !== 'shop'"
          label="目标名称"
          prop="target_name"
        >
          <el-input v-model="form.target_name" placeholder="请输入目标名称" />
        </el-form-item>
        <!-- 目标类型由入口决定：常规月度页→店铺，产品/战役 Tab→对应类型，不再提供下拉选择；编辑时仅展示 -->
        <el-form-item v-if="form.target_type" label="目标类型">
          <el-tag :type="getTargetTypeTagType(form.target_type)" size="large">
            {{ getTargetTypeLabel(form.target_type) }}
          </el-tag>
        </el-form-item>
        <!-- 店铺目标：选月份，名称自动生成 -->
        <el-form-item
          v-if="form.target_type === 'shop'"
          label="目标月份"
          prop="targetMonth"
        >
          <el-date-picker
            v-model="form.targetMonth"
            type="month"
            placeholder="选择月份"
            value-format="YYYY-MM"
            class="erp-w-full"
          />
          <div v-if="form.targetMonth" class="form-hint">
            目标名称将自动生成：{{ autoTargetName }}
          </div>
        </el-form-item>
        <!-- 产品/战役：自定义日期范围 -->
        <el-form-item
          v-else-if="form.target_type"
          label="时间周期"
          prop="dateRange"
        >
          <el-date-picker
            v-model="form.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            class="erp-w-full"
          />
        </el-form-item>
        <el-form-item label="目标金额" prop="target_amount">
          <el-input-number
            v-model="form.target_amount"
            :min="0.01"
            :precision="2"
            class="erp-w-full"
          />
        </el-form-item>
        <el-form-item label="目标数量" prop="target_quantity">
          <el-input-number
            v-model="form.target_quantity"
            :min="1"
            :precision="0"
            class="erp-w-full"
          />
        </el-form-item>

        <!-- 目标拆分 -->
        <el-divider>目标拆分</el-divider>

        <el-tabs v-model="breakdownTab" type="border-card">
          <el-tab-pane label="按店铺拆分" name="shop">
            <div class="erp-mb-sm">
              <template v-if="form.target_type === 'shop'">
                <span v-if="availableShops.length" class="breakdown-hint"
                  >已按全部店铺初始化。修改某店百分比后，仅未修改的店铺会重新均分剩余比例；全部改完后点击「自动计算」回填金额/数量。</span
                >
                <span v-else class="breakdown-hint breakdown-hint--warn"
                  >暂无店铺数据，请先在账号管理中维护店铺。</span
                >
              </template>
              <template v-else>
                <el-button
                  size="small"
                  type="primary"
                  @click="handleAddShopBreakdown"
                  >添加店铺</el-button
                >
              </template>
              <el-button size="small" @click="handleAutoCalculateShop"
                >自动计算</el-button
              >
            </div>
            <el-table :data="shopBreakdown" border>
              <el-table-column prop="shop_name" label="店铺名称" width="200">
                <template #default="{ row, $index }">
                  <el-select
                    v-model="row.shopKey"
                    placeholder="选择店铺"
                    class="erp-w-full"
                    @change="(v) => handleShopChange($index, v)"
                  >
                    <el-option
                      v-for="s in availableShops"
                      :key="getShopKey(s)"
                      :label="s.shop_name"
                      :value="getShopKey(s)"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="目标百分比(%)" width="160">
                <template #default="{ row, $index }">
                  <el-input-number
                    v-model="row.target_percent"
                    :min="0"
                    :max="100"
                    :precision="2"
                    :step="1"
                    class="erp-w-full"
                    @change="() => applyBalancePercent($index)"
                  />
                </template>
              </el-table-column>
              <el-table-column
                prop="target_amount"
                label="目标金额"
                width="140"
              >
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.target_amount"
                    :min="0"
                    :precision="2"
                    class="erp-w-full"
                  />
                </template>
              </el-table-column>
              <el-table-column
                prop="target_quantity"
                label="目标数量"
                width="150"
              >
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.target_quantity"
                    :min="0"
                    :precision="0"
                    class="erp-w-full"
                  />
                </template>
              </el-table-column>
              <el-table-column
                v-if="form.target_type !== 'shop'"
                label="操作"
                width="80"
              >
                <template #default="{ $index }">
                  <el-button
                    size="small"
                    type="danger"
                    @click="handleRemoveShopBreakdown($index)"
                    >删除</el-button
                  >
                </template>
              </el-table-column>
            </el-table>
            <div class="breakdown-summary">
              店铺拆分总和：金额 ¥{{
                shopBreakdownTotalAmount.toFixed(2)
              }}，数量 {{ shopBreakdownTotalQuantity }}，百分比
              {{ shopBreakdownTotalPercent.toFixed(1) }}%
              <el-tag
                :type="
                  shopBreakdownTotalAmount === form.target_amount &&
                  shopBreakdownTotalQuantity === form.target_quantity
                    ? 'success'
                    : 'danger'
                "
                size="small"
                class="erp-ml-sm"
              >
                {{
                  shopBreakdownTotalAmount === form.target_amount &&
                  shopBreakdownTotalQuantity === form.target_quantity
                    ? "拆分正确"
                    : "拆分总和必须等于总目标"
                }}
              </el-tag>
            </div>
          </el-tab-pane>

          <el-tab-pane label="按时间拆分" name="time">
            <div class="erp-mb-sm">
              <el-button
                size="small"
                type="primary"
                @click="handleAutoCalculateTime"
                >自动计算</el-button
              >
            </div>
            <el-table :data="timeBreakdown" border>
              <el-table-column prop="period" label="时间周期" width="150" />
              <el-table-column
                prop="target_amount"
                label="目标金额"
                width="150"
              >
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.target_amount"
                    :min="0.01"
                    :precision="2"
                    class="erp-w-full"
                  />
                </template>
              </el-table-column>
              <el-table-column
                prop="target_quantity"
                label="目标数量"
                width="150"
              >
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.target_quantity"
                    :min="1"
                    :precision="0"
                    class="erp-w-full"
                  />
                </template>
              </el-table-column>
            </el-table>
            <div class="breakdown-summary">
              时间拆分总和：金额 ¥{{
                timeBreakdownTotalAmount.toFixed(2)
              }}，数量 {{ timeBreakdownTotalQuantity }}
              <el-tag
                :type="
                  timeBreakdownTotalAmount === form.target_amount &&
                  timeBreakdownTotalQuantity === form.target_quantity
                    ? 'success'
                    : 'danger'
                "
                size="small"
                class="erp-ml-sm"
              >
                {{
                  timeBreakdownTotalAmount === form.target_amount &&
                  timeBreakdownTotalQuantity === form.target_quantity
                    ? "拆分正确"
                    : "拆分总和必须等于总目标"
                }}
              </el-tag>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting"
          >确定</el-button
        >
      </template>
    </el-dialog>

    <!-- 目标详情对话框 -->
    <el-dialog v-model="detailVisible" title="目标详情" width="1000px">
      <div v-if="targetDetail.data" v-loading="targetDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="目标名称" :span="2">{{
            targetDetail.data.target_name
          }}</el-descriptions-item>
          <el-descriptions-item label="目标类型">
            <el-tag
              :type="getTargetTypeTagType(targetDetail.data.target_type)"
              size="small"
            >
              {{ getTargetTypeLabel(targetDetail.data.target_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag
              :type="getStatusTagType(targetDetail.data.status)"
              size="small"
            >
              {{ getStatusLabel(targetDetail.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{
            targetDetail.data.period_start
          }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{
            targetDetail.data.period_end
          }}</el-descriptions-item>
          <el-descriptions-item label="目标金额"
            >¥{{
              targetDetail.data.target_amount.toFixed(2)
            }}</el-descriptions-item
          >
          <el-descriptions-item label="目标数量">{{
            targetDetail.data.target_quantity
          }}</el-descriptions-item>
          <el-descriptions-item label="达成金额"
            >¥{{
              targetDetail.data.achieved_amount.toFixed(2)
            }}</el-descriptions-item
          >
          <el-descriptions-item label="达成数量">{{
            targetDetail.data.achieved_quantity
          }}</el-descriptions-item>
          <el-descriptions-item label="达成率">
            <el-tag
              :type="
                targetDetail.data.achievement_rate >= 90
                  ? 'success'
                  : targetDetail.data.achievement_rate >= 80
                    ? 'warning'
                    : 'danger'
              "
              size="small"
            >
              {{ targetDetail.data.achievement_rate.toFixed(1) }}%
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 目标分解 -->
        <el-card
          class="erp-mt-lg"
          v-if="
            targetDetail.data.breakdown &&
            targetDetail.data.breakdown.length > 0
          "
        >
          <template #header>
            <span>目标分解（按店铺）</span>
          </template>
          <el-table :data="targetDetail.data.breakdown" stripe>
            <el-table-column prop="shop_name" label="店铺名称" />
            <el-table-column
              prop="target_amount"
              label="目标金额"
              width="150"
              align="right"
            >
              <template #default="{ row }">
                ¥{{ row.target_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="target_quantity"
              label="目标数量"
              width="120"
              align="right"
            />
            <el-table-column
              prop="achieved_amount"
              label="达成金额"
              width="150"
              align="right"
            >
              <template #default="{ row }">
                ¥{{ row.achieved_amount.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="achieved_quantity"
              label="达成数量"
              width="120"
              align="right"
            />
            <el-table-column prop="achievement_rate" label="达成率" width="120">
              <template #default="{ row }">
                <el-tag
                  :type="
                    row.achievement_rate >= 90
                      ? 'success'
                      : row.achievement_rate >= 80
                        ? 'warning'
                        : 'danger'
                  "
                  size="small"
                >
                  {{ row.achievement_rate.toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 时间分解（表格） -->
        <el-card
          class="erp-mt-lg"
          v-if="
            targetDetail.data.time_breakdown &&
            targetDetail.data.time_breakdown.length > 0
          "
        >
          <template #header>
            <span>目标分解（按时间）</span>
          </template>
          <el-table :data="targetDetail.data.time_breakdown" stripe>
            <el-table-column prop="period_label" label="周期" />
            <el-table-column
              prop="target_amount"
              label="目标金额"
              width="150"
              align="right"
            >
              <template #default="{ row }">
                ¥{{ (Number(row.target_amount) || 0).toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="target_quantity"
              label="目标数量"
              width="120"
              align="right"
            />
            <el-table-column
              prop="achieved_amount"
              label="达成金额"
              width="150"
              align="right"
            >
              <template #default="{ row }">
                ¥{{ (Number(row.achieved_amount) || 0).toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="achieved_quantity"
              label="达成数量"
              width="120"
              align="right"
            />
            <el-table-column prop="achievement_rate" label="达成率" width="120">
              <template #default="{ row }">
                <el-tag
                  :type="
                    (Number(row.achievement_rate) || 0) >= 90
                      ? 'success'
                      : (Number(row.achievement_rate) || 0) >= 80
                        ? 'warning'
                        : 'danger'
                  "
                  size="small"
                >
                  {{ (Number(row.achievement_rate) || 0).toFixed(1) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 周一到周日拆分比例（一键生成日度前配置） -->
        <el-card class="erp-mt-lg" v-if="targetDetail.data.period_start && targetDetail.data.period_end">
          <template #header>
            <span>周一到周日拆分比例</span>
            <el-button
              type="primary"
              size="small"
              class="header-action-right"
              :loading="weekdayRatiosSaving"
              :disabled="Math.abs(weekdayRatiosSum - 1) > 0.001"
              @click="saveWeekdayRatios"
            >
              保存比例
            </el-button>
          </template>
          <div class="weekday-ratios-hint">修改某天比例后，仅未修改的天会重新均分剩余比例；全部改完后点击「保存比例」再「一键生成日度」；和为 100%。</div>
          <div class="weekday-ratios-row">
            <template v-for="(label, key) in weekdayLabels" :key="key">
              <div class="weekday-ratio-item">
                <label>{{ label }}</label>
                <el-input-number
                  v-model="weekdayRatiosForm[key]"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="2"
                  size="small"
                  controls-position="right"
                  class="weekday-ratio-input"
                  @change="() => applyBalanceWeekdayRatios(key)"
                />
                <span class="weekday-pct">{{ (weekdayRatiosForm[key] * 100).toFixed(1) }}%</span>
              </div>
            </template>
          </div>
          <div class="weekday-ratios-sum">当前合计：{{ (weekdayRatiosSum * 100).toFixed(1) }}%</div>
        </el-card>

        <!-- 日度分解（日历） -->
        <el-card class="erp-mt-lg" v-if="targetDetail.data.period_start && targetDetail.data.period_end">
          <template #header>
            <span>日度分解（日历）</span>
            <el-button
              type="primary"
              size="small"
              class="header-action-right"
              :loading="dailyGenerateLoading"
              @click="handleGenerateDaily"
            >
              一键生成日度
            </el-button>
          </template>
          <el-calendar v-model="detailCalendarDate">
            <template #date-cell="{ data }">
              <div
                class="daily-cell"
                :class="{
                  'in-range': isDayInTargetRange(data.day),
                  'out-range': data.type === 'current-month' && !isDayInTargetRange(data.day),
                }"
                @click="data.type === 'current-month' && isDayInTargetRange(data.day) && handleDayClick(data.day)"
              >
                <span class="day-num">{{ getDayNumber(data.day) }}</span>
                <template v-if="data.type === 'current-month' && getDailyBreakdown(data.day)">
                  <div class="daily-target">¥{{ (getDailyBreakdown(data.day).target_amount || 0).toFixed(0) }}</div>
                  <div class="daily-achieved">达 ¥{{ (getDailyBreakdown(data.day).achieved_amount || 0).toFixed(0) }}</div>
                  <el-tag
                    :type="(Number(getDailyBreakdown(data.day).achievement_rate) || 0) >= 90 ? 'success' : (Number(getDailyBreakdown(data.day).achievement_rate) || 0) >= 80 ? 'warning' : 'danger'"
                    size="small"
                    class="daily-rate"
                  >
                    {{ (Number(getDailyBreakdown(data.day).achievement_rate) || 0).toFixed(0) }}%
                  </el-tag>
                </template>
              </div>
            </template>
          </el-calendar>
          <div v-if="targetDetail.data.period_start" class="daily-hint">
            点击目标范围内的日期可编辑该日目标；生成后可在业务概览中做日度对比。
          </div>
        </el-card>
      </div>
    </el-dialog>

    <!-- 单日目标编辑 -->
    <el-dialog v-model="dayEditVisible" title="编辑日度目标" width="400px">
      <el-form :model="dayEditForm" label-width="90px">
        <el-form-item label="日期">{{ dayEditForm.date }}</el-form-item>
        <el-form-item label="目标金额">
          <el-input-number v-model="dayEditForm.target_amount" :min="0" :precision="2" class="erp-w-full" />
        </el-form-item>
        <el-form-item label="目标数量">
          <el-input-number v-model="dayEditForm.target_quantity" :min="0" :precision="0" class="erp-w-full" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dayEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDayEdit" :loading="dayEditSaving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Download, Loading } from "@element-plus/icons-vue";
import { useUserStore } from "@/stores/user";
import api from "@/api";
import { handleApiError } from "@/utils/errorHandler";
import PageHeader from "@/components/common/PageHeader.vue";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatInteger,
} from "@/utils/dataFormatter";

const userStore = useUserStore();

// 页面 Tab：常规月度 | 产品 | 战役
const activeTab = ref("shop");
const monthStr = ref(
  (() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  })(),
);
const monthlyTarget = reactive({
  target: null,
  breakdowns: [],
  loading: false,
  error: null,
});
const monthlyCalendarDate = ref(new Date());
const shopDailyCalendarDate = ref(new Date());
const selectedShopKey = ref("");
const shopOptionsForMonthly = computed(() => {
  const shopRows = monthlyTarget.breakdowns.filter((b) => b.breakdown_type === "shop");
  if (shopRows.length) {
    return shopRows.map((b) => ({
      platform_code: b.platform_code,
      shop_id: b.shop_id,
      shop_name: b.shop_name || `${b.platform_code}-${b.shop_id}`,
    }));
  }
  return availableShops.value;
});
const shopBreakdownFromMonthly = computed(() =>
  monthlyTarget.breakdowns.filter((b) => b.breakdown_type === "shop"),
);
const timeBreakdownMonthly = computed(() =>
  monthlyTarget.breakdowns.filter((b) => b.breakdown_type === "time"),
);
const shopTimeBreakdownMonthly = computed(() =>
  monthlyTarget.breakdowns.filter((b) => b.breakdown_type === "shop_time"),
);

// 角色代码规范化（中文 → 英文）
const normalizeRoleCode = (role) => {
  if (!role) return "";
  const map = {
    管理员: "admin",
    主管: "manager",
    经理: "manager",
    操作员: "operator",
    运营: "operator",
    财务: "finance",
  };
  return map[role] || role;
};

// 权限检查 - 使用系统统一权限架构（基于 activeRole + permissions）
const hasPermission = (permission) => {
  // 获取当前激活的角色（与 SimpleAccountSwitcher 保持一致）
  const activeRole = normalizeRoleCode(localStorage.getItem("activeRole"));

  // 管理员拥有所有目标管理权限
  if (activeRole === "admin") return true;

  // 检查用户是否拥有管理员角色（即使不是当前激活角色）
  const userRoles = (userStore.roles || []).map(normalizeRoleCode);
  if (userRoles.includes("admin")) return true;

  // 主管角色的目标管理权限（根据权限矩阵，主管不能访问目标管理）
  // 但保留只读权限作为防御性设计
  if (activeRole === "manager") {
    return ["target:read", "target:export"].includes(permission);
  }

  // 其他角色只有只读权限
  return permission === "target:read";
};

// 目标列表数据
const targets = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false,
  error: null, // 错误状态：区分"无数据"和"加载失败"
});

const filters = reactive({
  targetType: "",
  status: "",
});

// 按月份加载常规月度目标（常规月度 Tab）
const loadMonthlyTarget = async () => {
  monthlyTarget.error = null;
  if (activeTab.value !== "shop" || !monthStr.value) return;
  monthlyTarget.loading = true;
  try {
    const response = await api.getTargetByMonth(monthStr.value, "shop");
    const data = response?.data ?? response;
    monthlyTarget.target = data?.target ?? null;
    monthlyTarget.breakdowns = Array.isArray(data?.breakdowns) ? data.breakdowns : [];
    if (monthlyTarget.target?.period_start) {
      monthlyCalendarDate.value = new Date(monthlyTarget.target.period_start + "T12:00:00");
      shopDailyCalendarDate.value = new Date(monthlyTarget.target.period_start + "T12:00:00");
    }
    syncWeekdayRatiosFromMonthly();
  } catch (e) {
    const err = handleApiError(e, { showMessage: false, logError: true });
    monthlyTarget.error = err?.message || "加载失败";
    monthlyTarget.target = null;
    monthlyTarget.breakdowns = [];
  } finally {
    monthlyTarget.loading = false;
  }
};

const syncWeekdayRatiosFromMonthly = () => {
  clearWeekdayRatiosLocks();
  const ratios = monthlyTarget.target?.weekday_ratios;
  if (ratios && typeof ratios === "object") {
    Object.keys(weekdayLabels).forEach((k) => {
      const v = Number(ratios[k]);
      if (!Number.isNaN(v)) weekdayRatiosForm[k] = Math.round(v * 100) / 100;
    });
  } else {
    Object.keys(weekdayLabels).forEach((k) => {
      weekdayRatiosForm[k] = defaultRatio;
    });
  }
};

const openCreateForMonth = async () => {
  form.id = null;
  form.target_name = "";
  form.target_type = "shop";
  form.targetMonth = monthStr.value;
  form.dateRange = [];
  form.target_amount = 0;
  form.target_quantity = 0;
  shopBreakdown.value = [];
  timeBreakdown.value = [];
  breakdownTab.value = "shop";
  if (availableShops.value.length === 0) await loadTargetShops();
  applyShopBreakdownFromAvailableShops();
  dialogVisible.value = true;
};

const applyShopBreakdownFromAvailableShops = () => {
  const list = availableShops.value || [];
  const n = Math.max(1, list.length);
  const pct = Math.round((100 / n) * 100) / 100;
  shopBreakdown.value = list.map((s, i) => ({
    shopKey: getShopKey(s),
    platform_code: s.platform_code,
    shop_id: s.shop_id,
    shop_name: s.shop_name || "",
    target_amount: 0,
    target_quantity: 0,
    target_percent: i === list.length - 1 ? 100 - pct * (list.length - 1) : pct,
    percentLocked: false,
  }));
};

const saveWeekdayRatiosMonthly = async () => {
  if (!monthlyTarget.target?.id) return;
  if (Math.abs(weekdayRatiosSum.value - 1) > 0.001) {
    ElMessage.warning("比例合计须为 100%");
    return;
  }
  weekdayRatiosSaving.value = true;
  try {
    const weekday_ratios = {};
    Object.keys(weekdayLabels).forEach((k) => {
      weekday_ratios[k] = Number(weekdayRatiosForm[k]) || 0;
    });
    await api.updateTarget(monthlyTarget.target.id, { weekday_ratios });
    ElMessage.success("比例已保存");
    await loadMonthlyTarget();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    weekdayRatiosSaving.value = false;
  }
};

const handleGenerateDailyMonthly = async () => {
  if (!monthlyTarget.target?.id) return;
  dailyGenerateLoading.value = true;
  try {
    const weekday_ratios = {};
    Object.keys(weekdayLabels).forEach((k) => {
      weekday_ratios[k] = Number(weekdayRatiosForm[k]) || 0;
    });
    const res = await api.generateDailyBreakdown(monthlyTarget.target.id, {
      overwrite: true,
      weekday_ratios: Object.keys(weekday_ratios).length ? weekday_ratios : undefined,
    });
    const msg = res?.message || (res?.data ? `已生成 ${res.data?.created ?? 0} 条日度分解` : "生成成功");
    ElMessage.success(msg);
    await loadMonthlyTarget();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    dailyGenerateLoading.value = false;
  }
};

const isDayInMonthlyRange = (dayStr) => {
  if (!monthlyTarget.target?.period_start || !monthlyTarget.target?.period_end) return false;
  return dayStr >= monthlyTarget.target.period_start && dayStr <= monthlyTarget.target.period_end;
};

const getMonthlyDailyBreakdown = (dayStr) => {
  const list = timeBreakdownMonthly.value;
  return list.find(
    (b) =>
      (b.period_start === dayStr || b.period_end === dayStr) && b.period_start === b.period_end,
  ) || null;
};

const handleMonthlyDayClick = (dayStr) => {
  const b = getMonthlyDailyBreakdown(dayStr);
  dayEditForm.date = dayStr;
  dayEditForm.target_amount = b ? Number(b.target_amount) || 0 : 0;
  dayEditForm.target_quantity = b ? Number(b.target_quantity) || 0 : 0;
  dayEditForm.breakdown_id = b?.id ?? null;
  dayEditForm.editMode = "time";
  dayEditForm.platform_code = "";
  dayEditForm.shop_id = "";
  dayEditVisible.value = true;
};

const onSelectedShopChange = () => {
  if (monthlyTarget.target?.period_start) {
    shopDailyCalendarDate.value = new Date(monthlyTarget.target.period_start + "T12:00:00");
  }
};

const getShopDailyBreakdown = (dayStr) => {
  if (!selectedShopKey.value) return null;
  const [platform_code, shop_id] = selectedShopKey.value.split("|");
  const list = shopTimeBreakdownMonthly.value.filter(
    (b) => b.platform_code === platform_code && String(b.shop_id) === String(shop_id),
  );
  return list.find(
    (b) =>
      (b.period_start === dayStr || b.period_end === dayStr) && b.period_start === b.period_end,
  ) || null;
};

const handleShopDayClick = (dayStr) => {
  const b = getShopDailyBreakdown(dayStr);
  dayEditForm.date = dayStr;
  dayEditForm.target_amount = b ? Number(b.target_amount) || 0 : 0;
  dayEditForm.target_quantity = b ? Number(b.target_quantity) || 0 : 0;
  dayEditForm.breakdown_id = b?.id ?? null;
  dayEditForm.editMode = "shop_time";
  const [platform_code, shop_id] = selectedShopKey.value.split("|");
  dayEditForm.platform_code = platform_code || "";
  dayEditForm.shop_id = shop_id || "";
  dayEditVisible.value = true;
};

// 目标详情
const targetDetail = reactive({
  data: null,
  loading: false,
});

// 对话框状态
const dialogVisible = ref(false);
const detailVisible = ref(false);
const submitting = ref(false);
const formRef = ref(null);
const breakdownTab = ref("shop");
// 日度分解：日历显示的月份、一键生成 loading、单日编辑
const detailCalendarDate = ref(new Date());
const dailyGenerateLoading = ref(false);
const dayEditVisible = ref(false);
const dayEditSaving = ref(false);
const dayEditForm = reactive({
  date: "",
  target_amount: 0,
  target_quantity: 0,
  breakdown_id: null,
  editMode: "time",
  platform_code: "",
  shop_id: "",
});
// 周一到周日拆分比例（1=周一…7=周日，和为 1）；与店铺拆分一致：仅重算未锁定的项
const weekdayLabels = { "1": "周一", "2": "周二", "3": "周三", "4": "周四", "5": "周五", "6": "周六", "7": "周日" };
const defaultRatio = Math.round((1 / 7) * 100) / 100;
const weekdayRatiosForm = reactive({
  "1": defaultRatio, "2": defaultRatio, "3": defaultRatio, "4": defaultRatio,
  "5": defaultRatio, "6": defaultRatio, "7": defaultRatio,
});
const weekdayRatiosLocked = reactive({
  "1": false, "2": false, "3": false, "4": false, "5": false, "6": false, "7": false,
});
const weekdayRatiosSaving = ref(false);
const weekdayRatiosSum = computed(() => {
  return Object.keys(weekdayLabels).reduce((s, k) => s + (Number(weekdayRatiosForm[k]) || 0), 0);
});

const clearWeekdayRatiosLocks = () => {
  Object.keys(weekdayLabels).forEach((k) => { weekdayRatiosLocked[k] = false; });
};

const applyBalanceWeekdayRatios = (editedKey) => {
  const keys = Object.keys(weekdayLabels);
  if (editedKey === null || editedKey === undefined || editedKey === "-1") {
    clearWeekdayRatiosLocks();
    keys.forEach((k) => { weekdayRatiosForm[k] = defaultRatio; });
    return;
  }
  weekdayRatiosLocked[editedKey] = true;
  const lockedSum = keys
    .filter((k) => weekdayRatiosLocked[k])
    .reduce((s, k) => s + (Number(weekdayRatiosForm[k]) || 0), 0);
  let remainder = Math.round((1 - lockedSum) * 100) / 100;
  if (remainder < 0) {
    ElMessage.warning("已锁定比例之和不能超过 100%");
    remainder = 0;
  }
  const unlockedKeys = keys.filter((k) => !weekdayRatiosLocked[k]);
  if (unlockedKeys.length === 0) return;
  const each = Math.round((remainder / unlockedKeys.length) * 100) / 100;
  unlockedKeys.forEach((k, i) => {
    weekdayRatiosForm[k] =
      i === unlockedKeys.length - 1
        ? Math.round((remainder - each * (unlockedKeys.length - 1)) * 100) / 100
        : each;
  });
};

// 表单数据
const form = reactive({
  id: null,
  target_name: "",
  target_type: "",
  targetMonth: "", // 店铺目标时用：YYYY-MM
  dateRange: [],
  target_amount: 0,
  target_quantity: 0,
});

// 店铺拆分数据：每行 { shopKey, platform_code, shop_id, shop_name, target_amount, target_quantity, target_percent }
const shopBreakdown = ref([]);

// 时间拆分数据
const timeBreakdown = ref([]);

// 店铺列表（来自 GET /targets/shops，账号管理 platform_accounts）
const availableShops = ref([]);
const shopsLoading = ref(false);

// 计算属性
const dialogTitle = computed(() => {
  return form.id ? "编辑目标" : "创建目标";
});

// 店铺目标时自动生成的名称，如「2026年1月常规月度目标」
const autoTargetName = computed(() => {
  if (!form.targetMonth) return "";
  const [y, m] = form.targetMonth.split("-");
  return `${y}年${parseInt(m, 10)}月常规月度目标`;
});

const shopBreakdownTotalAmount = computed(() => {
  return shopBreakdown.value.reduce(
    (sum, item) => sum + (item.target_amount || 0),
    0,
  );
});

const shopBreakdownTotalQuantity = computed(() => {
  return shopBreakdown.value.reduce(
    (sum, item) => sum + (item.target_quantity || 0),
    0,
  );
});

const shopBreakdownTotalPercent = computed(() => {
  return shopBreakdown.value.reduce(
    (sum, item) => sum + (Number(item.target_percent) || 0),
    0,
  );
});

function getShopKey(s) {
  return `${s.platform_code || ""}|${s.shop_id || ""}`;
}

const timeBreakdownTotalAmount = computed(() => {
  return timeBreakdown.value.reduce(
    (sum, item) => sum + (item.target_amount || 0),
    0,
  );
});

const timeBreakdownTotalQuantity = computed(() => {
  return timeBreakdown.value.reduce(
    (sum, item) => sum + (item.target_quantity || 0),
    0,
  );
});

// 表单验证规则（按目标类型生效：店铺用 targetMonth，产品/战役用 target_name + dateRange）
const formRules = computed(() => {
  const isShop = form.target_type === "shop";
  return {
    target_name: isShop
      ? []
      : [
          { required: true, message: "目标名称不能为空", trigger: "blur" },
          {
            min: 2,
            max: 100,
            message: "目标名称长度2-100字符",
            trigger: "blur",
          },
        ],
    target_type: [
      { required: true, message: "请选择目标类型", trigger: "change" },
    ],
    targetMonth: isShop
      ? [{ required: true, message: "请选择目标月份", trigger: "change" }]
      : [],
    dateRange: isShop
      ? []
      : [
          { required: true, message: "请选择时间周期", trigger: "change" },
          {
            validator: (rule, value, callback) => {
              if (!value || value.length !== 2) {
                callback(new Error("请选择开始和结束日期"));
              } else if (new Date(value[1]) <= new Date(value[0])) {
                callback(new Error("结束时间必须大于开始时间"));
              } else {
                callback();
              }
            },
            trigger: "change",
          },
        ],
    target_amount: [
      { required: true, message: "目标金额不能为空", trigger: "blur" },
      {
        type: "number",
        min: 0.01,
        message: "目标金额必须大于0",
        trigger: "blur",
      },
    ],
    target_quantity: [
      { required: true, message: "目标数量不能为空", trigger: "blur" },
      { type: "number", min: 1, message: "目标数量必须大于0", trigger: "blur" },
    ],
  };
});

// 加载供目标管理使用的店铺列表（来自账号管理）
const loadTargetShops = async () => {
  shopsLoading.value = true;
  try {
    const data = await api.getTargetShops();
    availableShops.value = Array.isArray(data)
      ? data
      : (data?.data ?? data ?? []);
  } catch (e) {
    handleApiError(e, { showMessage: true, logError: true });
    availableShops.value = [];
  } finally {
    shopsLoading.value = false;
  }
};

// 加载目标列表
const loadTargets = async () => {
  targets.loading = true;
  targets.error = null; // 重置错误状态
  try {
    const response = await api.getTargets({
      target_type: filters.targetType || undefined,
      status: filters.status || undefined,
      page: targets.page,
      page_size: targets.pageSize,
    });

    // 处理分页响应（后端返回 { items, total, page, page_size } 或兼容旧格式）
    if (response && Array.isArray(response)) {
      targets.data = response;
      targets.total = response.length;
    } else if (
      response &&
      typeof response === "object" &&
      "items" in response
    ) {
      targets.data = response.items ?? [];
      targets.total = Number(response.total ?? 0);
      if (response.page != null) targets.page = response.page;
      if (response.page_size != null) targets.pageSize = response.page_size;
    } else {
      targets.data = response?.data ?? response ?? [];
      targets.total = Number(
        response?.total ?? response?.pagination?.total ?? 0,
      );
    }
  } catch (error) {
    // 设置错误状态，区分"无数据"和"加载失败"
    const errorInfo = handleApiError(error, { showMessage: false, logError: true });
    targets.error = {
      message: errorInfo.message || "加载失败",
      code: errorInfo.code,
      recovery: errorInfo.recovery || "请检查网络连接或稍后重试",
    };
    targets.data = [];
    targets.total = 0;
    // 显示错误提示（延迟显示，避免与 loading 状态冲突）
    ElMessage.error(targets.error.message);
  } finally {
    targets.loading = false;
  }
};

// 查看详情（后端返回 { target, breakdowns }，整理为 targetDetail.data.breakdown / time_breakdown）
const handleView = async (row) => {
  detailVisible.value = true;
  targetDetail.loading = true;
  try {
    const response = await api.getTargetDetail(row.id);
    const res = response || {};
    const target = res.target || res;
    const breakdowns = res.breakdowns || res.breakdown || [];
    targetDetail.data = {
      ...target,
      breakdown: breakdowns.filter((b) => b.breakdown_type === "shop"),
      time_breakdown: breakdowns.filter((b) => b.breakdown_type === "time"),
    };
    if (targetDetail.data.period_start) {
      detailCalendarDate.value = new Date(targetDetail.data.period_start + "T12:00:00");
    }
    syncWeekdayRatiosFromDetail();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    targetDetail.loading = false;
  }
};

// 刷新目标详情（用于生成日度或编辑单日后更新日历）
const refreshDetail = async () => {
  if (!targetDetail.data?.id) return;
  targetDetail.loading = true;
  try {
    const response = await api.getTargetDetail(targetDetail.data.id);
    const res = response || {};
    const target = res.target || res;
    const breakdowns = res.breakdowns || res.breakdown || [];
    targetDetail.data = {
      ...target,
      breakdown: breakdowns.filter((b) => b.breakdown_type === "shop"),
      time_breakdown: breakdowns.filter((b) => b.breakdown_type === "time"),
    };
    syncWeekdayRatiosFromDetail();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    targetDetail.loading = false;
  }
};

// 从目标详情同步周一到周日比例到表单
const syncWeekdayRatiosFromDetail = () => {
  clearWeekdayRatiosLocks();
  const ratios = targetDetail.data?.weekday_ratios;
  if (ratios && typeof ratios === "object") {
    Object.keys(weekdayLabels).forEach((k) => {
      const v = Number(ratios[k]);
      if (!Number.isNaN(v)) weekdayRatiosForm[k] = Math.round(v * 100) / 100;
    });
  } else {
    Object.keys(weekdayLabels).forEach((k) => { weekdayRatiosForm[k] = defaultRatio; });
  }
};

// 保存周一到周日比例
const saveWeekdayRatios = async () => {
  if (!targetDetail.data?.id) return;
  if (Math.abs(weekdayRatiosSum.value - 1) > 0.001) {
    ElMessage.warning("比例合计须为 100%");
    return;
  }
  weekdayRatiosSaving.value = true;
  try {
    const weekday_ratios = {};
    Object.keys(weekdayLabels).forEach((k) => { weekday_ratios[k] = Number(weekdayRatiosForm[k]) || 0; });
    await api.updateTarget(targetDetail.data.id, { weekday_ratios });
    ElMessage.success("比例已保存");
    await refreshDetail();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    weekdayRatiosSaving.value = false;
  }
};

// 日度分解：判断某日是否在目标周期内
const isDayInTargetRange = (dayStr) => {
  if (!targetDetail.data?.period_start || !targetDetail.data?.period_end) return false;
  return dayStr >= targetDetail.data.period_start && dayStr <= targetDetail.data.period_end;
};

// 日历格子显示日期数字
const getDayNumber = (dayStr) => {
  if (!dayStr) return "";
  const d = dayStr.split("-");
  return d.length === 3 ? d[2] : "";
};

// 根据日期取当日分解（period_start 或 period_end 等于该日）
const getDailyBreakdown = (dayStr) => {
  const list = targetDetail.data?.time_breakdown || [];
  return list.find((b) => (b.period_start === dayStr || b.period_end === dayStr) && b.period_start === b.period_end) || null;
};

// 一键生成日度（使用当前表单的周一到周日比例）
const handleGenerateDaily = async () => {
  if (!targetDetail.data?.id) return;
  dailyGenerateLoading.value = true;
  try {
    const weekday_ratios = {};
    Object.keys(weekdayLabels).forEach((k) => { weekday_ratios[k] = Number(weekdayRatiosForm[k]) || 0; });
    const res = await api.generateDailyBreakdown(targetDetail.data.id, {
      overwrite: true,
      weekday_ratios: Object.keys(weekday_ratios).length ? weekday_ratios : undefined,
    });
    const msg = res?.message || res?.data ? `已生成 ${res.data?.created ?? 0} 条日度分解` : "生成成功";
    ElMessage.success(msg);
    await refreshDetail();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    dailyGenerateLoading.value = false;
  }
};

// 点击某日打开编辑
const handleDayClick = (dayStr) => {
  const b = getDailyBreakdown(dayStr);
  dayEditForm.date = dayStr;
  dayEditForm.target_amount = b ? Number(b.target_amount) || 0 : 0;
  dayEditForm.target_quantity = b ? Number(b.target_quantity) || 0 : 0;
  dayEditForm.breakdown_id = b?.id ?? null;
  dayEditForm.editMode = "time";
  dayEditForm.platform_code = "";
  dayEditForm.shop_id = "";
  dayEditVisible.value = true;
};

// 保存单日目标（创建或更新分解）；支持汇总(time)与按店铺(shop_time)
const saveDayEdit = async () => {
  const targetId = monthlyTarget.target?.id ?? targetDetail.data?.id;
  if (!targetId || !dayEditForm.date) return;
  dayEditSaving.value = true;
  try {
    const payload = {
      breakdown_type: dayEditForm.editMode || "time",
      period_start: dayEditForm.date,
      period_end: dayEditForm.date,
      period_label: dayEditForm.date,
      target_amount: Number(dayEditForm.target_amount) || 0,
      target_quantity: Math.max(0, Math.floor(Number(dayEditForm.target_quantity) || 0)),
    };
    if (dayEditForm.editMode === "shop_time" && dayEditForm.platform_code && dayEditForm.shop_id) {
      payload.platform_code = dayEditForm.platform_code;
      payload.shop_id = dayEditForm.shop_id;
    }
    await api.createTargetBreakdown(targetId, payload);
    ElMessage.success("已保存");
    dayEditVisible.value = false;
    if (monthlyTarget.target?.id === targetId) await loadMonthlyTarget();
    else await refreshDetail();
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true });
  } finally {
    dayEditSaving.value = false;
  }
};

// 创建目标：类型由当前 Tab 决定（产品目标 Tab→product，战役目标 Tab→campaign），不再让用户选择
const handleCreate = async () => {
  form.id = null;
  form.target_name = "";
  form.target_type = activeTab.value;
  form.targetMonth = "";
  form.dateRange = [];
  form.target_amount = 0;
  form.target_quantity = 0;
  shopBreakdown.value = [];
  timeBreakdown.value = [];
  breakdownTab.value = "shop";
  if (availableShops.value.length === 0) await loadTargetShops();
  if (form.target_type === "shop") applyShopBreakdownFromAvailableShops();
  dialogVisible.value = true;
};

// 编辑目标
const handleEdit = async (row) => {
  form.id = row.id;
  form.target_name = row.target_name;
  form.target_type = row.target_type;
  if (row.target_type === "shop" && row.period_start) {
    form.targetMonth = row.period_start.slice(0, 7);
    form.dateRange = [];
  } else {
    form.targetMonth = "";
    form.dateRange = [new Date(row.period_start), new Date(row.period_end)];
  }
  form.target_amount = row.target_amount;
  form.target_quantity = row.target_quantity;

  if (availableShops.value.length === 0) await loadTargetShops();

  const detailResponse = await api.getTargetDetail(row.id);
  const breakdowns =
    detailResponse?.breakdowns || detailResponse?.breakdown || [];
  const shopList = breakdowns.filter((b) => b.breakdown_type === "shop");
  const total = Number(row.target_amount) || 1;
  shopBreakdown.value = shopList.map((b) => {
    const pct = total > 0 ? ((Number(b.target_amount) || 0) / total) * 100 : 0;
    return {
      shopKey: `${b.platform_code || ""}|${b.shop_id || ""}`,
      platform_code: b.platform_code,
      shop_id: b.shop_id,
      shop_name: b.shop_name || "",
      target_amount: b.target_amount ?? 0,
      target_quantity: b.target_quantity ?? 0,
      target_percent: Math.round(pct * 100) / 100,
      percentLocked: false,
    };
  });
  timeBreakdown.value =
    breakdowns.filter((b) => b.breakdown_type === "time") || [];

  breakdownTab.value = "shop";
  dialogVisible.value = true;
};

// 删除目标
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除目标"${row.target_name}"吗？`,
      "确认删除",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      },
    );

    await api.deleteTarget(row.id);
    ElMessage.success("删除成功");
    loadTargets();
  } catch (error) {
    // 用户取消或删除失败
  }
};

// 目标类型变化：店铺目标默认带出全部店铺行并均分百分比，产品/战役清空由用户手动添加
const handleTargetTypeChange = () => {
  timeBreakdown.value = [];
  if (form.target_type === "shop") {
    const list = availableShops.value || [];
    const n = Math.max(1, list.length);
    const pct = Math.round((100 / n) * 100) / 100;
    shopBreakdown.value = list.map((s, i) => ({
      shopKey: getShopKey(s),
      platform_code: s.platform_code,
      shop_id: s.shop_id,
      shop_name: s.shop_name || "",
      target_amount: 0,
      target_quantity: 0,
      target_percent: i === list.length - 1 ? 100 - pct * (n - 1) : pct,
      percentLocked: false,
    }));
  } else {
    shopBreakdown.value = [];
  }
};

// 添加店铺拆分（产品/战役时手动添加）
const handleAddShopBreakdown = () => {
  shopBreakdown.value.push({
    shopKey: "",
    platform_code: "",
    shop_id: "",
    shop_name: "",
    target_amount: 0,
    target_quantity: 0,
    target_percent: 0,
    percentLocked: false,
  });
};

// 删除店铺拆分
const handleRemoveShopBreakdown = (index) => {
  shopBreakdown.value.splice(index, 1);
  applyBalancePercent(-1);
};

// 店铺选择变化：根据 shopKey 回填 platform_code / shop_id / shop_name
const handleShopChange = (index, val) => {
  const s = availableShops.value.find((x) => getShopKey(x) === val);
  if (s) {
    const row = shopBreakdown.value[index];
    row.platform_code = s.platform_code;
    row.shop_id = s.shop_id;
    row.shop_name = s.shop_name || "";
  }
};

// 比例平衡：仅重算「未锁定」行的百分比，使总和 100%。用户修改过的行视为锁定，不再被自动改写。
// editedIndex 为本次修改的行索引，-1 表示全部均分（并清除所有锁定）
const applyBalancePercent = (editedIndex) => {
  const rows = shopBreakdown.value;
  if (rows.length === 0) return;
  if (editedIndex === -1 || rows.length === 1) {
    rows.forEach((r) => { r.percentLocked = false; });
    const each = Math.round((100 / rows.length) * 100) / 100;
    rows.forEach((r, i) => {
      r.target_percent =
        i === rows.length - 1 ? 100 - each * (rows.length - 1) : each;
    });
    return;
  }
  rows[editedIndex].percentLocked = true;
  const lockedSum = rows
    .filter((r) => r.percentLocked)
    .reduce((s, r) => s + (Number(r.target_percent) || 0), 0);
  let remainder = Math.round((100 - lockedSum) * 100) / 100;
  if (remainder < 0) {
    ElMessage.warning("已锁定比例之和不能超过 100%");
    remainder = 0;
  }
  const unlocked = rows.filter((r) => !r.percentLocked);
  if (unlocked.length === 0) return;
  const each = Math.round((remainder / unlocked.length) * 100) / 100;
  unlocked.forEach((r, i) => {
    r.target_percent =
      i === unlocked.length - 1
        ? Math.round((remainder - each * (unlocked.length - 1)) * 100) / 100
        : each;
  });
};

// 自动计算店铺拆分：按目标百分比 × 总目标 回填金额与数量，最后一行用余数保证总和一致
const handleAutoCalculateShop = () => {
  const rows = shopBreakdown.value;
  if (rows.length === 0) {
    ElMessage.warning("请先添加店铺或选择店铺目标以加载全部店铺");
    return;
  }
  const totalAmount = Number(form.target_amount) || 0;
  const totalQty = Number(form.target_quantity) || 0;
  let sumAmount = 0;
  let sumQty = 0;
  rows.forEach((item, index) => {
    const pct = (Number(item.target_percent) || 0) / 100;
    if (index === rows.length - 1) {
      item.target_amount = Math.round((totalAmount - sumAmount) * 100) / 100;
      item.target_quantity = totalQty - sumQty;
    } else {
      item.target_amount = Math.round(totalAmount * pct * 100) / 100;
      item.target_quantity = Math.floor(totalQty * pct);
      sumAmount += item.target_amount;
      sumQty += item.target_quantity;
    }
  });
  ElMessage.success("已按目标百分比回填金额与数量");
};

// 自动计算时间拆分
const handleAutoCalculateTime = () => {
  if (!form.dateRange || form.dateRange.length !== 2) {
    ElMessage.warning("请先选择时间周期");
    return;
  }

  const start = new Date(form.dateRange[0]);
  const end = new Date(form.dateRange[1]);
  const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
  const weeks = Math.ceil(days / 7);

  timeBreakdown.value = [];
  let currentDate = new Date(start);

  for (let i = 0; i < weeks; i++) {
    const weekStart = new Date(currentDate);
    let weekEnd = new Date(currentDate); // Fixed: changed from const to let
    weekEnd.setDate(weekEnd.getDate() + 6);
    if (weekEnd > end) weekEnd = new Date(end);

    const weekDays =
      Math.ceil((weekEnd - weekStart) / (1000 * 60 * 60 * 24)) + 1;
    const weekAmount = (form.target_amount / days) * weekDays;
    const weekQuantity = Math.floor((form.target_quantity / days) * weekDays);

    timeBreakdown.value.push({
      week: `第${i + 1}周`,
      period_start: weekStart.toISOString().split("T")[0],
      period_end: weekEnd.toISOString().split("T")[0],
      target_amount: weekAmount,
      target_quantity: weekQuantity,
    });

    currentDate.setDate(currentDate.getDate() + 7);
  }

  ElMessage.success("自动计算完成");
};

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return;

  if (form.target_type === "shop") {
    form.target_name = autoTargetName.value;
    if (!form.targetMonth) {
      ElMessage.warning("请选择目标月份");
      return;
    }
  }

  // 验证拆分总和
  if (breakdownTab.value === "shop") {
    const okAmount =
      Math.abs(shopBreakdownTotalAmount.value - form.target_amount) < 0.02;
    const okQty = shopBreakdownTotalQuantity.value === form.target_quantity;
    if (!okAmount || !okQty) {
      ElMessage.warning(
        "店铺拆分总和需等于总目标，可使用「自动计算」按百分比回填",
      );
      return;
    }
  } else {
    if (
      timeBreakdownTotalAmount.value !== form.target_amount ||
      timeBreakdownTotalQuantity.value !== form.target_quantity
    ) {
      ElMessage.warning("时间拆分总和必须等于总目标");
      return;
    }
  }

  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    submitting.value = true;
    try {
      let periodStart, periodEnd;
      if (form.target_type === "shop" && form.targetMonth) {
        const [y, m] = form.targetMonth.split("-");
        periodStart = `${y}-${m}-01`;
        const lastDay = new Date(parseInt(y, 10), parseInt(m, 10), 0);
        periodEnd = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, "0")}-${String(lastDay.getDate()).padStart(2, "0")}`;
      } else if (form.dateRange && form.dateRange.length === 2) {
        const d0 = form.dateRange[0];
        const d1 = form.dateRange[1];
        periodStart =
          typeof d0 === "string"
            ? d0.slice(0, 10)
            : d0.toISOString().slice(0, 10);
        periodEnd =
          typeof d1 === "string"
            ? d1.slice(0, 10)
            : d1.toISOString().slice(0, 10);
      } else {
        ElMessage.warning("请选择时间周期或目标月份");
        submitting.value = false;
        return;
      }

      const data = {
        target_name: form.target_name,
        target_type: form.target_type,
        period_start: periodStart,
        period_end: periodEnd,
        target_amount: form.target_amount,
        target_quantity: form.target_quantity,
      };

      let response;
      if (form.id) {
        response = await api.updateTarget(form.id, data);
      } else {
        response = await api.createTarget(data);
      }

      const targetId = response?.id ?? form.id;
      if (
        breakdownTab.value === "shop" &&
        shopBreakdown.value.length > 0 &&
        targetId
      ) {
        for (const row of shopBreakdown.value) {
          if (!row.platform_code || !row.shop_id) continue;
          await api.createTargetBreakdown(targetId, {
            breakdown_type: "shop",
            platform_code: row.platform_code,
            shop_id: row.shop_id,
            target_amount: row.target_amount ?? 0,
            target_quantity: row.target_quantity ?? 0,
          });
        }
      }

      ElMessage.success(form.id ? "更新成功" : "创建成功");
      dialogVisible.value = false;
      if (form.target_type === "shop") loadMonthlyTarget();
      else loadTargets();
    } catch (error) {
      handleApiError(error, { showMessage: true, logError: true });
    } finally {
      submitting.value = false;
    }
  });
};

// 关闭对话框
const handleDialogClose = () => {
  formRef.value?.resetFields();
  form.targetMonth = "";
  shopBreakdown.value = [];
  timeBreakdown.value = [];
};

// 导出
const handleExport = () => {
  ElMessage.info("导出功能开发中（Mock阶段）");
  // TODO: 实现Excel导出功能
};

// 辅助函数
const getTargetTypeLabel = (type) => {
  const map = {
    shop: "店铺目标",
    product: "产品目标",
    campaign: "战役目标",
  };
  return map[type] || type;
};

const getTargetTypeTagType = (type) => {
  const map = {
    shop: "success",
    product: "warning",
    campaign: "info",
  };
  return map[type] || "";
};

const getStatusLabel = (status) => {
  const map = {
    active: "进行中",
    completed: "已完成",
    cancelled: "已取消",
  };
  return map[status] || status;
};

const getStatusTagType = (status) => {
  const map = {
    active: "success",
    completed: "info",
    cancelled: "danger",
  };
  return map[status] || "";
};

watch(activeTab, (tab) => {
  if (tab === "shop") loadMonthlyTarget();
  else if (tab === "product" || tab === "campaign") {
    filters.targetType = tab;
    loadTargets();
  }
});

onMounted(() => {
  loadTargetShops();
  if (activeTab.value === "shop") loadMonthlyTarget();
  else {
    filters.targetType = activeTab.value;
    loadTargets();
  }
});
</script>

<style scoped>
.target-management {
  min-height: calc(100vh - var(--header-height));
}

.main-tabs {
  margin-bottom: 16px;
}

.month-picker {
  width: 160px;
  margin-right: 12px;
}

.month-bar,
.list-action-bar,
.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #909399;
}

.loading-icon {
  font-size: 24px;
  margin-right: 8px;
}

.summary-card,
.ratios-card,
.shop-breakdown-card,
.daily-calendar-card,
.shop-daily-card {
  margin-bottom: 16px;
}

.shop-daily-placeholder {
  padding: 24px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}

.header-action-right {
  float: right;
}

.header-action-gap {
  margin-left: 8px;
}

.weekday-ratio-input {
  width: 100px;
}

.shop-selector {
  width: 280px;
  margin-bottom: 12px;
}

.target-pagination {
  margin-top: 20px;
  justify-content: flex-end;
}

.breakdown-summary {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}
.action-bar {
  display: flex;
  align-items: center;
}

/* 企业级表格样式 */
.erp-table :deep(.el-table__fixed-left) {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table__fixed-right) {
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.form-hint {
  display: block;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.breakdown-hint {
  font-size: 12px;
  color: #606266;
  margin-right: 8px;
}

.breakdown-hint--warn {
  color: #e6a23c;
}

/* 错误状态样式 */
.error-state {
  padding: 40px 20px;
  text-align: center;
}

.error-state :deep(.el-result__title) {
  font-size: 16px;
  color: #303133;
}

.error-state :deep(.el-result__subtitle) {
  font-size: 14px;
  color: #909399;
}

/* 日度分解日历格子 */
.daily-cell {
  min-height: 70px;
  padding: 4px;
  font-size: 12px;
  cursor: default;
}
.daily-cell.in-range {
  cursor: pointer;
  background: #ecf5ff;
  border-radius: 4px;
}
.daily-cell.in-range:hover {
  background: #d9ecff;
}
.daily-cell.out-range {
  color: #c0c4cc;
}
.day-num {
  display: block;
  font-weight: 600;
  margin-bottom: 2px;
}
.daily-target {
  color: #409eff;
  font-size: 11px;
}
.daily-achieved {
  color: #67c23a;
  font-size: 11px;
}
.daily-rate {
  margin-top: 2px;
  display: inline-block;
}
.daily-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

/* 周一到周日拆分比例 */
.weekday-ratios-hint {
  font-size: 12px;
  color: #606266;
  margin-bottom: 12px;
}
.weekday-ratios-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
}
.weekday-ratio-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.weekday-ratio-item label {
  width: 36px;
  font-size: 13px;
  color: #303133;
}
.weekday-pct {
  font-size: 12px;
  color: #909399;
  min-width: 40px;
}
.weekday-ratios-sum {
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
}
</style>
