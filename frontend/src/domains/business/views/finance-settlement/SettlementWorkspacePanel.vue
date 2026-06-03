<template>
  <el-card class="section-card workspace-card">
    <template #header>
      <div class="card-header workspace-header">
        <div>
          <span>店铺工作区</span>
          <div class="workspace-subtitle">按平台查看已启用店铺，左侧选店，右侧完成单店利润口径、跟投试算和结算处理。</div>
        </div>
        <div class="workspace-filters">
          <el-date-picker v-model="selectedMonthValue" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" @change="$emit('handle-month-change')" />
          <el-select v-model="selectedPlatformValue" style="width: 140px" @change="$emit('handle-platform-change')">
            <el-option v-for="platform in platformOptions" :key="platform" :label="platformLabels[platform] || platform" :value="platform" />
          </el-select>
        </div>
      </div>
    </template>

    <div class="platform-overview-card">
      <div class="platform-overview-header">
        <span>本平台店铺概览</span>
        <div class="platform-overview-meta">{{ selectedPlatformLabel }} · {{ selectedMonth }}</div>
      </div>
      <div class="platform-overview-grid">
        <div class="platform-overview-item"><div class="overview-label">平台店铺数</div><div class="overview-value">{{ platformShopStats.total }}</div></div>
        <div class="platform-overview-item"><div class="overview-label">可继续结算店铺</div><div class="overview-value">{{ platformShopStats.canSettle }}</div></div>
        <div class="platform-overview-item"><div class="overview-label">有跟投记录店铺</div><div class="overview-value">{{ platformShopStats.withFollowInvestment }}</div></div>
        <div class="platform-overview-item"><div class="overview-label">有结算台账店铺</div><div class="overview-value">{{ platformShopStats.withSettlement }}</div></div>
        <div class="platform-overview-item warning"><div class="overview-label">待补经营数据</div><div class="overview-value">{{ platformShopStats.pendingData }}</div></div>
      </div>
      <div class="rule-summary-card">
        <div class="rule-summary-title">规则口径</div>
        <div class="rule-summary-list">
          <div>已具备结算信号：同时存在跟投记录与当月结算台账。</div>
          <div>可继续结算店铺：已具备结算信号，且可进入单店结算处理。</div>
          <div>待补经营数据：既没有跟投记录，也没有当月结算台账。</div>
          <div>异常店铺：缺少结算台账，或仍处于待补经营数据状态。</div>
        </div>
      </div>
    </div>

    <div class="workspace-layout">
      <aside class="shop-list-panel">
        <div class="shop-list-header">
          <span>可用店铺列表</span>
          <el-tag type="info">{{ filteredShops.length }} 家</el-tag>
        </div>
        <div class="shop-list-toolbar">
          <div class="shop-filter-block">
            <div class="shop-filter-label">店铺筛选</div>
            <el-radio-group v-model="shopFilterModeValue" size="small">
              <el-radio-button label="all">全部店铺</el-radio-button>
              <el-radio-button label="exception">只看异常店铺</el-radio-button>
              <el-radio-button label="pending">只看待补经营数据</el-radio-button>
            </el-radio-group>
          </div>
          <el-input v-model="shopKeywordValue" clearable placeholder="按店铺名称或店铺ID筛选" />
          <div class="shop-list-hints">
            <span>平台：{{ selectedPlatformLabel }}</span>
            <span>当前店铺：{{ selectedShop?.shop_name || '未选择' }}</span>
          </div>
        </div>
        <div class="shop-list">
          <button
            v-for="shop in filteredShops"
            :key="shop.shop_id"
            type="button"
            class="shop-row"
            :class="{ active: selectedShop?.shop_id === shop.shop_id }"
            @click="$emit('select-shop', shop)"
          >
            <div class="shop-row-top">
              <div class="shop-display-cell">
                <span class="shop-name">{{ shop.shop_name }}</span>
                <div v-if="shop.secondary_name" class="shop-display-secondary">{{ shop.secondary_name }}</div>
              </div>
              <div class="shop-row-tags">
                <el-tag v-if="selectedShop?.shop_id === shop.shop_id" size="small" type="primary">当前</el-tag>
                <el-tag size="small" :type="shop.enabled === false ? 'danger' : 'success'">{{ shop.enabled === false ? '停用' : '可用' }}</el-tag>
                <el-tag v-if="getShopStatus(shop).canSettle" size="small" type="success">可继续结算</el-tag>
                <el-tag v-if="getShopStatus(shop).hasFollowInvestment" size="small" type="warning">有跟投记录</el-tag>
                <el-tag v-if="getShopStatus(shop).hasSettlement" size="small" type="info">有结算台账</el-tag>
                <el-tag v-if="getShopStatus(shop).hasException" size="small" type="danger">异常</el-tag>
                <el-tag v-if="getShopStatus(shop).pendingData" size="small" effect="plain">待补经营数据</el-tag>
              </div>
            </div>
            <div class="shop-meta">{{ shop.shop_id }}</div>
            <div class="shop-submeta">{{ selectedPlatformLabel }} · 已纳入财务结算范围</div>
          </button>
          <el-empty v-if="!filteredShops.length" description="当前筛选条件下暂无可用店铺" />
        </div>
      </aside>

      <section class="shop-detail-panel">
        <div class="shop-detail-header">
          <div>
            <div class="shop-detail-title">当前店铺详情</div>
            <div class="shop-detail-meta">
              <template v-if="selectedShop">
                {{ selectedShop.shop_name }}（{{ selectedShop.shop_id }}）
                <span v-if="selectedShop.secondary_name" class="shop-display-secondary shop-detail-secondary">{{ selectedShop.secondary_name }}</span>
              </template>
              <template v-else>请先从左侧选择店铺</template>
            </div>
          </div>
          <div v-if="selectedShop" class="shop-detail-signals">
            <el-tag effect="plain" :type="settlementStore.profitBasis.data ? 'success' : 'info'">{{ settlementStore.profitBasis.data ? '利润口径已加载' : '待加载利润口径' }}</el-tag>
            <el-tag effect="plain" :type="settlementStore.followInvestments.data.length ? 'success' : 'warning'">跟投记录 {{ settlementStore.followInvestments.data.length }} 条</el-tag>
            <el-tag effect="plain" :type="settlementStore.followInvestmentSettlements.data.length ? 'success' : 'info'">结算台账 {{ settlementStore.followInvestmentSettlements.data.length }} 条</el-tag>
          </div>
        </div>

        <el-empty v-if="!selectedShop" description="请先从左侧店铺列表选择一个店铺" />
        <div v-else>
          <el-card class="shop-next-step-card" v-if="recommendedActions.length">
            <template #header>
              <div class="card-header">
                <span>推荐下一步</span>
                <el-tag type="primary">{{ recommendedActions.length }} 条</el-tag>
              </div>
            </template>
            <div class="shop-next-step-list">
              <div v-for="item in recommendedActions" :key="item.key" class="shop-next-step-item">
                <div class="shop-next-step-title">{{ item.title }}</div>
                <div class="shop-next-step-desc">{{ item.description }}</div>
              </div>
            </div>
          </el-card>

          <el-card class="shop-exception-card" v-if="shopExceptionItems.length">
            <template #header>
              <div class="card-header">
                <span>当前店铺异常提示</span>
                <el-tag type="danger">{{ shopExceptionItems.length }} 项</el-tag>
              </div>
            </template>
            <div class="shop-exception-list">
              <div v-for="item in shopExceptionItems" :key="item.key" class="shop-exception-item">
                <div class="shop-exception-title">{{ item.title }}</div>
                <div class="shop-exception-desc">{{ item.description }}</div>
              </div>
            </div>
          </el-card>

          <el-tabs v-model="activeShopTabValue" class="shop-tabs">
            <el-tab-pane label="店铺结算净利润口径" name="basis">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="profitBasisForm.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 140px" /></el-form-item>
                  <el-form-item label="店铺">
                    <div class="shop-display-input">
                      <el-input :model-value="selectedShop?.shop_name || ''" disabled style="width: 220px" />
                      <div v-if="selectedShop?.secondary_name" class="shop-display-secondary">{{ selectedShop.secondary_name }}</div>
                    </div>
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="$emit('load-profit-basis')" :disabled="!selectedShop" :loading="settlementStore.profitBasis.loading">查询基准</el-button>
                    <el-button @click="$emit('rebuild-profit-basis')" :disabled="!selectedShop" :loading="settlementStore.profitBasis.loading">重算基准</el-button>
                  </el-form-item>
                </el-form>
                <el-alert v-if="settlementStore.profitBasis.error" type="error" :closable="false" :title="settlementStore.profitBasis.error" class="section-alert" />
                <el-row v-if="settlementStore.profitBasis.data" :gutter="20" class="summary-grid">
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">订单利润</div><div class="summary-value revenue">{{ formatCurrency(settlementStore.profitBasis.data.orders_profit_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">A类成本</div><div class="summary-value cost">{{ formatCurrency(settlementStore.profitBasis.data.a_class_cost_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">B类成本</div><div class="summary-value cost">{{ formatCurrency(settlementStore.profitBasis.data.b_class_cost_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">结算基准利润</div><div class="summary-value profit">{{ formatCurrency(settlementStore.profitBasis.data.profit_basis_amount) }}</div></div></el-col>
                </el-row>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="跟投收益试算" name="trial">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="followInvestmentForm.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 140px" /></el-form-item>
                  <el-form-item label="店铺">
                    <div class="shop-display-input">
                      <el-input :model-value="selectedShop?.shop_name || ''" disabled style="width: 220px" />
                      <div v-if="selectedShop?.secondary_name" class="shop-display-secondary">{{ selectedShop.secondary_name }}</div>
                    </div>
                  </el-form-item>
                  <el-form-item label="分配比例"><el-input-number v-model="followInvestmentForm.distribution_ratio" :min="0" :max="1" :step="0.05" :precision="2" /></el-form-item>
                  <el-form-item><el-button type="primary" @click="$emit('run-follow-settlement')" :disabled="!selectedShop" :loading="settlementStore.followInvestmentSettlement.loading">试算收益</el-button></el-form-item>
                </el-form>
                <el-alert v-if="settlementStore.followInvestmentSettlement.error" type="error" :closable="false" :title="settlementStore.followInvestmentSettlement.error" class="section-alert" />
                <el-row v-if="settlementStore.followInvestmentSettlement.data?.settlement" :gutter="20" class="summary-grid">
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">结算基准利润</div><div class="summary-value profit">{{ formatCurrency(settlementStore.followInvestmentSettlement.data.settlement.profit_basis_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">分配比例</div><div class="summary-value">{{ formatPercentValue(settlementStore.followInvestmentSettlement.data.settlement.distribution_ratio) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">可分配收益</div><div class="summary-value profit">{{ formatCurrency(settlementStore.followInvestmentSettlement.data.settlement.distributable_amount) }}</div></div></el-col>
                </el-row>
                <el-table :data="settlementStore.followInvestmentSettlement.data?.details || []" v-loading="settlementStore.followInvestmentSettlement.loading" stripe>
                  <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
                  <el-table-column prop="contribution_amount_snapshot" label="本金快照" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.contribution_amount_snapshot) }}</template></el-table-column>
                  <el-table-column prop="occupied_days" label="占用天数" width="100" align="right" />
                  <el-table-column prop="weighted_capital" label="加权资金" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.weighted_capital) }}</template></el-table-column>
                  <el-table-column prop="share_ratio" label="分配占比" width="120" align="right"><template #default="{ row }">{{ formatPercentValue(row.share_ratio) }}</template></el-table-column>
                  <el-table-column prop="estimated_income" label="预计收益" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.estimated_income) }}</template></el-table-column>
                </el-table>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="跟投记录" name="records">
              <el-card class="inner-card">
                <div class="card-header inner-toolbar"><span>当前店铺跟投记录</span><el-button type="primary" size="small" @click="$emit('open-create-follow-investment')" :disabled="!selectedShop">新增跟投</el-button></div>
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="状态"><el-select v-model="followInvestmentQuery.status" clearable style="width: 140px"><el-option label="生效" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
                  <el-form-item><el-button @click="$emit('load-follow-investments')" :disabled="!selectedShop" :loading="settlementStore.followInvestments.loading">查询记录</el-button></el-form-item>
                </el-form>
                <el-table :data="settlementStore.followInvestments.data" v-loading="settlementStore.followInvestments.loading" stripe>
                  <el-table-column prop="id" label="ID" width="80" />
                  <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
                  <el-table-column prop="contribution_amount" label="本金" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.contribution_amount) }}</template></el-table-column>
                  <el-table-column prop="contribution_date" label="投入日期" width="120" />
                  <el-table-column prop="withdraw_date" label="退出日期" width="120" />
                  <el-table-column prop="status" label="状态" width="100" />
                  <el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><el-button link type="primary" size="small" @click="$emit('open-edit-follow-investment', row)">编辑</el-button><el-button link type="danger" size="small" @click="$emit('archive-follow-investment', row)">归档</el-button></template></el-table-column>
                </el-table>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="结算台账" name="ledger">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="settlementQuery.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="状态"><el-select v-model="settlementQuery.status" clearable style="width: 140px"><el-option label="草稿" value="draft" /><el-option label="已试算" value="calculated" /><el-option label="已审批" value="approved" /><el-option label="已回退" value="reopened" /></el-select></el-form-item>
                  <el-form-item><el-button @click="$emit('load-follow-investment-settlements')" :disabled="!selectedShop" :loading="settlementStore.followInvestmentSettlements.loading">查询台账</el-button></el-form-item>
                </el-form>
                <el-table :data="settlementStore.followInvestmentSettlements.data" v-loading="settlementStore.followInvestmentSettlements.loading" stripe>
                  <el-table-column prop="id" label="结算ID" width="100" />
                  <el-table-column prop="period_month" label="月份" width="120" />
                  <el-table-column prop="profit_basis_amount" label="结算基准利润" width="160" align="right"><template #default="{ row }">{{ formatCurrency(row.profit_basis_amount) }}</template></el-table-column>
                  <el-table-column prop="distribution_ratio" label="分配比例" width="120" align="right"><template #default="{ row }">{{ formatPercentValue(row.distribution_ratio) }}</template></el-table-column>
                  <el-table-column prop="distributable_amount" label="可分配收益" width="160" align="right"><template #default="{ row }">{{ formatCurrency(row.distributable_amount) }}</template></el-table-column>
                  <el-table-column prop="status" label="状态" width="100" />
                  <el-table-column prop="approved_by_name" label="审核人" width="120" />
                  <el-table-column prop="approved_at" label="审核时间" width="180"><template #default="{ row }">{{ formatDateTime(row.approved_at) }}</template></el-table-column>
                  <el-table-column label="操作" width="180" fixed="right"><template #default="{ row }"><el-button link type="info" size="small" @click="$emit('view-settlement-details', row)">查看明细</el-button><el-button v-if="row.status === 'calculated'" link type="success" size="small" @click="$emit('approve-follow-investment', row)">审批通过</el-button><el-button v-if="row.status === 'approved'" link type="warning" size="small" @click="$emit('reopen-follow-investment', row)">回退审批</el-button></template></el-table-column>
                </el-table>
              </el-card>
            </el-tab-pane>
          </el-tabs>
        </div>
      </section>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  settlementStore: { type: Object, required: true },
  selectedMonth: { type: Object, required: true },
  selectedPlatform: { type: Object, required: true },
  shopKeyword: { type: Object, required: true },
  shopFilterMode: { type: Object, required: true },
  activeShopTab: { type: Object, required: true },
  platformOptions: { type: Array, required: true },
  platformLabels: { type: Object, required: true },
  selectedPlatformLabel: { type: String, required: true },
  filteredShops: { type: Array, required: true },
  selectedShop: { type: Object, default: null },
  platformShopStats: { type: Object, required: true },
  shopExceptionItems: { type: Array, required: true },
  recommendedActions: { type: Array, required: true },
  profitBasisForm: { type: Object, required: true },
  followInvestmentForm: { type: Object, required: true },
  followInvestmentQuery: { type: Object, required: true },
  settlementQuery: { type: Object, required: true },
  formatCurrency: { type: Function, required: true },
  formatPercentValue: { type: Function, required: true },
  formatDateTime: { type: Function, required: true },
  getShopStatus: { type: Function, required: true }
})

defineEmits([
  'handle-month-change',
  'handle-platform-change',
  'select-shop',
  'load-profit-basis',
  'rebuild-profit-basis',
  'run-follow-settlement',
  'load-follow-investments',
  'load-follow-investment-settlements',
  'view-settlement-details',
  'approve-follow-investment',
  'reopen-follow-investment',
  'open-create-follow-investment',
  'open-edit-follow-investment',
  'archive-follow-investment'
])

const selectedMonthValue = computed({
  get: () => props.selectedMonth.value,
  set: (value) => {
    props.selectedMonth.value = value
  }
})

const selectedPlatformValue = computed({
  get: () => props.selectedPlatform.value,
  set: (value) => {
    props.selectedPlatform.value = value
  }
})

const shopKeywordValue = computed({
  get: () => props.shopKeyword.value,
  set: (value) => {
    props.shopKeyword.value = value
  }
})

const shopFilterModeValue = computed({
  get: () => props.shopFilterMode.value,
  set: (value) => {
    props.shopFilterMode.value = value
  }
})

const activeShopTabValue = computed({
  get: () => props.activeShopTab.value,
  set: (value) => {
    props.activeShopTab.value = value
  }
})
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
.workspace-header { align-items: flex-start; }
.workspace-subtitle { margin-top: 6px; color: #909399; font-size: 12px; }
.workspace-filters { display: flex; gap: 12px; align-items: center; }
.platform-overview-card { margin-bottom: 18px; padding: 18px 20px; border: 1px solid #ebeef5; border-radius: 12px; background: linear-gradient(180deg, #fbfdff 0%, #f6fafc 100%); }
.platform-overview-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; font-weight: 600; }
.platform-overview-meta { color: #909399; font-size: 12px; }
.platform-overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.platform-overview-item { padding: 14px 16px; border-radius: 10px; background: #fff; border: 1px solid #e8eef3; }
.platform-overview-item.warning { background: #fffaf0; border-color: #f7d8a8; }
.overview-label { margin-bottom: 8px; color: #606266; font-size: 12px; }
.overview-value { font-size: 24px; font-weight: 700; color: #1f4d78; }
.rule-summary-card { margin-top: 14px; padding: 14px 16px; border-radius: 10px; border: 1px dashed #c8d7e1; background: rgba(255, 255, 255, 0.75); }
.rule-summary-title { margin-bottom: 8px; color: #1f4d78; font-size: 13px; font-weight: 700; }
.rule-summary-list { display: grid; gap: 6px; color: #4f6474; font-size: 12px; line-height: 1.5; }
.workspace-layout { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }
.shop-list-panel { border-right: 1px solid #ebeef5; padding-right: 16px; }
.shop-list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-weight: 600; }
.shop-list-toolbar { display: grid; gap: 10px; margin-bottom: 12px; }
.shop-filter-block { display: grid; gap: 8px; }
.shop-filter-label { color: #606266; font-size: 12px; font-weight: 600; }
.shop-list-hints { display: flex; flex-direction: column; gap: 4px; color: #909399; font-size: 12px; }
.shop-list { display: flex; flex-direction: column; gap: 10px; max-height: 880px; overflow: auto; }
.shop-row { width: 100%; border: 1px solid #ebeef5; background: #fff; border-radius: 12px; padding: 14px; text-align: left; cursor: pointer; transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease; }
.shop-row:hover { border-color: #7db1c8; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(47, 122, 154, 0.08); }
.shop-row.active { border-color: #2f7a9a; background: #f0f7fb; box-shadow: inset 0 0 0 1px rgba(47, 122, 154, 0.08); }
.shop-row-top { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.shop-row-tags { display: inline-flex; gap: 6px; align-items: center; }
.shop-display-cell { line-height: 1.4; }
.shop-display-secondary { font-size: 12px; color: #909399; }
.shop-name { font-weight: 600; color: #303133; }
.shop-meta { color: #909399; font-size: 12px; }
.shop-submeta { margin-top: 6px; color: #606266; font-size: 12px; }
.shop-detail-panel { min-width: 0; }
.shop-detail-header { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.shop-detail-title { font-size: 18px; font-weight: 700; color: #303133; }
.shop-detail-meta { color: #909399; margin-top: 4px; }
.shop-display-input { display: flex; flex-direction: column; gap: 4px; }
.shop-detail-secondary { margin-left: 6px; }
.shop-detail-signals { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.shop-exception-card { margin-bottom: 16px; border-color: #f7d8a8; background: linear-gradient(180deg, #fffdf8 0%, #fff8eb 100%); }
.shop-next-step-card { margin-bottom: 16px; border-color: #b7d3f3; background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%); }
.shop-next-step-list { display: grid; gap: 10px; }
.shop-next-step-item { padding: 12px 14px; border-radius: 10px; border: 1px solid #c9dcf5; background: rgba(255, 255, 255, 0.88); }
.shop-next-step-title { font-weight: 600; color: #1f4d78; margin-bottom: 4px; }
.shop-next-step-desc { color: #4f6474; font-size: 13px; line-height: 1.5; }
.shop-exception-list { display: grid; gap: 10px; }
.shop-exception-item { padding: 12px 14px; border-radius: 10px; border: 1px solid #f3d19e; background: rgba(255, 255, 255, 0.8); }
.shop-exception-title { font-weight: 600; color: #ad6800; margin-bottom: 4px; }
.shop-exception-desc { color: #8c6d1f; font-size: 13px; line-height: 1.5; }
.shop-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.inner-card { border: none; box-shadow: none; }
.inner-toolbar { margin-bottom: 16px; }
.filter-form { margin-bottom: 16px; }
.section-alert { margin-bottom: 16px; }
.summary-grid { margin-bottom: 20px; }
.summary-item { height: 100%; padding: 20px; border-radius: 10px; background: #fafbfc; border: 1px solid #ebeef5; }
.summary-label { margin-bottom: 8px; color: #606266; font-size: 13px; }
.summary-value { font-size: 28px; font-weight: 700; }
.summary-value.revenue { color: #2f7a9a; }
.summary-value.cost { color: #d46b08; }
.summary-value.profit { color: #237804; }
@media (max-width: 960px) {
  .platform-overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workspace-layout { grid-template-columns: 1fr; }
  .shop-list-panel { border-right: none; padding-right: 0; }
  .workspace-filters { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .shop-detail-header { flex-direction: column; }
  .shop-detail-signals { justify-content: flex-start; }
}
</style>
