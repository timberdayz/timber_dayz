<template>
  <div class="shop-assignment-page erp-page-container">
    <PageHeader
      title="人员店铺归属和提成比"
      family="admin"
      compact
    >
      <template #subtitle>
        配置员工负责的店铺及提成比例，用于后续提成计算。本模块仅管理员可见。<strong>页面上的钱一律由后端算</strong>（提成 = 可分配利润 × 归属提成比，零系数；绩效系数只影响绩效工资，不参与提成），前端不再自己算钱；「改了还没保存」的临时编辑会调后端试算接口取数。配置保存至数据库表 <code>a_class.employee_shop_assignments</code>。
      </template>
    </PageHeader>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="assignment-tabs">
      <el-tab-pane label="人员店铺归属和提成比配置" name="config">
        <template #label>
          <span><el-icon><Setting /></el-icon> 配置</span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="店铺利润和人员利润统计" name="stats">
        <template #label>
          <span><el-icon><DataAnalysis /></el-icon> 统计</span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="年度统计" name="annual">
        <template #label>
          <span><el-icon><Calendar /></el-icon> 年度统计</span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 配置子页：以店铺为行，直接显示可用店铺，行内编辑 -->
    <div v-if="activeTab === 'config'">
      <div class="action-bar">
        <el-date-picker
          v-model="configMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          class="erp-w-180"
          @change="handleConfigMonthChange"
        />
        <el-button type="warning" @click="handleCopyFromPrevMonth" :loading="copyLoading" :disabled="!configMonth">
          复制上月配置
        </el-button>
        <el-button type="success" @click="handleBatchSave" :loading="batchSaving">
          批量保存
        </el-button>
        <el-button @click="loadConfigData">
          刷新
        </el-button>
      </div>
      <div v-if="employeeCommissionSummary.length > 0" class="commission-summary-strip">
        <div class="commission-summary-title">员工月度预计提成（实发口径）</div>
        <div class="commission-summary-items">
          <div v-for="item in employeeCommissionSummary" :key="item.employee_code" class="commission-summary-item">
            <span class="commission-summary-name">{{ item.employee_name || item.employee_code }}</span>
            <span class="commission-summary-position">{{ item.position_name }}</span>
            <el-tag
              v-if="employeeStatusTag(item.calculation_status)"
              size="small"
              :type="employeeStatusTag(item.calculation_status).type"
            >
              {{ employeeStatusTag(item.calculation_status).label }}
            </el-tag>
            <span class="commission-summary-amount">¥{{ formatNumber(item.estimated_commission) }}</span>
            <span class="commission-summary-shops">{{ item.shop_count }}店 · 绩效系数 {{ formatCoefficient(item.score_coefficient) }}</span>
          </div>
        </div>
      </div>
      <div v-if="selectedShops.length > 0" class="batch-toolbar">
        <span class="batch-toolbar-count">已选 {{ selectedShops.length }} 家店铺</span>
        <el-button size="small" type="primary" @click="openBatchAttachDialog">批量挂靠</el-button>
        <el-button size="small" type="warning" @click="openBatchRatioDialog">批量调整比例</el-button>
        <el-button size="small" type="danger" @click="handleBatchRemove">批量移除</el-button>
        <el-button size="small" @click="clearShopSelection">清空选择</el-button>
      </div>
      <el-card>
        <el-table
          ref="configTableRef"
          :data="configTableRows"
          stripe
          v-loading="configLoading"
          class="erp-table erp-compact"
          border
          :span-method="configSpanMethod"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="46" fixed="left" :selectable="isShopFirstRow" />
          <el-table-column label="平台" width="100" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row._isFirst">{{ row.platform_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="店铺" width="200" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <div v-if="row._isFirst" class="shop-display-cell">
                <div class="shop-display-head">
                  <span class="shop-display-name">{{ row.shop_name }}</span>
                  <!--
                    「+ 添加人员」放在**固定左侧**的店铺列（2026-11-28 密度改造）：
                    人员列在横向滚动区之外（表宽 2446px > 视口），按钮原先落在
                    滚动区里，整行看起来是空的 —— 现在任何屏宽下都能看见入口。
                    与店铺名同行，避免把行撑成三行。
                  -->
                  <el-button
                    v-if="row._isAddRow"
                    size="small"
                    link
                    type="primary"
                    class="add-person-button"
                    @click="openAddForShop(row._shop)"
                  >
                    + 添加人员
                  </el-button>
                </div>
                <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
              </div>
              <el-button
                v-else-if="row._isAddRow"
                size="small"
                link
                type="primary"
                class="add-person-button"
                @click="openAddForShop(row._shop)"
              >
                + 添加人员
              </el-button>
            </template>
          </el-table-column>
          <el-table-column label="当月销售额" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">¥{{ formatNumber(row.monthly_sales) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当月利润" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">¥{{ formatNumber(row.monthly_profit) }}</span>
            </template>
          </el-table-column>
          <el-table-column width="150" align="right">
            <template #header>
              <el-tooltip :content="PROFIT_BASIS_REFERENCE_HINT" placement="top">
                <span>结算基数（参考）</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span v-if="row._isFirst">¥{{ formatNumber(row.profit_basis_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="成本明细" width="180" align="right">
            <template #default="{ row }">
              <div v-if="row._isFirst" class="cost-summary-cell">
                <el-tooltip placement="top" :show-after="150">
                  <template #content>
                    <div class="cost-tooltip">
                      <div>其他经营成本 ¥{{ formatNumber(row.other_a_class_cost_amount) }}</div>
                      <div>提成前人力成本 ¥{{ formatNumber(row.pre_commission_labor_cost_amount) }}</div>
                      <div>A类成本 ¥{{ formatNumber(row.a_class_cost_amount) }}</div>
                      <div class="cost-tooltip-tags">
                        <el-tag size="small" type="info">{{ formatBasisVersion(row.basis_version) }}</el-tag>
                        <el-tag v-if="isLaborAllocationMissing(row)" size="small" type="danger">缺少人力成本分摊</el-tag>
                      </div>
                    </div>
                  </template>
                  <span class="cost-summary-text">
                    ¥{{ formatNumber(row.other_a_class_cost_amount) }} / ¥{{ formatNumber(row.pre_commission_labor_cost_amount) }} / ¥{{ formatNumber(row.a_class_cost_amount) }}
                  </span>
                </el-tooltip>
                <el-tag
                  v-if="isLaborAllocationMissing(row)"
                  size="small"
                  type="danger"
                  class="cost-summary-alert"
                >
                  缺分摊
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="当月目标达成率" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">{{ row.achievement_rate != null ? Number(row.achievement_rate).toFixed(1) + '%' : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="可分配净利润率" width="180" align="right">
            <template #default="{ row }">
              <!--
                密度改造（2026-11-28）：输入框与状态标签**同行**。
                原先 .allocatable-rate-wrap 是 width:100% 的 inline-flex，
                会把状态标签挤到第二行 —— 单元格高度 48px，整行被撑到 57px。
                标签是「未配置 / 待保存」这类必须可见的状态，不能挪进 tooltip。
              -->
              <span v-if="row._isFirst" class="allocatable-rate-cell">
                <span class="allocatable-rate-wrap">
                  <el-input-number
                    :model-value="(row.allocatable_profit_rate ?? 0) * 100"
                    @update:model-value="(v) => { setShopAllocatableProfitRate(row, v); scheduleEstimate() }"
                    :min="0"
                    :max="100"
                    :step="0.01"
                    :precision="2"
                    :controls="false"
                    placeholder="0-100%"
                    size="small"
                    class="allocatable-rate-input"
                  />
                  <span class="allocatable-rate-suffix">%</span>
                </span>
                <span class="rate-status-cell">
                  <el-tag size="small" :type="allocatableRateTag(row).type">{{ allocatableRateTag(row).label }}</el-tag>
                  <el-tag v-if="isShopRateDirty(row)" size="small" type="warning">待保存</el-tag>
                </span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="可分配利润" width="140" align="right">
            <template #default="{ row }">
              <span v-if="row._isFirst">
                <span v-if="getRowAllocatableProfit(row) != null">¥{{ formatNumber(getRowAllocatableProfit(row)) }}</span>
                <span v-else class="fallback-text">—</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="人员" width="180" min-width="160">
            <template #header>
              <el-tooltip content="层级取自员工档案的职位名（只读、不落库），未设岗位显示「（未设岗位）」" placement="top">
                <span>人员</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <template v-if="!row._isAddRow">
                <span class="person-cell">
                  <el-tooltip
                    v-if="row._person"
                    content="共同承接店铺目标"
                    placement="top"
                  >
                    <el-tag size="small" type="info" class="person-cell-tag">
                      共担目标
                    </el-tag>
                  </el-tooltip>
                  <span class="person-cell-name">
                    {{ (row._person && (row._person.employee_name || row._person.employee_code)) || '' }}
                  </span>
                  <el-tag
                    v-if="row._person"
                    size="small"
                    type="info"
                    class="person-cell-position"
                  >
                    {{ positionNameOf(row._person.employee_code) }}
                  </el-tag>
                  <el-button v-if="row._person" size="small" link type="danger" @click="removePersonLocal(row._shop, row._person)">×</el-button>
                </span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="提成比例" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row._person" class="allocatable-rate-wrap">
                <el-input-number
                  :model-value="((row._person && row._person.commission_ratio) ?? 0) * 100"
                  @update:model-value="(v) => { if (row._person) row._person.commission_ratio = v != null ? Number(v) / 100 : 0; scheduleEstimate() }"
                  :min="0"
                  :max="100"
                  :step="0.01"
                  :precision="2"
                  :controls="false"
                  placeholder="0-100%"
                  size="small"
                  class="allocatable-rate-input"
                />
                <span class="allocatable-rate-suffix">%</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="绩效系数（仅影响绩效工资）" width="200" align="right">
            <template #default="{ row }">
              <el-tooltip content="该员工的个人绩效分数档位系数。它只影响绩效工资，不参与提成金额。" placement="top">
                <span v-if="row._person">{{ formatCoefficient(performanceCoefficientOf(row)) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="预计提成（实发口径）" width="210" align="right">
            <template #default="{ row }">
              <span v-if="row._person">
                <el-tooltip v-if="zeroReasonOf(row)" :content="zeroReasonOf(row)" placement="top">
                  <span class="commission-amount">¥{{ formatNumber(getRowEstimatedCommission(row)) }}</span>
                </el-tooltip>
                <span v-else class="commission-amount">¥{{ formatNumber(getRowEstimatedCommission(row)) }}</span>
                <el-tag v-if="estimateTagOf(row)" size="small" :type="estimateTagOf(row).type" style="margin-left: 4px;">{{ estimateTagOf(row).label }}</el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="220" align="center">
            <template #default="{ row }">
              <div class="status-cell">
                <template v-if="row._isFirst">
                  <el-tag v-if="hasConfig(row)" type="success" size="small">已配置</el-tag>
                  <el-tag v-else type="info" size="small">未配置</el-tag>
                  <el-tooltip v-if="shopProfitTag(row)" :content="shopProfitTag(row).text" placement="top">
                    <el-tag size="small" :type="shopProfitTag(row).type">{{ shopProfitTag(row).label }}</el-tag>
                  </el-tooltip>
                </template>
                <el-tag v-if="row._person && employeeStatusTagOf(row)" size="small" :type="employeeStatusTagOf(row).type">
                  {{ employeeStatusTagOf(row).label }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <template v-if="row._isFirst">
                <el-button size="small" type="primary" @click="handleSaveRow(row)" :loading="row.saving">
                  保存
                </el-button>
                <el-button size="small" type="danger" @click="handleDeleteRow(row)" :disabled="!hasConfig(row)">
                  删除
                </el-button>
              </template>
              <span v-else></span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 统计子页：按月份展示 -->
    <div v-if="activeTab === 'stats'">
      <div class="action-bar">
        <el-date-picker
          v-model="statsMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          class="erp-w-180"
          @change="loadStatsData"
        />
        <el-button size="small" @click="loadStatsData">刷新</el-button>
      </div>
      <el-card>
        <el-table :data="statsRows" stripe v-loading="statsLoading" class="erp-table erp-compact" border>
          <el-table-column prop="platform_code" label="平台" width="100" fixed="left" />
          <el-table-column prop="shop_name" label="店铺" width="200" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="shop-display-cell">
                <div>{{ row.shop_name }}</div>
                <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="monthly_sales" label="当月销售额" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.monthly_sales) }}</template>
          </el-table-column>
          <el-table-column prop="monthly_profit" label="当月利润" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.monthly_profit) }}</template>
          </el-table-column>
          <el-table-column width="150" align="right">
            <template #header>
              <el-tooltip :content="PROFIT_BASIS_REFERENCE_HINT" placement="top">
                <span>结算基数（参考）</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">¥{{ formatNumber(row.profit_basis_amount) }}</template>
          </el-table-column>
          <el-table-column label="成本明细" width="180" align="right">
            <template #default="{ row }">
              <div class="cost-summary-cell">
                <el-tooltip placement="top" :show-after="150">
                  <template #content>
                    <div class="cost-tooltip">
                      <div>其他经营成本 ¥{{ formatNumber(row.other_a_class_cost_amount) }}</div>
                      <div>提成前人力成本 ¥{{ formatNumber(row.pre_commission_labor_cost_amount) }}</div>
                      <div>A类成本 ¥{{ formatNumber(row.a_class_cost_amount) }}</div>
                      <div class="cost-tooltip-tags">
                        <el-tag size="small" type="info">{{ formatBasisVersion(row.basis_version) }}</el-tag>
                        <el-tag v-if="isLaborAllocationMissing(row)" size="small" type="danger">缺少人力成本分摊</el-tag>
                      </div>
                    </div>
                  </template>
                  <span class="cost-summary-text">
                    ¥{{ formatNumber(row.other_a_class_cost_amount) }} / ¥{{ formatNumber(row.pre_commission_labor_cost_amount) }} / ¥{{ formatNumber(row.a_class_cost_amount) }}
                  </span>
                </el-tooltip>
                <el-tag
                  v-if="isLaborAllocationMissing(row)"
                  size="small"
                  type="danger"
                  class="cost-summary-alert"
                >
                  缺分摊
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="当月目标达成率" width="140" align="right">
            <template #default="{ row }">{{ row.achievement_rate != null ? Number(row.achievement_rate).toFixed(1) + '%' : '—' }}</template>
          </el-table-column>
          <el-table-column label="可分配率" width="120" align="right">
            <template #default="{ row }">
              <el-tooltip :content="allocatableRateTag(row).text" placement="top">
                <el-tag size="small" :type="allocatableRateTag(row).type">{{ allocatableRateTag(row).label }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="预计提成（实发口径）" width="190" align="right">
            <template #default="{ row }">
              <el-tooltip content="该店当月实发提成合计 = 可分配利润 × 归属提成比（零系数）。店铺赛马评级与个人绩效分数都不参与提成金额。" placement="top">
                <span>¥{{ formatNumber(row.settlement_commission_amount) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="200" align="center">
            <template #default="{ row }">
              <div class="status-cell">
                <el-tooltip v-if="shopProfitTag(row)" :content="shopProfitTag(row).text" placement="top">
                  <el-tag size="small" :type="shopProfitTag(row).type">{{ shopProfitTag(row).label }}</el-tag>
                </el-tooltip>
                <el-tooltip v-if="formatCommissionZeroReason(row.commission_zero_reason)" :content="formatCommissionZeroReason(row.commission_zero_reason)" placement="top">
                  <el-tag size="small" type="warning">提成为 0</el-tag>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="statsRows.length === 0 && !statsLoading" style="padding: 40px; text-align: center; color: #909399;">
          暂无统计数据，请先配置店铺归属并确保有订单数据
        </div>
      </el-card>
    </div>

    <!-- 年度统计子页：按人员 / 按店铺 -->
    <div v-if="activeTab === 'annual'">
      <div class="action-bar">
        <el-date-picker
          v-model="annualYear"
          type="year"
          placeholder="选择年份"
          value-format="YYYY"
          size="default"
          class="erp-w-150"
          @change="loadAnnualData"
        />
        <el-radio-group v-model="annualGroupBy" size="default">
          <el-radio-button value="employee">按人员</el-radio-button>
          <el-radio-button value="shop">按店铺</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="loadAnnualData">刷新</el-button>
      </div>
      <el-card>
        <!-- 按人员：员工 x 1月..12月 x 年度合计 -->
        <el-table
          v-if="annualGroupBy === 'employee'"
          :data="annualByEmployee"
          stripe
          v-loading="annualLoading"
          class="erp-table erp-compact"
          border
        >
          <el-table-column prop="employee_code" label="员工工号" width="120" fixed="left" />
          <el-table-column prop="employee_name" label="姓名" width="100" fixed="left" />
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="100" align="right">
            <template #default="{ row }">
              ¥{{ formatNumber(row.months && row.months[String(m).padStart(2, '0')]) }}
            </template>
          </el-table-column>
          <el-table-column label="年度合计" width="120" align="right" fixed="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_profit) }}</template>
          </el-table-column>
        </el-table>
        <!-- 按店铺：店铺 x 1月..12月(当月利润) x 年度合计 -->
        <el-table
          v-else
          :data="annualByShop"
          stripe
          v-loading="annualLoading"
          class="erp-table erp-compact"
          border
        >
          <el-table-column prop="platform_code" label="平台" width="100" fixed="left" />
          <el-table-column prop="shop_name" label="店铺" width="200" fixed="left" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="shop-display-cell">
                <div>{{ row.shop_name }}</div>
                <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月利润`" width="110" align="right">
            <template #default="{ row }">
              ¥{{ formatNumber(row.months && row.months[String(m).padStart(2, '0')] && row.months[String(m).padStart(2, '0')].monthly_profit) }}
            </template>
          </el-table-column>
          <el-table-column label="年度销售额" width="120" align="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_sales) }}</template>
          </el-table-column>
          <el-table-column label="年度利润" width="120" align="right" fixed="right">
            <template #default="{ row }">¥{{ formatNumber(row.year_total_profit) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="(annualGroupBy === 'employee' ? annualByEmployee.length : annualByShop.length) === 0 && !annualLoading" style="padding: 40px; text-align: center; color: #909399;">
          暂无年度数据，请选择年份并确保该年有归属配置与订单数据
        </div>
      </el-card>
    </div>

    <!-- 新增/编辑归属弹窗 -->
    <el-dialog v-model="dialogVisible" :title="addForShopRow ? '添加人员' : '新增归属'" width="500px" @close="resetForm">
      <el-form :model="form" label-width="100px">
        <el-form-item v-if="addForShopRow" label="店铺">
          <el-input :value="addForShopRow.shop_name || addForShopRow.shop_id" disabled />
          <div v-if="addForShopRow.secondary_name" class="shop-display-secondary dialog-shop-secondary">{{ addForShopRow.secondary_name }}</div>
        </el-form-item>
        <el-form-item label="员工" required>
          <el-select v-model="form.employee_code" placeholder="选择员工" filterable style="width: 100%;">
            <el-option
              v-for="e in employeesActive"
              :key="e.employee_code"
              :label="`${e.name} (${e.employee_code}${e.position_name ? ' / ' + e.position_name : ''})`"
              :value="e.employee_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!addForShopRow" label="平台" required>
          <el-select v-model="form.platform_code" placeholder="选择平台" style="width: 100%;" @change="onPlatformChange">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="妙手" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!addForShopRow" label="店铺" required>
          <el-select v-model="form.shop_id" placeholder="选择店铺" filterable style="width: 100%;">
            <el-option v-for="s in shopsFiltered" :key="`${s.platform_code}-${s.shop_id}`" :label="s.option_label || s.shop_name || s.shop_id" :value="s.shop_id">
              <div>{{ s.shop_name || s.shop_id }}</div>
              <div v-if="s.secondary_name" class="shop-display-secondary">{{ s.secondary_name }}</div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="提成比例" required>
          <span class="allocatable-rate-wrap">
            <el-input-number
              :model-value="(form.commission_ratio ?? 0) * 100"
              @update:model-value="(v) => { form.commission_ratio = v != null ? Number(v) / 100 : 0 }"
              :min="0"
              :max="100"
              :step="0.01"
              :precision="2"
              placeholder="0-100%"
              style="width: 100%;"
            />
            <span class="allocatable-rate-suffix">%</span>
          </span>
        </el-form-item>
        <el-form-item label="目标承接方式">
          <el-tag type="info">共同承接店铺目标</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitForm">{{ addForShopRow ? '添加' : '新增' }}</el-button>
      </template>
    </el-dialog>

    <!-- 批量挂靠人员：选中的店铺 + 1 名员工 + 统一提成比例 -->
    <el-dialog v-model="batchAttachVisible" title="批量挂靠人员" width="520px">
      <el-form label-width="100px">
        <el-form-item label="店铺">
          <span>已选 {{ selectedShops.length }} 家店铺</span>
          <div class="batch-shop-preview">
            <div v-for="shop in selectedShops.slice(0, 6)" :key="shopKeyOf(shop)">
              {{ shop.shop_name || shop.shop_id }}
            </div>
            <div v-if="selectedShops.length > 6">等 {{ selectedShops.length }} 家店铺</div>
          </div>
        </el-form-item>
        <el-form-item label="员工" required>
          <el-select v-model="batchForm.employee_code" placeholder="选择员工" filterable style="width: 100%;">
            <el-option
              v-for="e in employeesActive"
              :key="e.employee_code"
              :label="`${e.name} (${e.employee_code}${e.position_name ? ' / ' + e.position_name : ''})`"
              :value="e.employee_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="提成比例" required>
          <span class="allocatable-rate-wrap">
            <el-input-number
              :model-value="(batchForm.commission_ratio ?? 0) * 100"
              @update:model-value="(v) => { batchForm.commission_ratio = v != null ? Number(v) / 100 : 0 }"
              :min="0"
              :max="100"
              :step="0.01"
              :precision="2"
              :controls="false"
              placeholder="0-100%"
              style="width: 100%;"
            />
            <span class="allocatable-rate-suffix">%</span>
          </span>
        </el-form-item>
        <el-form-item v-if="batchAttachOverflowShops.length > 0" label="超限预检">
          <el-alert
            type="warning"
            :closable="false"
            :title="`以下 ${batchAttachOverflowShops.length} 家店铺加上该比例后会超过 100%，提交后由后端逐店判定`"
          />
          <div class="batch-overflow-list">
            <div v-for="shop in batchAttachOverflowShops" :key="shopKeyOf(shop)">
              {{ shop.shop_name || shop.shop_id }}
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchAttachVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="submitBatchAttach">确认提交</el-button>
      </template>
    </el-dialog>

    <!-- 批量调整提成比例：选中店铺里已配置的人员行统一设比例 -->
    <el-dialog v-model="batchRatioVisible" title="批量调整提成比例" width="520px">
      <el-form label-width="100px">
        <el-form-item label="影响范围">
          <span>已选 {{ selectedShops.length }} 家店铺，共 {{ batchTargetRows.length }} 条人员归属</span>
        </el-form-item>
        <el-form-item v-if="batchUnsavedRows.length > 0" label="未保存行">
          <el-alert
            type="info"
            :closable="false"
            :title="`有 ${batchUnsavedRows.length} 条人员是本地新增、还没保存，批量改比例只作用于已保存的归属`"
          />
        </el-form-item>
        <el-form-item label="提成比例" required>
          <span class="allocatable-rate-wrap">
            <el-input-number
              :model-value="(batchForm.commission_ratio ?? 0) * 100"
              @update:model-value="(v) => { batchForm.commission_ratio = v != null ? Number(v) / 100 : 0 }"
              :min="0"
              :max="100"
              :step="0.01"
              :precision="2"
              :controls="false"
              placeholder="0-100%"
              style="width: 100%;"
            />
            <span class="allocatable-rate-suffix">%</span>
          </span>
        </el-form-item>
        <el-form-item v-if="batchRatioOverflowShops.length > 0" label="超限预检">
          <el-alert
            type="warning"
            :closable="false"
            :title="`以下 ${batchRatioOverflowShops.length} 家店铺按新比例合计会超过 100%，提交后由后端逐店判定`"
          />
          <div class="batch-overflow-list">
            <div v-for="shop in batchRatioOverflowShops" :key="shopKeyOf(shop)">
              {{ shop.shop_name || shop.shop_id }}
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchRatioVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="submitBatchRatio">确认提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Setting, DataAnalysis, Calendar } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  buildBatchCreateItems,
  buildBatchUpdatePayload,
  buildPositionNameMap,
  collectAssignmentIds,
  collectEstimateOverrides,
  exceedsCommissionRatioLimit,
  indexEstimateRows,
  isAssignmentDirty,
  readBackendAllocatableProfit,
  resolveEstimatedCommission,
  resolvePositionName,
  setShopAllocatableProfitRate,
  summarizeEmployeeCommissions,
  sumCommissionRatio
} from './shopAssignmentRules'
import {
  describeAllocatableRate,
  describeShopProfitTag,
  employeeCalculationStatusTag as employeeStatusTag,
  formatBasisVersion,
  formatCommissionZeroReason,
  formatCoefficient,
  PROFIT_BASIS_REFERENCE_HINT
} from './settlementDisplayRules'
import { buildShopAccountLookup, decorateShopEntity } from '@/utils/shopDisplay'

const activeTab = ref('config')
const configMonth = ref(new Date().toISOString().slice(0, 7))  // YYYY-MM
const statsMonth = ref(new Date().toISOString().slice(0, 7))
const copyLoading = ref(false)
const batchSaving = ref(false)

const shopRows = ref([])
const configLoading = ref(false)
const statsRows = ref([])
const statsLoading = ref(false)
// 后端结算预览（GET /hr/commissions/settlement-preview）：页面上的钱以它为准。
const settlementPreviewEmployees = ref([])
// 后端试算结果（改了还没保存时，后端按同一套口径算出来的钱）。
// ⚠️ 前端**不自己算钱**：只把「待保存的输入」发给后端，页面渲染返回的金额。
const estimateRows = ref(new Map())
const estimateLoading = ref(false)
let estimateTimer = null

const annualYear = ref(new Date().getFullYear().toString())
const annualGroupBy = ref('employee')
const annualLoading = ref(false)
const annualData = ref({ year: null, by_employee: [], by_shop: [] })
let shopAccountLookup = new Map()

const annualByEmployee = computed(() => annualData.value.by_employee || [])
const annualByShop = computed(() => (annualData.value.by_shop || []).map((row) => decorateShopEntity(row, shopAccountLookup)))

const employees = ref([])
const employeesActive = computed(() => employees.value.filter((e) => e.status === 'active'))
const shops = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const addForShopRow = ref(null)
const submitLoading = ref(false)
const form = ref({
  employee_code: '',
  platform_code: '',
  shop_id: '',
  commission_ratio: 0.05
})

// 批量操作：选中的店铺（表格多选）、批量弹窗与提交状态。
const configTableRef = ref(null)
const selectedShops = ref([])
const batchAttachVisible = ref(false)
const batchRatioVisible = ref(false)
const batchSubmitting = ref(false)
const batchForm = ref({ employee_code: '', commission_ratio: 0.05 })

const shopsFiltered = computed(() => {
  const pc = form.value.platform_code
  if (!pc) return shops.value
  return shops.value.filter((s) => (s.platform_code || '').toLowerCase() === (pc || '').toLowerCase())
})
// 层级只是展示：职位名来自员工档案（不落库、不需要用户勾选）。
// ⚠️ 这里必须用**全量**员工名单，而不是在职名单：离职员工的归属行是历史事实
// （工资单、绩效、提成审计都还指向他），若只取在职名单，他会在归属行里
// 被误显示成「（未设岗位）」。下拉选人仍然只给在职员工（employeesActive）。
const positionByEmployee = computed(() => buildPositionNameMap(employees.value))

// 员工月度预计提成：金额直接读后端 expected_commission，前端不再自己累加。
const employeeCommissionSummary = computed(() => summarizeEmployeeCommissions(settlementPreviewEmployees.value, positionByEmployee.value))

// 配置表 flattened 行：一店多人，每行一个人员或“添加”占位
const configTableRows = computed(() => {
  const rows = []
  for (const shop of shopRows.value) {
    const assignments = shop.assignments || []
    const shopKey = `${shop.platform_code}|${shop.shop_id}`
    let isFirst = true
    for (const p of assignments) {
      rows.push({
        ...shop,
        _shop: shop,
        _person: p,
        _isAddRow: false,
        _isFirst: isFirst,
        _shopKey: shopKey
      })
      isFirst = false
    }
    rows.push({
      ...shop,
      _shop: shop,
      _person: null,
      _isAddRow: true,
      _isFirst: isFirst,
      _shopKey: shopKey
    })
  }
  return rows
})

// 不再使用 rowspan:0 隐藏单元格，避免固定列 + 部分隐藏导致的错位。每行各占一单元格，非首行用 v-if 显示空。
function configSpanMethod() {
  return { rowspan: 1, colspan: 1 }
}

function formatNumber(v) {
  if (v == null || v === '') return '0.00'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function isLaborAllocationMissing(row) {
  return [
    'missing_labor_allocation',
    'pending_labor_allocation',
    'data_incomplete'
  ].includes(String(row?.cost_status || '').toLowerCase())
}

// 口径 / 成本状态一律用后端返回的值，前端不再补默认值：
// 前端拼一个 basis_version 或 cost_status 只会让页面显示出一个后端并不认可的口径。
function normalizeProfitBasisFields(row = {}) {
  return {
    ...row,
    other_a_class_cost_amount: row.other_a_class_cost_amount ?? 0,
    pre_commission_labor_cost_amount: row.pre_commission_labor_cost_amount ?? 0,
    a_class_cost_amount: row.a_class_cost_amount ?? 0,
    basis_version: row.basis_version ?? '',
    cost_status: row.cost_status ?? ''
  }
}

// 可分配利润：后端已经算好（max(利润基数, 0) × 可分配率，并按 2 位小数舍入）。
function getRowAllocatableProfit(row) {
  return readBackendAllocatableProfit(row?._shop || row)
}

// 预计提成：两条路径都是**后端算的**。
//   * 没改过        → 后端结算预览返回的金额；
//   * 改了还没保存  → 后端试算接口按同一套口径算出的金额。
// 前端不做任何乘法。
function getRowEstimatedCommission(row) {
  if (!row?._person) return 0
  const preview = row._person._preview || null
  const estimate = estimateAmountOf(row)
  return resolveEstimatedCommission({
    backendEstimatedCommission: preview?.estimated_commission ?? null,
    estimateAmount: estimate
  })
}

// 这一行的后端试算金额（没有试算结果时返回 null）。
function estimateAmountOf(row) {
  if (!row?._person) return null
  const person = row._person
  const shop = row?._shop || row
  const key = `${String(person.employee_code ?? '').trim()}|${String(shop?.platform_code ?? '').trim().toLowerCase()}|${String(shop?.shop_id ?? '').trim()}`
  const hit = estimateRows.value.get(key)
  return hit ? hit.estimated_commission : null
}

// 「试算」标签：只有真的拿到后端试算金额才标「试算」，
// 否则区分「还在算」和「还没算出来」。
function estimateTagOf(row) {
  if (!isRowDirty(row)) return null
  if (estimateAmountOf(row) != null) return { label: '试算', type: 'warning' }
  if (estimateLoading.value) return { label: '计算中', type: 'info' }
  return { label: '待试算', type: 'info' }
}

// 可分配率是否被改过（还没保存）。
function isShopRateDirty(row) {
  const shop = row?._shop || row
  const current = Number(shop?.allocatable_profit_rate ?? 0)
  const backend = Number(shop?._backend_allocatable_profit_rate ?? current)
  return Math.abs(current - backend) > 1e-9
}

// 整行是否被改过（可分配率或归属提成比）。
function isRowDirty(row) {
  if (!row) return false
  return isShopRateDirty(row) || isAssignmentDirty(row?._shop || row, row?._person)
}

// 把「改了还没保存」的输入交给后端试算。
// ⚠️ 前端只传**输入**（可分配率、归属提成比），金额一律由后端算。
async function refreshEstimate() {
  const dirty = configTableRows.value.filter((row) => row?._person && isRowDirty(row))
  if (dirty.length === 0) {
    estimateRows.value = new Map()
    return
  }
  const overrides = collectEstimateOverrides(dirty, (row) => isRowDirty(row))
  if (overrides.length === 0) {
    estimateRows.value = new Map()
    return
  }
  estimateLoading.value = true
  try {
    const res = await api.postHrCommissionSettlementEstimate({
      year_month: configMonth.value,
      overrides
    })
    const payload = res?.data ?? {}
    estimateRows.value = indexEstimateRows(payload?.rows ?? [])
  } catch (e) {
    estimateRows.value = new Map()
    ElMessage.warning(e?.response?.data?.detail || e?.message || '试算失败，请稍后重试')
  } finally {
    estimateLoading.value = false
  }
}

// 连续输入时防抖，避免每敲一个数字都打一次后端。
function scheduleEstimate() {
  if (estimateTimer) clearTimeout(estimateTimer)
  estimateTimer = setTimeout(() => {
    estimateTimer = null
    refreshEstimate()
  }, 300)
}

// 绩效系数（后端下发的个人分数档位系数，缺失显示「—」而不是 0）。
// ⚠️ 它只影响绩效工资，**不参与提成金额**（提成零系数）。
function performanceCoefficientOf(row) {
  return row?._person?._preview?.score_coefficient ?? null
}

// 提成为 0 的业务原因（后端下发），让「0」变成一句能行动的话。
function zeroReasonOf(row) {
  return formatCommissionZeroReason(row?._person?._preview?.commission_zero_reason)
}

// 员工考核状态徽标。
function employeeStatusTagOf(row) {
  return employeeStatusTag(row?._person?._employee_status)
}

// 可分配率三态（未配置 / 配成 0 / 正常）。
function allocatableRateTag(row) {
  const shop = row?._shop || row
  return describeAllocatableRate(shop?.is_allocatable_rate_configured, shop?.allocatable_profit_rate)
}

// 店铺亏损徽标。
function shopProfitTag(row) {
  return describeShopProfitTag(row?._shop || row)
}

function onPlatformChange() {
  form.value.shop_id = ''
}

// 员工的职位名（层级只是展示，来自员工档案）。
function positionNameOf(employeeCode) {
  return resolvePositionName(employeeCode, positionByEmployee.value)
}

function resetForm() {
  form.value = { employee_code: '', platform_code: '', shop_id: '', commission_ratio: 0.05 }
  editId.value = null
  isEdit.value = false
  addForShopRow.value = null
}

function hasConfig(row) {
  const assignments = row.assignments || row._shop?.assignments
  return (assignments && assignments.length > 0) || (Number(row.allocatable_profit_rate) ?? 0) > 0
}

function validateShopAssignmentRatio(shop, nextAssignment = null, excludePredicate = null) {
  const assignments = shop?.assignments || []
  if (!nextAssignment) {
    return sumCommissionRatio(assignments) <= 1 + 1e-9
  }
  return !exceedsCommissionRatioLimit(
    assignments,
    nextAssignment.commission_ratio ?? 0,
    excludePredicate
  )
}

function handleConfigMonthChange() {
  if (configMonth.value) loadConfigData()
}

async function handleCopyFromPrevMonth() {
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将使用上月配置覆盖 ${configMonth.value} 未锁定店铺的人员、提成比例和可分配净利润率，是否继续？`,
      '确认复制上月配置',
      { type: 'warning', confirmButtonText: '继续复制', cancelButtonText: '取消' }
    )
  } catch (_) {
    return
  }
  copyLoading.value = true
  try {
    const res = await api.copyHrEmployeeShopAssignmentsFromPrevMonth({ year_month: configMonth.value })
    const data = res?.data ?? res ?? {}
    const copied = data.copied ?? 0
    const updated = data.updated ?? 0
    ElMessage.success(`已复制上月配置到 ${configMonth.value}，新增 ${copied} 条，更新 ${updated} 项`)
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '复制失败')
  } finally {
    copyLoading.value = false
  }
}

async function handleSaveRow(row) {
  const shop = row._shop || row
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  if (!validateShopAssignmentRatio(shop)) {
    ElMessage.warning('该店铺该月份人员提成比例总和不能超过100%')
    return
  }
  shop.saving = true
  try {
    await saveShopRow(shop)
    ElMessage.success('已保存')
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    shop.saving = false
  }
}

/**
 * 保存单个店铺的归属（不刷新页面）。
 *
 * 匹配键只有 employee_code：同一个人在同一店就是同一行。
 * 批量保存复用它，并行提交、逐行汇总，失败不中断其余行。
 */
async function saveShopRow(shop) {
  if (!validateShopAssignmentRatio(shop)) {
    throw new Error('该店铺该月份人员提成比例总和不能超过100%')
  }
  const targetAssignments = (shop.assignments || []).map((p) => ({
    id: p.id,
    employee_code: p.employee_code,
    commission_ratio: p.commission_ratio ?? 0
  }))
  const assRes = await api.getHrEmployeeShopAssignments({ year_month: configMonth.value, platform_code: shop.platform_code, shop_id: shop.shop_id, page: 1, page_size: 100 })
  const assData = assRes?.data ?? assRes ?? {}
  const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])) || []
  for (const a of items) {
    const found = targetAssignments.find((t) => t.employee_code === a.employee_code)
    if (found) {
      if (Math.abs((a.commission_ratio ?? 0) - (found.commission_ratio ?? 0)) > 0.001) {
        await api.updateHrEmployeeShopAssignment(a.id, {
          commission_ratio: found.commission_ratio
        })
      }
    } else {
      await api.deleteHrEmployeeShopAssignment(a.id)
    }
  }
  for (const p of targetAssignments) {
    const exists = items.find((a) => a.employee_code === p.employee_code)
    if (!exists) {
      await api.createHrEmployeeShopAssignment({
        year_month: configMonth.value,
        employee_code: p.employee_code,
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        commission_ratio: p.commission_ratio
      })
    }
  }
  // 保存可分配利润率
  const rate = Number(shop.allocatable_profit_rate)
  if (!Number.isNaN(rate) && rate >= 0 && rate <= 1) {
    await api.putHrShopCommissionConfig(shop.platform_code, shop.shop_id, {
      year_month: configMonth.value,
      allocatable_profit_rate: rate
    })
  }
}

async function handleDeleteRow(row) {
  const shop = row._shop || row
  if (!configMonth.value) {
    ElMessage.warning('请先选择配置月份')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除 ${shop.shop_name || shop.shop_id} 的归属配置？删除后可重新编辑。`, '确认删除', { type: 'warning' })
    const assRes = await api.getHrEmployeeShopAssignments({ year_month: configMonth.value, platform_code: shop.platform_code, shop_id: shop.shop_id, page: 1, page_size: 100 })
    const assData = assRes?.data ?? assRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])) || []
    for (const a of items) await api.deleteHrEmployeeShopAssignment(a.id)
    shop.assignments = []
    shop.allocatable_profit_rate = 0
    await api.putHrShopCommissionConfig(shop.platform_code, shop.shop_id, {
      year_month: configMonth.value,
      allocatable_profit_rate: 0
    })
    ElMessage.success('已删除，可重新编辑')
    await loadConfigData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

/**
 * 批量保存：并行提交所有已配置的店铺，逐行汇总结果。
 * 失败不中断其余行（用 Promise.allSettled 而不是串行 for + await）。
 */
async function handleBatchSave() {
  if (!configMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }
  const toSave = shopRows.value.filter((r) => hasConfig(r))
  if (toSave.length === 0) {
    ElMessage.warning('没有需要保存的店铺')
    return
  }
  batchSaving.value = true
  try {
    const results = await Promise.allSettled(toSave.map((shop) => saveShopRow(shop)))
    const failed = []
    let succeeded = 0
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        succeeded += 1
        return
      }
      failed.push({
        target: {
          shop_name: toSave[index]?.shop_name,
          shop_id: toSave[index]?.shop_id
        },
        reason: result.reason?.response?.data?.detail || result.reason?.detail || result.reason?.message || String(result.reason)
      })
    })
    if (failed.length === 0) {
      ElMessage.success(`批量保存完成：成功 ${succeeded} 行 / 失败 0 行`)
    } else {
      ElMessage.warning(`批量保存完成：成功 ${succeeded} 行 / 失败 ${failed.length} 行`)
      showBatchFailureList('批量保存', failed)
    }
    await loadConfigData()
  } finally {
    batchSaving.value = false
  }
}

// 表格多选：只有每家店的第一行可以勾选，勾选结果按店铺去重。
function isShopFirstRow(row) {
  return Boolean(row?._isFirst)
}

function handleSelectionChange(rows) {
  selectedShops.value = (rows || [])
    .filter((row) => row?._isFirst && row?._shop)
    .map((row) => row._shop)
}

function clearShopSelection() {
  selectedShops.value = []
  configTableRef.value?.clearSelection()
}

function shopKeyOf(shop) {
  return `${shop?.platform_code ?? ''}|${shop?.shop_id ?? ''}`
}

// 选中店铺里已配置的人员行（批量改比例的作用对象）。
const batchTargetRows = computed(() => {
  const rows = []
  for (const shop of selectedShops.value) {
    for (const assignment of shop.assignments || []) {
      rows.push({
        ...assignment,
        platform_code: shop.platform_code,
        shop_id: shop.shop_id
      })
    }
  }
  return rows
})

// 本地刚加、还没保存的人员行：批量端点只改已落库的归属，这些行不参与。
const batchUnsavedRows = computed(() =>
  batchTargetRows.value.filter((row) => row.id === null || row.id === undefined)
)

// 超限预检：口径与页面的 validateShopAssignmentRatio 一致（按店铺合计 ≤ 100%）。
const batchAttachOverflowShops = computed(() => {
  if (!batchAttachVisible.value) return []
  const ratio = batchForm.value.commission_ratio ?? 0
  return selectedShops.value.filter((shop) => !validateShopAssignmentRatio(shop, { commission_ratio: ratio }))
})

const batchRatioOverflowShops = computed(() => {
  if (!batchRatioVisible.value) return []
  const ratio = batchForm.value.commission_ratio ?? 0
  return selectedShops.value.filter((shop) => {
    const rows = shop.assignments || []
    if (rows.length === 0) return false
    const excluded = new Set(rows)
    return !validateShopAssignmentRatio(
      shop,
      { commission_ratio: ratio * rows.length },
      (assignment) => excluded.has(assignment)
    )
  })
})

// 从后端批量端点的响应里取出逐项结果。
function extractBatchResult(response) {
  const payload = response?.data ?? response ?? {}
  const inner = payload?.data ?? payload
  return {
    succeeded: Array.isArray(inner?.succeeded) ? inner.succeeded : [],
    failed: Array.isArray(inner?.failed) ? inner.failed : [],
    summary: inner?.summary ?? null
  }
}

function describeBatchTarget(target) {
  if (target === null || target === undefined) return '未知对象'
  if (typeof target === 'string') return target
  if (typeof target !== 'object') return String(target)
  const parts = []
  const shopLabel = target.shop_name || target.shop_id
  if (shopLabel) parts.push(String(shopLabel))
  const employeeLabel = target.employee_name || target.employee_code
  if (employeeLabel) parts.push(String(employeeLabel))
  if (parts.length === 0) {
    try {
      return JSON.stringify(target)
    } catch (_) {
      return '未知对象'
    }
  }
  return parts.join(' / ')
}

function showBatchFailureList(label, failed) {
  const lines = (failed || []).map((item, index) => {
    const reason = item?.reason || '未知原因'
    return `${index + 1}. ${describeBatchTarget(item?.target)} —— ${reason}`
  })
  if (lines.length === 0) return
  ElMessageBox.alert(lines.join('\n'), `${label}失败清单`, {
    type: 'warning',
    confirmButtonText: '知道了',
    customClass: 'batch-failure-summary'
  }).catch(() => {})
}

// 批量结果的统一播报：成功 N 家 / 跳过 M 家，失败原因逐条列出。
function reportBatchResult(label, result) {
  const succeeded = result.succeeded.length
  const failed = result.failed.length
  if (failed === 0) {
    ElMessage.success(`${label}成功 ${succeeded} 家 / 跳过 0 家`)
    return
  }
  ElMessage.warning(`${label}成功 ${succeeded} 家 / 跳过 ${failed} 家`)
  showBatchFailureList(label, result.failed)
}

function openBatchAttachDialog() {
  if (selectedShops.value.length === 0) {
    ElMessage.warning('请先勾选店铺')
    return
  }
  batchForm.value = { employee_code: '', commission_ratio: 0.05 }
  batchAttachVisible.value = true
}

async function submitBatchAttach() {
  const employeeCode = String(batchForm.value.employee_code || '').trim()
  if (!employeeCode) {
    ElMessage.warning('请选择员工')
    return
  }
  const items = buildBatchCreateItems(
    selectedShops.value,
    employeeCode,
    batchForm.value.commission_ratio ?? 0
  )
  if (items.length === 0) {
    ElMessage.warning('没有可提交的店铺')
    return
  }
  batchSubmitting.value = true
  try {
    const res = await api.batchHrEmployeeShopAssignments({
      year_month: configMonth.value,
      mode: 'create',
      items
    })
    reportBatchResult('批量挂靠', extractBatchResult(res))
    batchAttachVisible.value = false
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.detail || e?.message || '批量挂靠失败')
  } finally {
    batchSubmitting.value = false
  }
}

function openBatchRatioDialog() {
  if (selectedShops.value.length === 0) {
    ElMessage.warning('请先勾选店铺')
    return
  }
  if (batchTargetRows.value.length === 0) {
    ElMessage.warning('选中的店铺还没有配置人员，无法调整比例')
    return
  }
  batchForm.value = { employee_code: '', commission_ratio: 0.05 }
  batchRatioVisible.value = true
}

async function submitBatchRatio() {
  const rows = batchTargetRows.value
  if (rows.length === 0) {
    ElMessage.warning('没有可调整的人员归属')
    return
  }
  const { items, assignment_ids } = buildBatchUpdatePayload(
    rows,
    batchForm.value.commission_ratio ?? 0
  )
  if (items.length === 0) {
    ElMessage.warning('选中的归属都还没保存，请先保存后再批量调整比例')
    return
  }
  batchSubmitting.value = true
  try {
    const res = await api.batchHrEmployeeShopAssignments({
      year_month: configMonth.value,
      mode: 'update',
      items,
      assignment_ids
    })
    reportBatchResult('批量调整比例', extractBatchResult(res))
    batchRatioVisible.value = false
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.detail || e?.message || '批量调整比例失败')
  } finally {
    batchSubmitting.value = false
  }
}

async function handleBatchRemove() {
  if (selectedShops.value.length === 0) {
    ElMessage.warning('请先勾选店铺')
    return
  }
  const assignmentIds = collectAssignmentIds(selectedShops.value)
  if (assignmentIds.length === 0) {
    ElMessage.warning('选中的店铺还没有人员归属，无需移除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将移除已选 ${selectedShops.value.length} 家店铺下的全部人员归属（共 ${assignmentIds.length} 条），是否继续？`,
      '确认批量移除',
      { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' }
    )
  } catch (_) {
    return
  }
  batchSubmitting.value = true
  try {
    const res = await api.batchHrEmployeeShopAssignments({
      year_month: configMonth.value,
      mode: 'delete',
      items: [],
      assignment_ids: assignmentIds
    })
    reportBatchResult('批量移除', extractBatchResult(res))
    await loadConfigData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.detail || e?.message || '批量移除失败')
  } finally {
    batchSubmitting.value = false
  }
}

function removePersonLocal(shop, p) {
  shop.assignments = (shop.assignments || []).filter((x) => x.employee_code !== p.employee_code)
}

async function loadEmployees() {
  try {
    const res = await api.getHrEmployees({ page: 1, page_size: 500 })
    employees.value = Array.isArray(res) ? res : (res?.data ?? res ?? [])
  } catch (_) {
    employees.value = []
  }
}

async function loadShops() {
  try {
    const [targetShopsResult, shopDirectoryResult] = await Promise.allSettled([
      api.getTargetShops(),
      api.getShopDirectory({ enabled: true })
    ])
    if (targetShopsResult.status !== 'fulfilled') {
      throw targetShopsResult.reason
    }
    const shopDirectory = shopDirectoryResult.status === 'fulfilled' ? shopDirectoryResult.value : []
    shopAccountLookup = buildShopAccountLookup(Array.isArray(shopDirectory) ? shopDirectory : [])
    const data = targetShopsResult.value?.data ?? targetShopsResult.value
    const rows = Array.isArray(data) ? data : (data?.data ?? data ?? [])
    shops.value = rows.map((row) => decorateShopEntity(row, shopAccountLookup))
  } catch (_) {
    shops.value = []
  }
}

// 从后端结算预览响应里取出 employees 数组。
// 响应拦截器已经把 { success, data } 拆成 data，这里兼容两种形态。
function extractPreviewEmployees(response) {
  const payload = response?.data ?? response ?? {}
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.employees)) return payload.employees
  return []
}

// 员工 + 店铺 的预览索引键。
function previewShopKey(employeeCode, platformCode, shopId) {
  return `${employeeCode}|${String(platformCode || '').toLowerCase()}|${shopId}`
}

function toRateNumber(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

async function loadConfigData() {
  if (!configMonth.value) return
  configLoading.value = true
  // 重新加载 = 回到后端已保存的状态 ⇒ 之前的试算结果作废。
  estimateRows.value = new Map()
  try {
    const [assignmentsRes, shopsRes, statsRes, configRes, previewRes] = await Promise.all([
      api.getHrEmployeeShopAssignments({ year_month: configMonth.value, page: 1, page_size: 1000 }),
      api.getTargetShops(),
      api.getHrShopProfitStatistics({ month: configMonth.value }).catch(() => ({ data: [] })),
      api.getHrShopCommissionConfig({ year_month: configMonth.value }).catch(() => ({ data: [] })),
      api.getHrCommissionSettlementPreview({ year_month: configMonth.value }).catch(() => ({ data: [] }))
    ])
    const shopData = shopsRes?.data ?? shopsRes ?? []
    const shopList = (Array.isArray(shopData) ? shopData : (shopData?.data ?? shopData ?? [])).map((row) => decorateShopEntity(row, shopAccountLookup))
    const assData = assignmentsRes?.data ?? assignmentsRes ?? {}
    const items = (assData?.items ?? (Array.isArray(assData) ? assData : [])).filter(Boolean)
    const statsData = statsRes?.data ?? statsRes ?? []
    const statsList = Array.isArray(statsData) ? statsData : (statsData?.data ?? statsData ?? [])
    const configData = configRes?.data ?? configRes ?? []
    const configList = Array.isArray(configData) ? configData : (configData?.data ?? configData ?? [])
    const previewEmployees = extractPreviewEmployees(previewRes)
    settlementPreviewEmployees.value = previewEmployees

    const byShop = {}
    for (const s of shopList) {
      const key = `${(s.platform_code || '').toLowerCase()}|${s.shop_id}`
      byShop[key] = {
        platform_code: (s.platform_code || '').toLowerCase(),
        shop_id: s.shop_id,
        shop_name: s.shop_name || s.shop_id,
        secondary_name: s.secondary_name || '',
        canonical_shop_name: s.canonical_shop_name || '',
        allocatable_profit_rate: 0,
        // 「有没有配可分配率」和「配成 0」业务含义不同，必须分开存。
        is_allocatable_rate_configured: false,
        assignments: [],
        saving: false,
        monthly_sales: 0,
        monthly_profit: 0,
        profit_basis_amount: 0,
        allocatable_profit_amount: null,
        other_a_class_cost_amount: 0,
        pre_commission_labor_cost_amount: 0,
        a_class_cost_amount: 0,
        // 口径 / 成本状态一律来自后端，前端不补默认值。
        basis_version: '',
        cost_status: '',
        achievement_rate: null
      }
    }
    for (const st of statsList) {
      const key = `${(st.platform_code || '').toLowerCase()}|${st.shop_id != null ? String(st.shop_id) : ''}`
      if (byShop[key]) {
        byShop[key].monthly_sales = st.monthly_sales ?? 0
        byShop[key].monthly_profit = st.monthly_profit ?? 0
        byShop[key].profit_basis_amount = st.profit_basis_amount ?? 0
        byShop[key].allocatable_profit_amount = st.allocatable_profit_amount ?? null
        byShop[key].other_a_class_cost_amount = st.other_a_class_cost_amount ?? 0
        byShop[key].pre_commission_labor_cost_amount = st.pre_commission_labor_cost_amount ?? 0
        byShop[key].a_class_cost_amount = st.a_class_cost_amount ?? 0
        byShop[key].basis_version = st.basis_version ?? ''
        byShop[key].cost_status = st.cost_status ?? ''
        byShop[key].achievement_rate = st.achievement_rate
        if (st.is_allocatable_rate_configured !== undefined && st.is_allocatable_rate_configured !== null) {
          byShop[key].is_allocatable_rate_configured = Boolean(st.is_allocatable_rate_configured)
          byShop[key].allocatable_profit_rate = toRateNumber(st.allocatable_profit_rate)
        }
      }
    }
    for (const c of configList) {
      const key = `${(c.platform_code || '').toLowerCase()}|${c.shop_id}`
      if (byShop[key]) {
        byShop[key].allocatable_profit_rate = toRateNumber(c.allocatable_profit_rate)
        byShop[key].is_allocatable_rate_configured =
          c.is_allocatable_rate_configured === undefined || c.is_allocatable_rate_configured === null
            ? true
            : Boolean(c.is_allocatable_rate_configured)
      }
    }
    // 记住加载时的原始值：用户改了之后用来判断「还没保存」，试算只改展示不改原始值。
    for (const shop of Object.values(byShop)) {
      shop._backend_allocatable_profit_rate = shop.allocatable_profit_rate
    }
    // 结算预览索引：谁在哪家店、后端算出来的提成 / 系数 / 零提成原因。
    const previewShopIndex = new Map()
    for (const employee of previewEmployees) {
      for (const previewShop of employee?.shops || []) {
        previewShopIndex.set(
          previewShopKey(employee.employee_code, previewShop.platform_code, previewShop.shop_id),
          { employee, shop: previewShop }
        )
      }
    }
    for (const a of items) {
      const key = `${(a.platform_code || '').toLowerCase()}|${a.shop_id}`
      if (!byShop[key]) {
        byShop[key] = {
          platform_code: (a.platform_code || '').toLowerCase(),
          shop_id: a.shop_id,
          ...decorateShopEntity(a, shopAccountLookup),
          allocatable_profit_rate: 0,
          is_allocatable_rate_configured: false,
          assignments: [],
          saving: false,
          monthly_sales: 0,
          monthly_profit: 0,
          profit_basis_amount: 0,
          allocatable_profit_amount: null,
          other_a_class_cost_amount: 0,
          pre_commission_labor_cost_amount: 0,
          a_class_cost_amount: 0,
          basis_version: '',
          cost_status: '',
          achievement_rate: null
        }
        byShop[key]._backend_allocatable_profit_rate = 0
      }
      const p = {
        id: a.id,
        employee_code: a.employee_code,
        employee_name: a.employee_name,
        commission_ratio: a.commission_ratio ?? 0
      }
      const matched = previewShopIndex.get(previewShopKey(a.employee_code, a.platform_code, a.shop_id))
      p._preview = matched?.shop || null
      p._employee_status = matched?.employee?.calculation_status ?? ''
      // 后端下发的原始提成比：用来判断用户是否改了还没保存。
      p._backend_commission_ratio = matched?.shop?.commission_ratio ?? p.commission_ratio
      byShop[key].assignments.push(p)
    }
    // 店铺级可分配利润：优先用结算预览里后端算好的值。
    for (const [key, entry] of previewShopIndex.entries()) {
      const shopKey = key.split('|').slice(1).join('|')
      const shop = byShop[shopKey]
      if (shop && shop.allocatable_profit_amount == null) {
        shop.allocatable_profit_amount = entry.shop?.allocatable_profit_amount ?? null
      }
    }
    shopRows.value = Object.values(byShop).sort((a, b) => (a.platform_code + a.shop_id).localeCompare(b.platform_code + b.shop_id))
    // 重新加载后行对象已换新，旧的勾选作废。
    clearShopSelection()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    shopRows.value = []
    settlementPreviewEmployees.value = []
  } finally {
    configLoading.value = false
  }
}

async function loadStatsData() {
  if (!statsMonth.value) return
  statsLoading.value = true
  try {
    const res = await api.getHrShopProfitStatistics({ month: statsMonth.value })
    const data = res?.data ?? res ?? []
    const items = Array.isArray(data) ? data : (data?.data ?? data ?? [])
    // 店铺维度的「实发口径预计提成」由后端直接给出
    // （settlement_commission_amount：按结算预览逐人汇总到店）。
    // 前端不再自己拼口径，也不再自己累加成另一套数字。
    statsRows.value = items.map((row) =>
      decorateShopEntity(normalizeProfitBasisFields(row), shopAccountLookup)
    )
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    statsRows.value = []
  } finally {
    statsLoading.value = false
  }
}

async function loadAnnualData() {
  const year = annualYear.value ? Number(annualYear.value) : new Date().getFullYear()
  if (!year) return
  annualLoading.value = true
  try {
    const res = await api.getHrAnnualProfitStatistics({ year })
    const raw = res?.data ?? res ?? {}
    const data = raw?.data ?? raw ?? {}
    annualData.value = {
      year: data.year ?? year,
      by_employee: data.by_employee ?? [],
      by_shop: data.by_shop ?? []
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载年度统计失败')
    annualData.value = { year: null, by_employee: [], by_shop: [] }
  } finally {
    annualLoading.value = false
  }
}

function openAddForShop(shop) {
  resetForm()
  isEdit.value = false
  addForShopRow.value = shop
  form.value.platform_code = shop.platform_code
  form.value.shop_id = shop.shop_id
  form.value.commission_ratio = 0.05
  dialogVisible.value = true
}

async function submitForm() {
  if (!form.value.employee_code) {
    ElMessage.warning('请选择员工')
    return
  }
  const shop = addForShopRow.value
  if (shop) {
    const emp = employeesActive.value.find((e) => e.employee_code === form.value.employee_code)
    const p = {
      employee_code: form.value.employee_code,
      employee_name: emp?.name,
      commission_ratio: form.value.commission_ratio ?? 0
    }
    if ((shop.assignments || []).some((x) => x.employee_code === p.employee_code)) {
      ElMessage.warning('该人员已添加')
      return
    }
    if (!validateShopAssignmentRatio(shop, p)) {
      ElMessage.warning('该店铺该月份人员提成比例总和不能超过100%')
      return
    }
    shop.assignments = [...(shop.assignments || []), p]
    ElMessage.success('已添加，请点击保存提交')
    dialogVisible.value = false
  } else {
    submitLoading.value = true
    try {
      await api.createHrEmployeeShopAssignment({
        year_month: configMonth.value,
        employee_code: form.value.employee_code,
        platform_code: form.value.platform_code,
        shop_id: form.value.shop_id,
        commission_ratio: form.value.commission_ratio ?? 0
      })
      ElMessage.success('已新增')
      dialogVisible.value = false
      await loadConfigData()
      if (activeTab.value === 'stats') await loadStatsData()
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
    } finally {
      submitLoading.value = false
    }
  }
}

watch(activeTab, (tab) => {
  if (tab === 'config') loadConfigData()
  else if (tab === 'stats') loadStatsData()
  else if (tab === 'annual') loadAnnualData()
})

onMounted(async () => {
  await Promise.all([loadEmployees(), loadShops()])
  await loadConfigData()
})
</script>

<style scoped>
/*
 * 页面容器：内边距由 .erp-page-container 提供（20px）。
 * 这里**不要**再叠一层 padding —— 原来 .shop-assignment-page 的 20px 与工具类的
 * 20px 叠加成 40px，是页面四周留白偏大的直接原因。
 */

/* 操作栏：间距统一由 gap 控制，不再靠逐个按钮的 margin-left */
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.assignment-tabs {
  margin-bottom: 12px;
}

.person-list {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
}
.commission-summary-strip {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
}
.commission-summary-title {
  flex: 0 0 auto;
  color: #606266;
  font-weight: 600;
  line-height: 24px;
}
.commission-summary-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.commission-summary-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  color: #303133;
}
.commission-summary-name {
  font-weight: 600;
}
.commission-summary-position,
.commission-summary-shops {
  color: #909399;
  font-size: 12px;
}
.commission-summary-amount {
  color: #067647;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.allocatable-rate-wrap {
  display: inline-flex;
  align-items: center;
  width: 100%;
}
.allocatable-rate-wrap .allocatable-rate-input { flex: 1; min-width: 0; }
.allocatable-rate-wrap .allocatable-rate-suffix { margin-left: 4px; color: #909399; }
/*
 * 密度改造（2026-11-28）：表格行内的「可分配净利润率」输入 + 状态标签同行，
 * 输入框可压缩、标签不可压缩（状态必须可见）。
 */
.allocatable-rate-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  max-width: 100%;
}
.allocatable-rate-cell .allocatable-rate-wrap {
  width: auto;
  flex: 1 1 auto;
  min-width: 56px;
}
.allocatable-rate-cell .rate-status-cell {
  flex: 0 0 auto;
  margin-top: 0;
}
.person-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  white-space: nowrap;
}
/* 「+ 添加人员」入口放在固定左侧的店铺列，缩进对齐店铺名 */
.add-person-button {
  margin-left: 4px;
  padding: 0;
}
.person-cell-name {
  overflow: hidden;
  text-overflow: ellipsis;
}
.person-cell-tag,
.person-cell-position {
  flex: 0 0 auto;
}
.shop-display-cell {
  line-height: 1.4;
}
/* 店铺名与「+ 添加人员」同行：名字过长时省略号截断，不把行撑成三行 */
.shop-display-head {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.shop-display-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shop-display-secondary {
  font-size: 12px;
  color: #909399;
}
.v2-cost-breakdown {
  color: #606266;
  font-size: 12px;
  line-height: 1.55;
}
.v2-cost-breakdown .el-tag {
  margin-top: 3px;
  margin-left: 4px;
}

/*
 * 成本明细摘要（2026-11-28 密度改造）
 * -----------------------------------
 * 原来这一列是「3 行金额 + 2 个标签」，行高被撑到 ~110px。
 * 现在：单元格内只留**一行**摘要（三个金额用 / 分隔），完整明细进 tooltip；
 * 「缺少人力成本分摊」的红色警示在摘要行里仍可见（缩成「缺分摊」），
 * tooltip 里给出完整文案。
 */
.cost-summary-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  max-width: 100%;
}

.cost-summary-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.cost-summary-alert {
  flex: 0 0 auto;
}

.cost-tooltip {
  white-space: nowrap;
  line-height: 1.7;
  font-size: 12px;
}

.cost-tooltip-tags {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}
.dialog-shop-secondary {
  margin-top: 4px;
}
.fallback-text {
  color: #909399;
}
.status-cell {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  justify-content: center;
}
.rate-status-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 4px;
}
.commission-amount {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.batch-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #f5f7fa;
}
.batch-toolbar-count {
  color: #606266;
  font-weight: 600;
}
.batch-shop-preview,
.batch-overflow-list {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.55;
  max-height: 120px;
  overflow-y: auto;
}
</style>

<!-- 批量失败清单需要换行展示（消息框挂在 body 上，不能用 scoped 样式）。 -->
<style>
.batch-failure-summary .el-message-box__message {
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
  max-height: 50vh;
  overflow-y: auto;
}
</style>
