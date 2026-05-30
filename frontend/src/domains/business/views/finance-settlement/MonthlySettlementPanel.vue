<template>
  <el-card class="section-card company-card">
    <template #header>
      <div class="card-header">
        <span>月度利润结算中心</span>
        <el-tag type="success">公司月结</el-tag>
      </div>
    </template>

    <el-form :inline="true" class="filter-form">
      <el-form-item label="月份">
        <el-date-picker v-model="monthlyForm.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" />
      </el-form-item>
      <el-form-item label="人员成本预算(%)">
        <el-input-number v-model="monthlyForm.personnel_target_ratio" :min="0" :max="1" :step="0.05" :precision="2" :formatter="formatRatioInput" :parser="parseRatioInput" />
      </el-form-item>
      <el-form-item label="跟投收益预算(%)">
        <el-input-number v-model="monthlyForm.follow_target_ratio" :min="0" :max="1" :step="0.05" :precision="2" :formatter="formatRatioInput" :parser="parseRatioInput" />
      </el-form-item>
      <el-form-item label="公司留存预算(%)">
        <el-input-number v-model="monthlyForm.company_target_ratio" :min="0" :max="1" :step="0.05" :precision="2" :formatter="formatRatioInput" :parser="parseRatioInput" />
      </el-form-item>
      <el-form-item label="调整金额">
        <el-input-number v-model="monthlyForm.adjustment_amount" :step="100" :precision="2" />
      </el-form-item>
      <el-form-item label="调整原因">
        <el-input v-model="monthlyForm.adjustment_reason" placeholder="请输入调整原因" style="width: 220px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="$emit('load-monthly')" :loading="loading">查询月结</el-button>
        <el-button @click="$emit('rebuild-monthly')" :loading="loading">重建月结</el-button>
        <el-button v-if="currentSettlementId" @click="$emit('save-monthly-targets')" :loading="loading">保存目标</el-button>
        <el-button v-if="currentSettlementId && monthlySummary?.status !== 'approved'" type="success" @click="$emit('approve-monthly')">审批通过</el-button>
        <el-button v-if="currentSettlementId && monthlySummary?.status === 'approved'" type="warning" @click="$emit('reopen-monthly')">回退草稿</el-button>
      </el-form-item>
    </el-form>

    <el-alert v-if="error" type="error" :closable="false" :title="error" class="section-alert" />
    <el-alert v-if="showSettlementDifferenceWarning" type="warning" :closable="false" title="当前月结差异超过默认阈值，系统将拦截直接审批，请先核对上游数据或填写调整原因。" class="section-alert" />

    <el-row v-if="monthlySummary" :gutter="20" class="summary-grid">
      <el-col :xs="24" :sm="12" :md="3"><div class="summary-item"><div class="summary-label">月度净利润</div><div class="summary-value profit">{{ formatCurrency(monthlySummary.net_profit_amount) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="3"><div class="summary-item"><div class="summary-label">人员成本</div><div class="summary-value cost">{{ formatCurrency(monthlySummary.personnel_actual_amount) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="3"><div class="summary-item"><div class="summary-label">跟投收益</div><div class="summary-value revenue">{{ formatCurrency(monthlySummary.follow_actual_amount) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="3"><div class="summary-item"><div class="summary-label">公司留存</div><div class="summary-value profit">{{ formatCurrency(monthlySummary.company_actual_amount) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="4"><div class="summary-item compact"><div class="summary-label">预算差异金额</div><div>{{ formatCurrency(monthlySummary.difference_amount) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="4"><div class="summary-item compact"><div class="summary-label">预算差异比例</div><div>{{ formatPercentValue(monthlySummary.difference_ratio) }}</div></div></el-col>
      <el-col :xs="24" :sm="12" :md="4"><div class="summary-item compact"><div class="summary-label">月结状态</div><div>{{ monthlySummary.status || '-' }}</div></div></el-col>
    </el-row>
  </el-card>
</template>

<script setup>
defineProps({
  monthlyForm: { type: Object, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  currentSettlementId: { type: [Number, null], default: null },
  monthlySummary: { type: Object, default: null },
  showSettlementDifferenceWarning: { type: Boolean, default: false },
  formatCurrency: { type: Function, required: true },
  formatPercentValue: { type: Function, required: true },
  formatRatioInput: { type: Function, required: true },
  parseRatioInput: { type: Function, required: true }
})

defineEmits(['load-monthly', 'rebuild-monthly', 'save-monthly-targets', 'approve-monthly', 'reopen-monthly'])
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.filter-form { margin-bottom: 16px; }
.section-alert { margin-bottom: 16px; }
.summary-grid { margin-bottom: 20px; }
.summary-item { height: 100%; padding: 20px; border-radius: 10px; background: #fafbfc; border: 1px solid #ebeef5; }
.summary-item.compact { padding: 16px 20px; }
.summary-label { margin-bottom: 8px; color: #606266; font-size: 13px; }
.summary-value { font-size: 28px; font-weight: 700; }
.summary-value.revenue { color: #2f7a9a; }
.summary-value.cost { color: #d46b08; }
.summary-value.profit { color: #237804; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
</style>
