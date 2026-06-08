<template>
  <div class="performance-management erp-page-container">
    <PageHeader
      :title="pageTitle"
      :subtitle="pageSubtitle"
      family="admin"
    />
    
    <!-- 操作栏：月份、维度切换与功能按钮 -->
    <div class="action-bar">
      <el-date-picker
        v-model="filters.period"
        type="month"
        format="YYYY-MM"
        value-format="YYYY-MM"
        placeholder="选择月份"
        size="default"
        style="width: 180px;"
        @change="handlePeriodChange"
      />
      <el-radio-group v-if="showGroupToggle" v-model="filters.groupBy" size="default" @change="handleGroupByChange">
        <el-radio-button value="shop">按店铺</el-radio-button>
        <el-radio-button value="person">按人员</el-radio-button>
      </el-radio-group>
      <el-button :icon="Refresh" @click="handleRefreshAll">刷新</el-button>
      <el-button
        type="warning"
        :loading="calculating"
        @click="handleRecalculate"
        v-if="hasPermission('performance:config')"
      >
        重新计算
      </el-button>
      <el-button type="primary" :icon="Setting" @click="handleConfig" v-if="hasPermission('performance:config')">
        配置公式
      </el-button>
      <el-button :icon="Download" @click="handleExport" v-if="hasPermission('performance:export')">导出报表</el-button>
      <el-select v-if="filters.groupBy === 'shop'" v-model="poolFilter" size="default" style="width: 120px;" @change="() => {}">
        <el-option label="全部池" value="all" />
        <el-option label="正式池" value="official" />
        <el-option label="观察池" value="observation" />
      </el-select>
      <el-select v-if="filters.groupBy === 'shop'" v-model="alertFilter" size="default" style="width: 130px;" @change="() => {}">
        <el-option label="全部预警" value="all" />
        <el-option label="无预警" value="none" />
        <el-option label="黄牌" value="yellow" />
        <el-option label="红牌" value="red" />
        <el-option label="淘汰评估" value="elimination" />
      </el-select>
      <el-select v-if="filters.groupBy === 'shop'" v-model="filters.platform" placeholder="选择平台" clearable size="default" style="width: 140px; margin-left: auto;" @change="loadPerformanceList">
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
      <el-input
        v-if="filters.groupBy === 'shop'"
        v-model="shopKeyword"
        clearable
        placeholder="按别名 / 标准名 / 店铺ID筛选"
        size="default"
        style="width: 220px;"
      />
    </div>

    <el-card shadow="never" class="policy-card">
      <template #header>
        <div class="card-header">
          <span>口径说明</span>
        </div>
      </template>
      <div class="policy-grid">
        <div class="policy-item">
          <div class="policy-label">赛马池</div>
          <div class="policy-text">正式池参与公司总榜赛马并生成系数；观察池仅展示绩效，不参与正式奖惩。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">预警规则</div>
          <div class="policy-text">绩效分低于 70 为黄牌，低于 60 为红牌；连续红牌达到条件时升级为淘汰评估。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">{{ filters.groupBy === 'person' ? '人员维度' : '店铺维度' }}</div>
          <div class="policy-text">{{ currentGroupPolicyText }}</div>
        </div>
      </div>
    </el-card>
    
    <!-- 绩效表格 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>绩效管理视图</span>
          <div style="font-size: 12px; color: #909399;">
            绩效构成：{{ formulaText }}
          </div>
        </div>
      </template>
      
      <el-table :data="filteredPerformanceData" stripe v-loading="performanceList.loading" class="erp-table" border>
        <el-table-column :prop="filters.groupBy === 'person' ? 'employee_name' : 'shop_name'" :label="filters.groupBy === 'person' ? '人员' : '店铺'" width="200" fixed="left" show-overflow-tooltip>
          <template #default="{ row }">
            <template v-if="filters.groupBy === 'person'">{{ row.employee_name || row.employee_code || '—' }}</template>
            <div v-else class="shop-display-cell">
              <div>{{ row.shop_name || row.shop_id || '—' }}</div>
              <div v-if="row.secondary_name" class="shop-display-secondary">{{ row.secondary_name }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额目标" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成" width="110" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额达成率" width="120" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="销售额得分" width="100" align="right">
          <template #default="{ row }">{{ row.sales_score != null ? Number(row.sales_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利目标" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_target) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.profit_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利达成率" width="110" align="right">
          <template #default="{ row }">{{ formatPercent(row.profit_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="毛利得分" width="90" align="right">
          <template #default="{ row }">{{ row.profit_score != null ? Number(row.profit_score).toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" prop="operation_score" label="店铺运营得分" width="120" align="right" sortable>
          <template #default="{ row }">{{ row.operation_score != null ? Number(row.operation_score).toFixed(1) : '—' }}</template>
        </el-table-column>

        <el-table-column v-if="filters.groupBy === 'person'" label="实际销售额" width="120" align="right">
          <template #default="{ row }">{{ formatCell(row.sales_achieved) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="店铺汇总达成率" width="140" align="right">
          <template #default="{ row }">{{ formatPercent(row.sales_rate) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'person'" label="个人运营加减分(人工)" width="160" align="right">
          <template #default="{ row }">
            <el-tag v-if="row.personal_adjustment_total != null" :type="Number(row.personal_adjustment_total || 0) >= 0 ? 'success' : 'danger'" size="small">
              {{ Number(row.personal_adjustment_total || 0) > 0 ? '+' : '' }}{{ Number(row.personal_adjustment_total || 0).toFixed(1) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>

        <el-table-column prop="total_score" :label="filters.groupBy === 'person' ? '个人绩效总分' : '总分'" width="120" align="right" sortable>
          <template #default="{ row }">
            <el-tag v-if="row.total_score != null" :type="row.total_score >= 90 ? 'success' : row.total_score >= 80 ? 'warning' : 'danger'" size="small">{{ Number(row.total_score).toFixed(1) }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="80" align="center" sortable>
          <template #default="{ row }">{{ row.rank != null ? `第${row.rank}名` : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" prop="performance_coefficient" label="绩效系数" width="100" align="right" sortable>
          <template #default="{ row }">{{ row.performance_coefficient != null ? Number(row.performance_coefficient).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="赛马池" width="100" align="center">
          <template #default="{ row }">{{ rankingPoolText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="预警" width="120" align="center">
          <template #default="{ row }">{{ performanceAlertText(row) }}</template>
        </el-table-column>
        <el-table-column v-if="filters.groupBy === 'shop'" label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleViewDetail(row)" v-if="row.platform_code && row.shop_id">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div v-if="performanceList.data.length === 0 && !performanceList.loading" style="padding: 40px; text-align: center; color: #909399;">
        <template v-if="loadError">查询失败，请稍后重试或联系管理员。</template>
        <template v-else>
          <div style="margin-bottom: 12px;">暂无绩效数据，请选择月份并确认已执行绩效计算。</div>
          <el-button type="warning" :loading="calculating" @click="handleRecalculate" v-if="hasPermission('performance:config')">
            重新计算当月绩效
          </el-button>
        </template>
      </div>
      <el-pagination
        v-model:current-page="performanceList.page"
        v-model:page-size="performanceList.pageSize"
        :total="performanceList.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadPerformanceList"
        @current-change="loadPerformanceList"
      />
    </el-card>
    
    <!-- 绩效详情 -->


    <el-card v-if="hasPermission('performance:config') && filters.groupBy === 'person'" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span>个人绩效输入项</span>
          <div class="card-actions">
            <el-button size="small" @click="loadInputList">刷新</el-button>
            <el-button size="small" @click="openApplyTemplate">套用默认模板</el-button>
            <el-button size="small" type="primary" @click="openCreateInput">新增输入项</el-button>
          </div>
        </div>
      </template>
      <el-table :data="inputList.data" stripe v-loading="inputList.loading" class="erp-table" border>
        <el-table-column prop="employee_name" label="人员" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.employee_name || row.employee_code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="year_month" label="月份" width="100" />
        <el-table-column prop="metric_name" label="指标名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.metric_name || row.metric_code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="metric_direction" label="方向" width="90" align="center">
          <template #default="{ row }">{{ row.metric_direction === 'down' || row.metric_direction === 'lower_better' ? '越低越好' : '越高越好' }}</template>
        </el-table-column>
        <el-table-column prop="target_value" label="目标值" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.target_value) }}</template>
        </el-table-column>
        <el-table-column prop="achieved_value" label="实际值" width="100" align="right">
          <template #default="{ row }">{{ formatCell(row.achieved_value) }}</template>
        </el-table-column>
        <el-table-column prop="max_score" label="满分" width="90" align="right">
          <template #default="{ row }">{{ formatCell(row.max_score) }}</template>
        </el-table-column>
        <el-table-column label="人工评分" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.manual_score_enabled" type="warning" size="small">
              {{ row.manual_score_value != null ? Number(row.manual_score_value).toFixed(1) : '启用' }}
            </el-tag>
            <span v-else>自动</span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="140" show-overflow-tooltip />
        <el-table-column prop="reason" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditInput(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDeleteInput(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="inputList.data.length === 0 && !inputList.loading" class="empty-state small">
        当前月份暂无个人绩效输入项。
      </div>
    </el-card>

    <el-card v-if="hasPermission('performance:config') && filters.groupBy === 'person'" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span>个人绩效调整项</span>
          <div class="card-actions">
            <el-button size="small" @click="loadAdjustmentList">刷新</el-button>
            <el-button size="small" type="primary" @click="openCreateAdjustment">新增调整项</el-button>
          </div>
        </div>
      </template>
      <el-table :data="adjustmentList.data" stripe v-loading="adjustmentList.loading" class="erp-table" border>
        <el-table-column prop="employee_name" label="人员" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.employee_name || row.employee_code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="year_month" label="月份" width="100" />
        <el-table-column prop="adjustment_type" label="调整类型" width="140" />
        <el-table-column prop="score_delta" label="分值变化" width="100" align="right">
          <template #default="{ row }">
            <el-tag :type="Number(row.score_delta || 0) >= 0 ? 'success' : 'danger'" size="small">
              {{ Number(row.score_delta || 0) > 0 ? '+' : '' }}{{ Number(row.score_delta || 0).toFixed(1) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="140" show-overflow-tooltip />
        <el-table-column prop="reason" label="原因/备注" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditAdjustment(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDeleteAdjustment(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="adjustmentList.data.length === 0 && !adjustmentList.loading" class="empty-state small">
        当前月份暂无个人绩效调整项。
      </div>
    </el-card>

    <el-dialog
      v-model="detailVisible"
      title="绩效详情"
      width="900px"
    >
      <div v-if="performanceDetail.data" v-loading="performanceDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="店铺名称" :span="2">
            <div class="shop-display-cell">
              <div>{{ performanceDetail.data.shop_name }}</div>
              <div v-if="performanceDetail.data.secondary_name" class="shop-display-secondary">{{ performanceDetail.data.secondary_name }}</div>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="考核周期">{{ performanceDetail.data.period }}</el-descriptions-item>
          <el-descriptions-item label="总分">
            <el-tag :type="performanceDetail.data.total_score != null ? (performanceDetail.data.total_score >= 90 ? 'success' : performanceDetail.data.total_score >= 80 ? 'warning' : 'danger') : 'info'" size="large">
              {{ performanceDetail.data.total_score != null ? performanceDetail.data.total_score.toFixed(1) : '未完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="排名">
            <el-tag :type="performanceDetail.data.rank === 1 ? 'success' : performanceDetail.data.rank === 2 ? 'warning' : performanceDetail.data.rank === 3 ? 'info' : 'info'" size="small">
              {{ performanceDetail.data.rank != null ? `第${performanceDetail.data.rank}名` : '未参与正式赛马' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="绩效系数">
            <el-tag :type="performanceDetail.data.performance_coefficient != null ? (performanceDetail.data.performance_coefficient >= 1.2 ? 'success' : performanceDetail.data.performance_coefficient >= 1.0 ? 'warning' : 'danger') : 'info'" size="small">
              {{ performanceDetail.data.performance_coefficient != null ? performanceDetail.data.performance_coefficient.toFixed(2) : '未完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="赛马池">{{ rankingPoolText(performanceDetail.data) }}</el-descriptions-item>
          <el-descriptions-item label="预警">{{ performanceAlertText(performanceDetail.data) }}</el-descriptions-item>
        </el-descriptions>
        
        <el-card style="margin-top: 20px;">
          <template #header>
            <span>得分详情</span>
          </template>
          <el-card
            v-for="card in detailMetricCards"
            :key="card.key"
            shadow="never"
            style="margin-bottom: 15px;"
          >
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <span style="font-weight: bold;">{{ card.label }}（满分 {{ card.maxScore }}）</span>
              <el-tag :type="metricTagType(card.metric, card.successThreshold, card.warningThreshold)" size="small">
                {{ metricScoreText(card.metric) }}
              </el-tag>
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="状态">{{ isMetricCalculated(card.metric) ? '已计算' : '未就绪' }}</el-descriptions-item>
              <el-descriptions-item label="数据来源">{{ card.metric?.source || '—' }}</el-descriptions-item>
              <el-descriptions-item label="目标">{{ metricValueText(card.metric, 'target', card.targetType) }}</el-descriptions-item>
              <el-descriptions-item label="达成">{{ metricValueText(card.metric, 'achieved', card.achievedType) }}</el-descriptions-item>
              <el-descriptions-item label="达成率">{{ metricValueText(card.metric, 'rate', 'percent') }}</el-descriptions-item>
              <el-descriptions-item label="说明">{{ metricMessageText(card.metric) }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-card>
      </div>
    </el-dialog>
    
    <!-- 店铺绩效配置 -->
    <el-dialog
      v-model="configVisible"
      title="店铺绩效配置"
      width="600px"
      @close="handleConfigClose"
    >
      <el-form
        ref="configFormRef"
        :model="configForm"
        :rules="configRules"
        label-width="150px"
      >
        <el-divider content-position="left">正式公式满分配置（销售额 + 毛利 + 店铺运营）</el-divider>
        <el-form-item label="销售额满分" prop="sales_max_score">
          <el-input-number v-model="configForm.sales_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="毛利满分" prop="profit_max_score">
          <el-input-number v-model="configForm.profit_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="运营满分" prop="operation_max_score">
          <el-input-number v-model="configForm.operation_max_score" :min="0" :max="100" :precision="0" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="兼容字段">
          <el-tag type="info" size="large">重点产品与旧权重字段保留兼容，不参与当前公式</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfigSubmit" :loading="configSubmitting">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="templateDialogVisible"
      title="套用个人绩效模板"
      width="520px"
    >
      <el-form :model="templateForm" label-width="110px">
        <el-form-item label="月份"><el-input v-model="templateForm.year_month" disabled /></el-form-item>
        <el-form-item label="人员" required>
          <el-select v-model="templateForm.employee_code" filterable placeholder="选择人员" style="width: 100%;" @change="loadTemplateOptions">
            <el-option v-for="employee in adjustmentEmployeeOptions" :key="employee.employee_code" :label="`${employee.name} (${employee.employee_code})`" :value="employee.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="模板">
          <el-select v-model="templateForm.template_code" placeholder="选择模板" style="width: 100%;">
            <el-option v-for="item in templateOptions" :key="item.template_code" :label="`${item.template_name}${item.recommended ? '（推荐）' : ''}`" :value="item.template_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="覆盖已有项">
          <el-switch v-model="templateForm.overwrite" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="selectedTemplateSummary"
        :title="selectedTemplateSummary"
        type="info"
        :closable="false"
      />
      <template #footer>
        <el-button @click="templateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="templateSubmitting" @click="handleApplyTemplate">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="inputDialogVisible"
      :title="inputMode === 'create' ? '新增个人绩效输入项' : '编辑个人绩效输入项'"
      width="560px"
    >
      <el-form :model="inputForm" label-width="110px">
        <el-form-item label="月份"><el-input v-model="inputForm.year_month" disabled /></el-form-item>
        <el-form-item label="人员" required>
          <el-select v-model="inputForm.employee_code" filterable placeholder="选择人员" style="width: 100%;">
            <el-option v-for="employee in adjustmentEmployeeOptions" :key="employee.employee_code" :label="`${employee.name} (${employee.employee_code})`" :value="employee.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标编码" required><el-input v-model="inputForm.metric_code" placeholder="例如 sales_target / reply_rate" :disabled="inputMode === 'edit'" /></el-form-item>
        <el-form-item label="指标名称" required><el-input v-model="inputForm.metric_name" placeholder="例如 销售目标 / 及时回复率" /></el-form-item>
        <el-form-item label="指标方向" required>
          <el-select v-model="inputForm.metric_direction" style="width: 100%;">
            <el-option label="越高越好" value="up" />
            <el-option label="越低越好" value="down" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标值"><el-input-number v-model="inputForm.target_value" :min="0" :precision="2" style="width: 100%;" /></el-form-item>
        <el-form-item label="实际值"><el-input-number v-model="inputForm.achieved_value" :min="0" :precision="2" style="width: 100%;" /></el-form-item>
        <el-form-item label="满分" required><el-input-number v-model="inputForm.max_score" :min="0" :max="100" :precision="1" style="width: 100%;" /></el-form-item>
        <el-form-item label="人工评分">
          <el-switch v-model="inputForm.manual_score_enabled" />
        </el-form-item>
        <el-form-item v-if="inputForm.manual_score_enabled" label="人工分值">
          <el-input-number v-model="inputForm.manual_score_value" :min="0" :max="100" :precision="1" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="来源"><el-input v-model="inputForm.source" placeholder="例如 manual_target / system_sync" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="inputForm.reason" type="textarea" :rows="3" placeholder="填写该绩效输入项说明" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inputDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="inputSubmitting" @click="handleSubmitInput">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="adjustmentDialogVisible"
      :title="adjustmentMode === 'create' ? '新增个人绩效调整项' : '编辑个人绩效调整项'"
      width="520px"
    >
      <el-form :model="adjustmentForm" label-width="110px">
        <el-form-item label="月份"><el-input v-model="adjustmentForm.year_month" disabled /></el-form-item>
        <el-form-item label="人员" required>
          <el-select v-model="adjustmentForm.employee_code" filterable placeholder="选择人员" style="width: 100%;">
            <el-option v-for="employee in adjustmentEmployeeOptions" :key="employee.employee_code" :label="`${employee.name} (${employee.employee_code})`" :value="employee.employee_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="调整类型" required>
          <el-select v-model="adjustmentForm.adjustment_type" placeholder="选择调整类型" style="width: 100%;">
            <el-option label="考试" value="exam_score" />
            <el-option label="培训检核" value="training_check" />
            <el-option label="人工奖惩" value="manual_other" />
            <el-option label="考勤扣分" value="attendance_penalty" />
          </el-select>
        </el-form-item>
        <el-form-item label="分值变化" required><el-input-number v-model="adjustmentForm.score_delta" :min="-100" :max="100" :step="0.5" :precision="1" style="width: 100%;" /></el-form-item>
        <el-form-item label="来源"><el-input v-model="adjustmentForm.source" placeholder="例如 manual_exam / training_review" /></el-form-item>
        <el-form-item label="原因/备注"><el-input v-model="adjustmentForm.reason" type="textarea" :rows="3" placeholder="填写本次调整原因" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustmentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adjustmentSubmitting" @click="handleSubmitAdjustment">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Setting, Download } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useUserStore } from '@/stores/user'
import { useRoute } from 'vue-router'
import api from '@/api'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatNumber, formatPercent, formatInteger } from '@/utils/dataFormatter'
import { formatPayrollLockedConflictSummary } from '@/utils/payrollConflict'
import { hasScopedActionPermission } from '@/utils/actionPermissions'
import { buildShopAccountLookup, decorateShopEntity } from '@/utils/shopDisplay'
import {
  buildFormalPerformanceConfigPayload,
  extractPerformanceConfigRow,
  savePerformanceConfig
} from './performanceConfigSubmit'

const props = defineProps({
  forcedGroupBy: {
    type: String,
    default: ''
  }
})
const userStore = useUserStore()
const route = useRoute()
const showGroupToggle = computed(() => !props.forcedGroupBy)
const pageTitle = computed(() => {
  if (route.path.includes('/hr-performance-management/person')) return '个人绩效管理'
  if (route.path.includes('/hr-performance-management/shop')) return '店铺绩效管理'
  return '绩效管理'
})
const pageSubtitle = computed(() => {
  if (props.forcedGroupBy === 'person') {
    return '用于查看个人绩效结果、执行月度重算，并维护个人绩效输入项和调整项。'
  }
  if (props.forcedGroupBy === 'shop') {
    return '用于查看各店铺的绩效结果、赛马池状态与预警信息，并完成店铺维度绩效重算。'
  }
  if (route.path.includes('/hr-performance-management/person')) {
    return '用于查看个人绩效结果、执行月度重算，并维护个人绩效调整项。'
  }
  if (route.path.includes('/hr-performance-management/shop')) {
    return '用于查看店铺绩效结果、执行月度重算，并维护店铺绩效公式。'
  }
  return '用于查看店铺/人员绩效、执行月度重算、维护绩效公式，以及录入个人绩效调整项。'
})

const hasPermission = (permission) =>
  hasScopedActionPermission({
    roles: userStore.roles || [],
    activeRole: localStorage.getItem('activeRole') || '',
    permission,
  })

// 绩效列表数据
const performanceList = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})

const resolveGroupBy = () => props.forcedGroupBy || (route.path.includes('/hr-performance-management/person') ? 'person' : 'shop')

const filters = reactive({
  period: new Date().toISOString().slice(0, 7),
  platform: '',
  shopId: null,
  groupBy: resolveGroupBy()
})

// 绩效详情
const performanceDetail = reactive({
  data: null,
  loading: false
})

const detailVisible = ref(false)
const poolFilter = ref('all')
const alertFilter = ref('all')
const shopKeyword = ref('')
const loadError = ref(false)
const calculating = ref(false)
const configVisible = ref(false)
const configSubmitting = ref(false)
const configFormRef = ref(null)
const currentConfigId = ref(null)
const employeeDirectory = ref([])
const templateDialogVisible = ref(false)
const templateSubmitting = ref(false)
const templateOptions = ref([])
const inputDialogVisible = ref(false)
const inputSubmitting = ref(false)
const inputMode = ref('create')
const adjustmentDialogVisible = ref(false)
const adjustmentSubmitting = ref(false)
// 新增/编辑模式
const adjustmentMode = ref('create')
let shopDisplayLookup = new Map()

const inputList = reactive({
  data: [],
  total: 0,
  loading: false
})

const adjustmentList = reactive({
  data: [],
  total: 0,
  loading: false
})

// 配置表单
const configForm = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20,
  sales_max_score: 30,
  profit_max_score: 25,
  key_product_max_score: 25,
  operation_max_score: 20
})
const weightConfig = reactive({
  sales_weight: 30,
  profit_weight: 25,
  key_product_weight: 25,
  operation_weight: 20,
  sales_max_score: 30,
  profit_max_score: 25,
  key_product_max_score: 25,
  operation_max_score: 20
})
const inputForm = reactive({
  id: null,
  year_month: '',
  employee_code: '',
  metric_code: '',
  metric_name: '',
  metric_direction: 'up',
  target_value: 0,
  achieved_value: 0,
  max_score: 20,
  manual_score_enabled: false,
  manual_score_value: null,
  source: '',
  reason: ''
})
const templateForm = reactive({
  employee_code: '',
  year_month: '',
  template_code: '',
  overwrite: false
})
const adjustmentForm = reactive({
  id: null,
  year_month: '',
  employee_code: '',
  adjustment_type: 'exam_score',
  score_delta: 0,
  source: '',
  reason: ''
})

const formulaText = computed(() => {
  if (filters.groupBy === 'person') {
    return '个人绩效输入项得分 + 个人调整项 + 考勤扣分；无输入项时才回退至店铺汇总绩效'
  }
  return `销售额满分${weightConfig.sales_max_score} + 毛利满分${weightConfig.profit_max_score} + 店铺运营满分${weightConfig.operation_max_score}`
})

const currentGroupPolicyText = computed(() => {
  if (filters.groupBy === 'person') {
    return '人员绩效优先来源于个人绩效输入项；人工调整和考勤扣分继续叠加。若当月未配置个人输入项，系统才回退到挂店店铺绩效聚合。'
  }
  return '店铺总分由销售、毛利和运营三项组成；重点产品当前不纳入正式口径。正式池店铺按公司总榜排名并叠加分数底线生成赛马系数。'
})

// 表单验证规则
const adjustmentEmployeeOptions = computed(() => {
  return (employeeDirectory.value || []).filter((item) => !item.status || item.status === 'active')
})
const selectedTemplateSummary = computed(() => {
  const selected = (templateOptions.value || []).find((item) => item.template_code === templateForm.template_code)
  if (!selected) return ''
  return `${selected.template_name}：${(selected.metrics || []).map((item) => item.metric_name).join(' / ')}`
})

const configRules = {
  sales_max_score: [
    { required: true, message: '销售额满分不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '满分范围为 0-100', trigger: 'blur' }
  ],
  profit_max_score: [
    { required: true, message: '毛利满分不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '满分范围为 0-100', trigger: 'blur' }
  ],
  operation_max_score: [
    { required: true, message: '运营满分不能为空', trigger: 'blur' },
    { type: 'number', min: 0, max: 100, message: '满分范围为 0-100', trigger: 'blur' }
  ]
}

function formatCell(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v)
}

// 加载绩效列表
function isMetricCalculated(metric) {
  return metric?.status === 'calculated'
}

function metricTagType(metric, successThreshold, warningThreshold) {
  if (!isMetricCalculated(metric)) return 'info'
  const score = Number(metric?.score || 0)
  if (score >= successThreshold) return 'success'
  if (score >= warningThreshold) return 'warning'
  return 'danger'
}

function metricScoreText(metric) {
  if (!isMetricCalculated(metric) || metric?.score == null) return '未就绪'
  return `${Number(metric.score).toFixed(1)}分`
}

function metricValueText(metric, field, valueType = 'text') {
  const value = metric?.[field]
  if (value == null || value === '') return '—'
  if (valueType === 'currency') return formatCurrency(value)
  if (valueType === 'percent') return formatPercent(value)
  if (typeof value === 'number') return Number(value).toFixed(1)
  return String(value)
}

function metricMessageText(metric) {
  return metric?.calculation || metric?.message || '—'
}

function rankingPoolText(row) {
  const status = row?.score_details?.summary?.ranking_pool_status
  if (status === 'official') return '正式池'
  if (status === 'observation') return '观察池'
  return '—'
}

function performanceAlertText(row) {
  const level = row?.score_details?.summary?.performance_alert_level
  const types = row?.score_details?.summary?.performance_alert_types || []
  if (types.includes('performance_elimination_review')) return '淘汰评估'
  if (level === 'critical') return '红牌'
  if (level === 'warning') return '黄牌'
  return '—'
}

const filteredPerformanceData = computed(() => {
  if (filters.groupBy !== 'shop') {
    return performanceList.data || []
  }
  return (performanceList.data || []).filter((row) => {
    const pool = row?.score_details?.summary?.ranking_pool_status || 'unknown'
    const alertTypes = row?.score_details?.summary?.performance_alert_types || []
    const alert = alertTypes.includes('performance_elimination_review')
      ? 'elimination'
      : alertTypes.includes('performance_red_card')
        ? 'red'
        : alertTypes.includes('performance_yellow_card')
          ? 'yellow'
          : 'none'
    const poolOk = poolFilter.value === 'all' || pool === poolFilter.value
    const alertOk = alertFilter.value === 'all' || alert === alertFilter.value
    const keywordOk = !shopKeyword.value.trim() || (row.search_text || `${row.shop_name || ''} ${row.shop_id || ''}`.toLowerCase()).includes(shopKeyword.value.trim().toLowerCase())
    return poolOk && alertOk && keywordOk
  })
})

const loadShopDisplayLookup = async () => {
  try {
    const response = await api.getShopDirectory({ enabled: true })
    shopDisplayLookup = buildShopAccountLookup(Array.isArray(response) ? response : [])
  } catch (_error) {
    shopDisplayLookup = new Map()
  }
}

const detailMetricCards = computed(() => {
  const data = performanceDetail.data || {}
  return [
    {
      key: 'sales_score',
      label: '销售额得分',
      maxScore: weightConfig.sales_max_score,
      metric: data.sales_score,
      successThreshold: 27,
      warningThreshold: 24,
      targetType: 'currency',
      achievedType: 'currency',
    },
    {
      key: 'profit_score',
      label: '毛利得分',
      maxScore: weightConfig.profit_max_score,
      metric: data.profit_score,
      successThreshold: 22.5,
      warningThreshold: 20,
      targetType: 'currency',
      achievedType: 'currency',
    },
    {
      key: 'operation_score',
      label: '店铺运营得分',
      maxScore: weightConfig.operation_max_score,
      metric: data.operation_score,
      successThreshold: 18,
      warningThreshold: 16,
      targetType: 'text',
      achievedType: 'text',
    },
  ]
})

const loadPerformanceList = async () => {
  performanceList.loading = true
  loadError.value = false
  try {
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    
    const response = await api.getPerformanceScores({
      period,
      platform: filters.platform || undefined,
      shop_id: filters.shopId || undefined,
      group_by: filters.groupBy,
      page: performanceList.page,
      page_size: performanceList.pageSize
    })
    
    // 兼容分页响应结构
    if (response && Array.isArray(response)) {
      performanceList.data = filters.groupBy === 'shop'
        ? response.map((row) => decorateShopEntity(row, shopDisplayLookup))
        : response
      performanceList.total = response.length
    } else {
      const rows = response?.data || response || []
      performanceList.data = filters.groupBy === 'shop'
        ? rows.map((row) => decorateShopEntity(row, shopDisplayLookup))
        : rows
      performanceList.total = response?.total || 0
    }
  } catch (error) {
    loadError.value = true
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceList.loading = false
  }
}

const loadWeightConfig = async () => {
  try {
    const response = await api.getPerformanceConfigs({ is_active: true, page: 1, page_size: 1 })
    const row = extractPerformanceConfigRow(response)
    if (!row) return
    weightConfig.sales_weight = row.sales_weight ?? weightConfig.sales_weight
    weightConfig.profit_weight = row.profit_weight ?? weightConfig.profit_weight
    weightConfig.key_product_weight = row.key_product_weight ?? weightConfig.key_product_weight
    weightConfig.operation_weight = row.operation_weight ?? weightConfig.operation_weight
    weightConfig.sales_max_score = row.sales_max_score ?? weightConfig.sales_max_score
    weightConfig.profit_max_score = row.profit_max_score ?? weightConfig.profit_max_score
    weightConfig.key_product_max_score = row.key_product_max_score ?? weightConfig.key_product_max_score
    weightConfig.operation_max_score = row.operation_max_score ?? weightConfig.operation_max_score
  } catch (error) {
    // 配置读取失败时不阻塞页面加载
  }
}

const loadEmployeeDirectory = async () => {
  if (!hasPermission('performance:config')) return
  try {
    const response = await api.getHrEmployees({ page: 1, page_size: 500 })
    const data = Array.isArray(response) ? response : (response?.items || response?.data?.items || response?.data || [])
    employeeDirectory.value = Array.isArray(data) ? data : []
  } catch (error) {
    employeeDirectory.value = []
  }
}

const loadAdjustmentList = async () => {
  if (!hasPermission('performance:config')) return
  adjustmentList.loading = true
  try {
    const response = await api.getHrPerformanceAdjustments({
      year_month: typeof filters.period === 'string' ? filters.period : undefined,
      page: 1,
      page_size: 100
    })
    adjustmentList.data = response?.items || []
    adjustmentList.total = response?.total || 0
  } catch (error) {
    adjustmentList.data = []
    adjustmentList.total = 0
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    adjustmentList.loading = false
  }
}

const loadInputList = async () => {
  if (!hasPermission('performance:config')) return
  inputList.loading = true
  try {
    const response = await api.getHrPerformanceInputs({
      year_month: typeof filters.period === 'string' ? filters.period : undefined,
      page: 1,
      page_size: 100
    })
    inputList.data = response?.data?.items || response?.items || []
    inputList.total = response?.data?.total || response?.total || 0
  } catch (error) {
    inputList.data = []
    inputList.total = 0
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    inputList.loading = false
  }
}

const handleRefreshAll = async () => {
  await loadPerformanceList()
  if (filters.groupBy === 'person') {
    await loadInputList()
    await loadAdjustmentList()
  }
}

const handleGroupByChange = async () => {
  await loadPerformanceList()
  if (filters.groupBy === 'person') {
    await loadInputList()
    await loadAdjustmentList()
  }
}

const handlePeriodChange = async () => {
  await handleRefreshAll()
}

const resetAdjustmentForm = () => {
  adjustmentForm.id = null
  adjustmentForm.year_month = typeof filters.period === 'string' ? filters.period : ''
  adjustmentForm.employee_code = ''
  adjustmentForm.adjustment_type = 'exam_score'
  adjustmentForm.score_delta = 0
  adjustmentForm.source = ''
  adjustmentForm.reason = ''
}

const resetInputForm = () => {
  inputForm.id = null
  inputForm.year_month = typeof filters.period === 'string' ? filters.period : ''
  inputForm.employee_code = ''
  inputForm.metric_code = ''
  inputForm.metric_name = ''
  inputForm.metric_direction = 'up'
  inputForm.target_value = 0
  inputForm.achieved_value = 0
  inputForm.max_score = 20
  inputForm.manual_score_enabled = false
  inputForm.manual_score_value = null
  inputForm.source = ''
  inputForm.reason = ''
}

const resetTemplateForm = () => {
  templateForm.employee_code = ''
  templateForm.year_month = typeof filters.period === 'string' ? filters.period : ''
  templateForm.template_code = ''
  templateForm.overwrite = false
  templateOptions.value = []
}

const loadTemplateOptions = async () => {
  if (!templateForm.employee_code) {
    templateOptions.value = []
    templateForm.template_code = ''
    return
  }
  try {
    const response = await api.getHrPerformanceInputTemplates({
      employee_code: templateForm.employee_code
    })
    const items = response?.data?.items || response?.items || []
    templateOptions.value = items
    templateForm.template_code = response?.data?.recommended_template_code || items[0]?.template_code || ''
  } catch (error) {
    templateOptions.value = []
    templateForm.template_code = ''
    handleApiError(error, { showMessage: true, logError: true })
  }
}

const openApplyTemplate = async () => {
  resetTemplateForm()
  templateDialogVisible.value = true
}

const handleApplyTemplate = async () => {
  if (!templateForm.employee_code) {
    ElMessage.warning('请选择人员')
    return
  }
  templateSubmitting.value = true
  try {
    await api.applyHrPerformanceInputTemplate({
      employee_code: templateForm.employee_code,
      year_month: templateForm.year_month,
      template_code: templateForm.template_code || undefined,
      overwrite: Boolean(templateForm.overwrite)
    })
    ElMessage.success('个人绩效模板已套用')
    templateDialogVisible.value = false
    await loadInputList()
    await loadPerformanceList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    templateSubmitting.value = false
  }
}

const openCreateInput = () => {
  inputMode.value = 'create'
  resetInputForm()
  inputDialogVisible.value = true
}

const openEditInput = (row) => {
  inputMode.value = 'edit'
  inputForm.id = row.id
  inputForm.year_month = row.year_month
  inputForm.employee_code = row.employee_code
  inputForm.metric_code = row.metric_code
  inputForm.metric_name = row.metric_name || row.metric_code
  inputForm.metric_direction = row.metric_direction || 'up'
  inputForm.target_value = Number(row.target_value || 0)
  inputForm.achieved_value = Number(row.achieved_value || 0)
  inputForm.max_score = Number(row.max_score || 0)
  inputForm.manual_score_enabled = Boolean(row.manual_score_enabled)
  inputForm.manual_score_value = row.manual_score_value != null ? Number(row.manual_score_value) : null
  inputForm.source = row.source || ''
  inputForm.reason = row.reason || ''
  inputDialogVisible.value = true
}

const handleSubmitInput = async () => {
  if (!inputForm.year_month) {
    ElMessage.warning('请选择月份')
    return
  }
  if (!inputForm.employee_code) {
    ElMessage.warning('请选择人员')
    return
  }
  if (!inputForm.metric_code || !inputForm.metric_name) {
    ElMessage.warning('请填写指标编码和指标名称')
    return
  }
  inputSubmitting.value = true
  try {
    const payload = {
      year_month: inputForm.year_month,
      employee_code: inputForm.employee_code,
      metric_code: inputForm.metric_code,
      metric_name: inputForm.metric_name,
      metric_direction: inputForm.metric_direction,
      target_value: Number(inputForm.target_value || 0),
      achieved_value: Number(inputForm.achieved_value || 0),
      max_score: Number(inputForm.max_score || 0),
      manual_score_enabled: Boolean(inputForm.manual_score_enabled),
      manual_score_value: inputForm.manual_score_enabled ? Number(inputForm.manual_score_value || 0) : null,
      source: inputForm.source || null,
      reason: inputForm.reason || null
    }
    if (inputMode.value === 'create') {
      await api.createHrPerformanceInput(payload)
    } else {
      await api.updateHrPerformanceInput(inputForm.id, payload)
    }
    ElMessage.success('个人绩效输入项保存成功')
    inputDialogVisible.value = false
    await loadInputList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    inputSubmitting.value = false
  }
}

const handleDeleteInput = async (row) => {
  try {
    await ElMessageBox.confirm('确认停用该个人绩效输入项吗？', '确认停用', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await api.deleteHrPerformanceInput(row.id)
    ElMessage.success('已停用该输入项')
    await loadInputList()
  } catch (error) {
    if (error !== 'cancel') {
      handleApiError(error, { showMessage: true, logError: true })
    }
  }
}

const openCreateAdjustment = () => {
  adjustmentMode.value = 'create'
  resetAdjustmentForm()
  adjustmentDialogVisible.value = true
}

const openEditAdjustment = (row) => {
  adjustmentMode.value = 'edit'
  adjustmentForm.id = row.id
  adjustmentForm.year_month = row.year_month
  adjustmentForm.employee_code = row.employee_code
  adjustmentForm.adjustment_type = row.adjustment_type
  adjustmentForm.score_delta = Number(row.score_delta || 0)
  adjustmentForm.source = row.source || ''
  adjustmentForm.reason = row.reason || ''
  adjustmentDialogVisible.value = true
}

const handleSubmitAdjustment = async () => {
  if (!adjustmentForm.year_month) {
    ElMessage.warning('请选择月份')
    return
  }
  if (!adjustmentForm.employee_code) {
    ElMessage.warning('请选择人员')
    return
  }
  adjustmentSubmitting.value = true
  try {
    const payload = {
      year_month: adjustmentForm.year_month,
      employee_code: adjustmentForm.employee_code,
      adjustment_type: adjustmentForm.adjustment_type,
      score_delta: Number(adjustmentForm.score_delta || 0),
      source: adjustmentForm.source || null,
      reason: adjustmentForm.reason || null
    }
    if (adjustmentMode.value === 'create') {
      await api.createHrPerformanceAdjustment(payload)
    } else {
      await api.updateHrPerformanceAdjustment(adjustmentForm.id, payload)
    }
    ElMessage.success('个人绩效调整项保存成功')
    adjustmentDialogVisible.value = false
    await loadAdjustmentList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    adjustmentSubmitting.value = false
  }
}

const handleDeleteAdjustment = async (row) => {
  try {
    await ElMessageBox.confirm('确认停用该个人绩效调整项吗？', '确认停用', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await api.deleteHrPerformanceAdjustment(row.id)
    ElMessage.success('已停用该调整项')
    await loadAdjustmentList()
  } catch (error) {
    if (error !== 'cancel') {
      handleApiError(error, { showMessage: true, logError: true })
    }
  }
}

const handleRecalculate = async () => {
  const period = typeof filters.period === 'string'
    ? filters.period
    : (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : '')
  if (!period) {
    ElMessage.warning('请选择考核月份')
    return
  }
  calculating.value = true
  try {
    const result = await api.calculatePerformanceScores(period)
    ElMessage.success('已完成当月店铺绩效、个人绩效和提成重算，请刷新查看最新结果')
    const lockedConflicts = result?.payroll_locked_conflicts || 0
    const conflictDetails = result?.payroll_locked_conflict_details || []
    if (lockedConflicts > 0) {
      const summary = formatPayrollLockedConflictSummary(conflictDetails, lockedConflicts)
      await ElMessageBox.alert(summary, '工资单锁定冲突', {
        type: 'warning',
        confirmButtonText: '知道了'
      })
    }
    await handleRefreshAll()
  } catch (error) {
    const code = error?.response?.data?.data?.error_code
    if (code === 'PERF_CALC_NOT_READY') {
      ElMessage.warning('绩效计算能力未就绪，请先完成 PostgreSQL 数据链路与目标分解配置')
    } else if (code === 'PERF_CONFIG_NOT_FOUND') {
      ElMessage.warning('当前考核周期无可用绩效配置，请先配置公式和生效周期')
    } else {
      handleApiError(error, { showMessage: true, logError: true })
    }
  } finally {
    calculating.value = false
  }
}

// 查看详情
const handleViewDetail = async (row) => {
  detailVisible.value = true
  performanceDetail.loading = true
  try {
    const period = typeof filters.period === 'string' ? filters.period : 
      (filters.period ? `${filters.period.getFullYear()}-${String(filters.period.getMonth() + 1).padStart(2, '0')}` : undefined)
    const response = await api.getShopPerformanceDetail(row.platform_code, row.shop_id, period)
    const payload = response?.data ?? response ?? {}
    performanceDetail.data = decorateShopEntity(payload, shopDisplayLookup)
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    performanceDetail.loading = false
  }
}

// 配置公式
const handleConfig = async () => {
  const response = await api.getPerformanceConfigs({ is_active: true, page: 1, page_size: 1 })
  const setForm = (config) => {
    currentConfigId.value = config.id || null
    configForm.sales_weight = config.sales_weight ?? 30
    configForm.profit_weight = config.profit_weight ?? 25
    configForm.key_product_weight = config.key_product_weight ?? 25
    configForm.operation_weight = config.operation_weight ?? 20
    configForm.sales_max_score = config.sales_max_score ?? 30
    configForm.profit_max_score = config.profit_max_score ?? 25
    configForm.key_product_max_score = config.key_product_max_score ?? 25
    configForm.operation_max_score = config.operation_max_score ?? 20
  }
  const currentConfig = extractPerformanceConfigRow(response)
  if (currentConfig) {
    setForm(currentConfig)
  } else {
    currentConfigId.value = null
  }
  configVisible.value = true
}

// 提交配置
const handleConfigSubmit = async () => {
  configSubmitting.value = true
  try {
    await savePerformanceConfig({
      api,
      currentConfigId: currentConfigId.value,
      payload: buildFormalPerformanceConfigPayload(configForm),
      effectiveFrom: new Date().toISOString().slice(0, 10)
    })
    
    ElMessage.success('配置更新成功')
    configVisible.value = false
    await loadWeightConfig()
    await loadPerformanceList()
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    configSubmitting.value = false
  }
}

// 关闭配置对话框
const handleConfigClose = () => {
  configFormRef.value?.resetFields()
}

// 导出报表
const handleExport = () => {
  ElMessage.info('导出功能开发中（当前为占位实现）')
  // TODO: 实现 Excel 导出功能
}

// formatCurrency 已从 dataFormatter 导入，无需重复声明

watch(() => route.path, () => {
  filters.groupBy = resolveGroupBy()
  if (typeof handleRefreshAll === 'function') {
    handleRefreshAll()
  } else {
    loadPerformanceList()
  }
})

onMounted(async () => {
  await loadWeightConfig()
  await loadEmployeeDirectory()
  await loadShopDisplayLookup()
  await handleRefreshAll()
})
</script>

<style scoped>
.performance-management {
  padding: 20px;
  --perf-text-primary: #1d1d1f;
  --perf-text-secondary: #6e6e73;
  --perf-surface: #ffffff;
  --perf-surface-muted: #f5f5f7;
  --perf-border: #d2d2d7;
  --perf-shadow: 0 12px 32px rgba(15, 23, 42, 0.05);
}

.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 20px;
  padding: 14px 16px;
  border: 1px solid var(--perf-border);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(245, 245, 247, 0.96) 100%);
  box-shadow: var(--perf-shadow);
}

.policy-card {
  margin-bottom: 20px;
  border-color: var(--perf-border);
  border-radius: 18px;
  background: var(--perf-surface);
  box-shadow: var(--perf-shadow);
}

.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.policy-item {
  padding: 14px 16px;
  border: 1px solid var(--perf-border);
  border-radius: 14px;
  background: var(--perf-surface-muted);
}

.policy-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--perf-text-primary);
}

.policy-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--perf-text-secondary);
}

.card-header span {
  color: var(--perf-text-primary);
}

.shop-display-cell {
  line-height: 1.4;
}

.shop-display-secondary {
  font-size: 12px;
  color: var(--perf-text-secondary);
}

/* 浼佷笟绾ц〃鏍兼牱寮?*/
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
</style>


