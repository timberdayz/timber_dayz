<template>
  <div class="financial-management">
    <div class="page-header">
      <h1>财务结算中心</h1>
      <p>先确认公司月结，再按平台切换店铺处理利润口径、跟投试算、跟投记录与结算台账。</p>
    </div>

    <el-alert
      class="page-alert"
      type="info"
      :closable="false"
      show-icon
      title="建议先确认利润基准、店铺提成、工资和跟投审批，再进行月度利润结算审批。"
    />

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
          <el-button type="primary" @click="loadMonthlySettlement" :loading="financeStore.monthlyProfitSettlement.loading">查询月结</el-button>
          <el-button @click="rebuildMonthlySettlement" :loading="financeStore.monthlyProfitSettlement.loading">重建月结</el-button>
          <el-button v-if="currentSettlementId" @click="saveMonthlyTargets" :loading="financeStore.monthlyProfitSettlement.loading">保存目标</el-button>
          <el-button v-if="currentSettlementId && monthlySummary?.status !== 'approved'" type="success" @click="approveMonthlySettlement">审批通过</el-button>
          <el-button v-if="currentSettlementId && monthlySummary?.status === 'approved'" type="warning" @click="reopenMonthlySettlement">回退草稿</el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="financeStore.monthlyProfitSettlement.error" type="error" :closable="false" :title="financeStore.monthlyProfitSettlement.error" class="section-alert" />
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

    <el-card class="section-card workspace-card">
      <template #header>
        <div class="card-header workspace-header">
          <div>
            <span>店铺工作区</span>
            <div class="workspace-subtitle">按平台查看已启用店铺，左侧选店，右侧完成单店利润口径、跟投试算和结算处理。</div>
          </div>
          <div class="workspace-filters">
            <el-date-picker v-model="selectedMonth" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" @change="handleMonthChange" />
            <el-select v-model="selectedPlatform" style="width: 140px" @change="handlePlatformChange">
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
          <div class="platform-overview-item">
            <div class="overview-label">平台店铺数</div>
            <div class="overview-value">{{ platformShopStats.total }}</div>
          </div>
          <div class="platform-overview-item">
            <div class="overview-label">可继续结算店铺</div>
            <div class="overview-value">{{ platformShopStats.canSettle }}</div>
          </div>
          <div class="platform-overview-item">
            <div class="overview-label">有跟投记录店铺</div>
            <div class="overview-value">{{ platformShopStats.withFollowInvestment }}</div>
          </div>
          <div class="platform-overview-item">
            <div class="overview-label">有结算台账店铺</div>
            <div class="overview-value">{{ platformShopStats.withSettlement }}</div>
          </div>
          <div class="platform-overview-item warning">
            <div class="overview-label">待补经营数据</div>
            <div class="overview-value">{{ platformShopStats.pendingData }}</div>
          </div>
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
              <el-radio-group v-model="shopFilterMode" size="small">
                <el-radio-button label="all">全部店铺</el-radio-button>
                <el-radio-button label="exception">只看异常店铺</el-radio-button>
                <el-radio-button label="pending">只看待补经营数据</el-radio-button>
              </el-radio-group>
            </div>
            <el-input
              v-model="shopKeyword"
              clearable
              placeholder="按店铺名称或店铺ID筛选"
            />
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
              @click="selectShop(shop)"
            >
              <div class="shop-row-top">
                <span class="shop-name">{{ shop.shop_name }}</span>
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
              <div class="shop-detail-meta">{{ selectedShop ? `${selectedShop.shop_name}（${selectedShop.shop_id}）` : '请先从左侧选择店铺' }}</div>
            </div>
            <div v-if="selectedShop" class="shop-detail-signals">
              <el-tag effect="plain" :type="financeStore.profitBasis.data ? 'success' : 'info'">{{ financeStore.profitBasis.data ? '利润口径已加载' : '待加载利润口径' }}</el-tag>
              <el-tag effect="plain" :type="financeStore.followInvestments.data.length ? 'success' : 'warning'">跟投记录 {{ financeStore.followInvestments.data.length }} 条</el-tag>
              <el-tag effect="plain" :type="financeStore.followInvestmentSettlements.data.length ? 'success' : 'info'">结算台账 {{ financeStore.followInvestmentSettlements.data.length }} 条</el-tag>
            </div>
          </div>

          <el-empty v-if="!selectedShop" description="请先从左侧店铺列表选择一个店铺" />
          <div v-else>
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
            <el-tabs v-model="activeShopTab" class="shop-tabs">
            <el-tab-pane label="店铺结算净利润口径" name="basis">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="profitBasisForm.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 140px" /></el-form-item>
                  <el-form-item label="店铺"><el-input :model-value="selectedShop?.shop_name || ''" disabled style="width: 220px" /></el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="loadProfitBasis" :disabled="!selectedShop" :loading="financeStore.profitBasis.loading">查询基准</el-button>
                    <el-button @click="rebuildProfitBasis" :disabled="!selectedShop" :loading="financeStore.profitBasis.loading">重算基准</el-button>
                  </el-form-item>
                </el-form>
                <el-alert v-if="financeStore.profitBasis.error" type="error" :closable="false" :title="financeStore.profitBasis.error" class="section-alert" />
                <el-row v-if="financeStore.profitBasis.data" :gutter="20" class="summary-grid">
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">订单利润</div><div class="summary-value revenue">{{ formatCurrency(financeStore.profitBasis.data.orders_profit_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">A类成本</div><div class="summary-value cost">{{ formatCurrency(financeStore.profitBasis.data.a_class_cost_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">B类成本</div><div class="summary-value cost">{{ formatCurrency(financeStore.profitBasis.data.b_class_cost_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="6"><div class="summary-item"><div class="summary-label">结算基准利润</div><div class="summary-value profit">{{ formatCurrency(financeStore.profitBasis.data.profit_basis_amount) }}</div></div></el-col>
                </el-row>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="跟投收益试算" name="trial">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="followInvestmentForm.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 140px" /></el-form-item>
                  <el-form-item label="店铺"><el-input :model-value="selectedShop?.shop_name || ''" disabled style="width: 220px" /></el-form-item>
                  <el-form-item label="分配比例"><el-input-number v-model="followInvestmentForm.distribution_ratio" :min="0" :max="1" :step="0.05" :precision="2" /></el-form-item>
                  <el-form-item><el-button type="primary" @click="runFollowInvestmentSettlement" :disabled="!selectedShop" :loading="financeStore.followInvestmentSettlement.loading">试算收益</el-button></el-form-item>
                </el-form>
                <el-alert v-if="financeStore.followInvestmentSettlement.error" type="error" :closable="false" :title="financeStore.followInvestmentSettlement.error" class="section-alert" />
                <el-row v-if="financeStore.followInvestmentSettlement.data?.settlement" :gutter="20" class="summary-grid">
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">结算基准利润</div><div class="summary-value profit">{{ formatCurrency(financeStore.followInvestmentSettlement.data.settlement.profit_basis_amount) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">分配比例</div><div class="summary-value">{{ formatPercentValue(financeStore.followInvestmentSettlement.data.settlement.distribution_ratio) }}</div></div></el-col>
                  <el-col :xs="24" :sm="12" :md="8"><div class="summary-item"><div class="summary-label">可分配收益</div><div class="summary-value profit">{{ formatCurrency(financeStore.followInvestmentSettlement.data.settlement.distributable_amount) }}</div></div></el-col>
                </el-row>
                <el-table :data="financeStore.followInvestmentSettlement.data?.details || []" v-loading="financeStore.followInvestmentSettlement.loading" stripe>
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
                <div class="card-header inner-toolbar"><span>当前店铺跟投记录</span><el-button type="primary" size="small" @click="openCreateFollowInvestment" :disabled="!selectedShop">新增跟投</el-button></div>
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="状态"><el-select v-model="followInvestmentQuery.status" clearable style="width: 140px"><el-option label="生效" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
                  <el-form-item><el-button @click="loadFollowInvestments" :disabled="!selectedShop" :loading="financeStore.followInvestments.loading">查询记录</el-button></el-form-item>
                </el-form>
                <el-table :data="financeStore.followInvestments.data" v-loading="financeStore.followInvestments.loading" stripe>
                  <el-table-column prop="id" label="ID" width="80" />
                  <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
                  <el-table-column prop="contribution_amount" label="本金" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.contribution_amount) }}</template></el-table-column>
                  <el-table-column prop="contribution_date" label="投入日期" width="120" />
                  <el-table-column prop="withdraw_date" label="退出日期" width="120" />
                  <el-table-column prop="status" label="状态" width="100" />
                  <el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><el-button link type="primary" size="small" @click="openEditFollowInvestment(row)">编辑</el-button><el-button link type="danger" size="small" @click="archiveFollowInvestment(row)">归档</el-button></template></el-table-column>
                </el-table>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="结算台账" name="ledger">
              <el-card class="inner-card">
                <el-form :inline="true" class="filter-form">
                  <el-form-item label="月份"><el-date-picker v-model="settlementQuery.period_month" type="month" value-format="YYYY-MM" format="YYYY-MM" style="width: 140px" /></el-form-item>
                  <el-form-item label="状态"><el-select v-model="settlementQuery.status" clearable style="width: 140px"><el-option label="草稿" value="draft" /><el-option label="已试算" value="calculated" /><el-option label="已审批" value="approved" /></el-select></el-form-item>
                  <el-form-item><el-button @click="loadFollowInvestmentSettlements" :disabled="!selectedShop" :loading="financeStore.followInvestmentSettlements.loading">查询台账</el-button></el-form-item>
                </el-form>
                <el-table :data="financeStore.followInvestmentSettlements.data" v-loading="financeStore.followInvestmentSettlements.loading" stripe>
                  <el-table-column prop="id" label="结算ID" width="100" />
                  <el-table-column prop="period_month" label="月份" width="120" />
                  <el-table-column prop="profit_basis_amount" label="结算基准利润" width="160" align="right"><template #default="{ row }">{{ formatCurrency(row.profit_basis_amount) }}</template></el-table-column>
                  <el-table-column prop="distribution_ratio" label="分配比例" width="120" align="right"><template #default="{ row }">{{ formatPercentValue(row.distribution_ratio) }}</template></el-table-column>
                  <el-table-column prop="distributable_amount" label="可分配收益" width="160" align="right"><template #default="{ row }">{{ formatCurrency(row.distributable_amount) }}</template></el-table-column>
                  <el-table-column prop="status" label="状态" width="100" />
                  <el-table-column prop="approved_by_name" label="审核人" width="120" />
                  <el-table-column prop="approved_at" label="审核时间" width="180"><template #default="{ row }">{{ formatDateTime(row.approved_at) }}</template></el-table-column>
                  <el-table-column label="操作" width="180" fixed="right"><template #default="{ row }"><el-button link type="info" size="small" @click="viewSettlementDetails(row)">查看明细</el-button><el-button v-if="row.status !== 'approved'" link type="success" size="small" @click="approveFollowInvestment(row)">审批通过</el-button><el-button v-if="row.status === 'approved'" link type="warning" size="small" @click="reopenFollowInvestment(row)">回退审批</el-button></template></el-table-column>
                </el-table>
              </el-card>
            </el-tab-pane>
            </el-tabs>
          </div>
        </section>
      </div>
    </el-card>

    <el-dialog v-model="showFollowInvestmentDialog" :title="followInvestmentDialogMode === 'create' ? '新增跟投' : '编辑跟投'" width="600px">
      <el-form :model="followInvestmentRecordForm" label-width="120px">
        <el-form-item label="投资人ID"><el-input-number v-model="followInvestmentRecordForm.investor_user_id" :min="1" /></el-form-item>
        <el-form-item label="平台"><el-input :model-value="selectedPlatformLabel" disabled style="width: 180px" /></el-form-item>
        <el-form-item label="店铺"><el-input :model-value="selectedShop?.shop_name || ''" disabled /></el-form-item>
        <el-form-item label="本金"><el-input-number v-model="followInvestmentRecordForm.contribution_amount" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="投入日期"><el-date-picker v-model="followInvestmentRecordForm.contribution_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="退出日期"><el-date-picker v-model="followInvestmentRecordForm.withdraw_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="状态"><el-select v-model="followInvestmentRecordForm.status" style="width: 180px"><el-option label="生效" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
        <el-form-item label="备注"><el-input v-model="followInvestmentRecordForm.remark" type="textarea" rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showFollowInvestmentDialog = false">取消</el-button><el-button type="primary" @click="submitFollowInvestmentRecord" :loading="submitting">保存</el-button></template>
    </el-dialog>

    <el-drawer v-model="showSettlementDetailsDrawer" title="结算明细" size="50%">
      <el-alert v-if="financeStore.followInvestmentSettlementDetails.error" type="error" :closable="false" :title="financeStore.followInvestmentSettlementDetails.error" class="section-alert" />
      <el-table :data="financeStore.followInvestmentSettlementDetails.data" v-loading="financeStore.followInvestmentSettlementDetails.loading" stripe>
        <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
        <el-table-column prop="investor_name" label="投资人姓名" width="140" />
        <el-table-column prop="contribution_amount_snapshot" label="本金快照" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.contribution_amount_snapshot) }}</template></el-table-column>
        <el-table-column prop="occupied_days" label="占用天数" width="100" align="right" />
        <el-table-column prop="weighted_capital" label="加权资金" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.weighted_capital) }}</template></el-table-column>
        <el-table-column prop="share_ratio" label="分配占比" width="120" align="right"><template #default="{ row }">{{ formatPercentValue(row.share_ratio) }}</template></el-table-column>
        <el-table-column prop="estimated_income" label="预计收益" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.estimated_income) }}</template></el-table-column>
        <el-table-column prop="approved_income" label="已批准收益" width="140" align="right"><template #default="{ row }">{{ formatCurrency(row.approved_income) }}</template></el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>
<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import financeApi from '@/api/finance'
import { useFinanceStore } from '@/stores/finance'

const financeStore = useFinanceStore()
const currentMonth = new Date().toISOString().slice(0, 7)
const activeTab = ref('monthly')
const activeShopTab = ref('basis')
const selectedMonth = ref(currentMonth)
const selectedPlatform = ref('shopee')
const shopKeyword = ref('')
const shopFilterMode = ref('all')
const platformLabels = { shopee: 'Shopee', tiktok: 'TikTok', amazon: 'Amazon', miaoshou: '妙手ERP' }
const allShops = ref([])
const selectedShop = ref(null)
const platformFollowInvestments = ref([])
const platformSettlementRows = ref([])
const monthlyForm = ref({ period_month: currentMonth, personnel_target_ratio: 0.3, follow_target_ratio: 0.2, company_target_ratio: 0.5, adjustment_amount: 0, adjustment_reason: '' })
const profitBasisForm = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '' })
const followInvestmentForm = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '', distribution_ratio: 0.4 })
const followInvestmentQuery = ref({ platform_code: 'shopee', shop_id: '', status: '' })
const settlementQuery = ref({ period_month: currentMonth, platform_code: 'shopee', shop_id: '', status: '' })
const showFollowInvestmentDialog = ref(false)
const showSettlementDetailsDrawer = ref(false)
const followInvestmentDialogMode = ref('create')
const editingFollowInvestmentId = ref(null)
const submitting = ref(false)
const followInvestmentRecordForm = ref({ investor_user_id: null, platform_code: 'shopee', shop_id: '', contribution_amount: 0, contribution_date: new Date().toISOString().split('T')[0], withdraw_date: '', status: 'active', remark: '' })
const monthlySummary = computed(() => financeStore.monthlyProfitSettlement.data?.summary || null)
const monthlyPersonnelDetails = computed(() => financeStore.monthlyProfitSettlement.data?.personnel_details || [])
const currentSettlementId = computed(() => monthlySummary.value?.id || null)
const showSettlementDifferenceWarning = computed(() => !!monthlySummary.value && (Math.abs(Number(monthlySummary.value.difference_amount || 0)) > 3000 || Math.abs(Number(monthlySummary.value.difference_ratio || 0)) > 0.01))
const selectedPlatformLabel = computed(() => platformLabels[selectedPlatform.value] || selectedPlatform.value)
const filteredShops = computed(() => {
  const keyword = shopKeyword.value.trim().toLowerCase()
  return allShops.value.filter((shop) => {
    if (shop.platform_code !== selectedPlatform.value) return false
    const status = getShopStatus(shop)
    if (shopFilterMode.value === 'exception' && !status.hasException) return false
    if (shopFilterMode.value === 'pending' && !status.pendingData) return false
    if (!keyword) return true
    return `${shop.shop_name || ''} ${shop.shop_id || ''}`.toLowerCase().includes(keyword)
  })
})
const platformShopStats = computed(() => {
  const total = filteredShops.value.length
  const canSettle = filteredShops.value.filter((shop) => {
    const status = getShopStatus(shop)
    return status.canSettle
  }).length
  const withFollowInvestment = filteredShops.value.filter((shop) => getShopStatus(shop).hasFollowInvestment).length
  const withSettlement = filteredShops.value.filter((shop) => getShopStatus(shop).hasSettlement).length
  const pendingData = filteredShops.value.filter((shop) => {
    const status = getShopStatus(shop)
    return status.pendingData
  }).length

  return { total, canSettle, withFollowInvestment, withSettlement, pendingData }
})
const shopExceptionItems = computed(() => {
  if (!selectedShop.value) return []
  const status = getShopStatus(selectedShop.value)
  const items = []

  if (status.pendingData) {
    items.push({
      key: 'pending-data',
      title: '缺少经营沉淀数据',
      description: '当前店铺既没有跟投记录，也没有当月结算台账，建议先核对利润口径和跟投数据。'
    })
  }

  if (!financeStore.profitBasis.data) {
    items.push({
      key: 'profit-basis',
      title: '尚未加载利润口径',
      description: '请先查询或重算店铺结算净利润口径，再继续后续试算和审批。'
    })
  }

  if (!status.hasSettlement) {
    items.push({
      key: 'settlement-ledger',
      title: '缺少当月结算台账',
      description: '当前月份还没有结算台账，建议先完成跟投收益试算或检查月度结算生成流程。'
    })
  }

  return items
})

const syncMonthlyForm = (payload) => { const summary = payload?.summary; if (!summary) return; const firstAdjustment = payload?.adjustments?.[0] || null; monthlyForm.value = { period_month: summary.period_month || currentMonth, personnel_target_ratio: Number(summary.personnel_target_ratio ?? 0.3), follow_target_ratio: Number(summary.follow_target_ratio ?? 0.2), company_target_ratio: Number(summary.company_target_ratio ?? 0.5), adjustment_amount: Number(summary.adjustment_amount ?? 0), adjustment_reason: firstAdjustment?.reason || '' } }
const syncSelectedShopForms = () => {
  if (!selectedShop.value) return
  const shopId = selectedShop.value.shop_id
  profitBasisForm.value = { ...profitBasisForm.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
  followInvestmentForm.value = { ...followInvestmentForm.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
  followInvestmentQuery.value = { ...followInvestmentQuery.value, platform_code: selectedPlatform.value, shop_id: shopId }
  settlementQuery.value = { ...settlementQuery.value, period_month: selectedMonth.value, platform_code: selectedPlatform.value, shop_id: shopId }
  followInvestmentRecordForm.value = { ...followInvestmentRecordForm.value, platform_code: selectedPlatform.value, shop_id: shopId }
}
const loadShopList = async () => { const response = await api.getTargetShops(); allShops.value = (response?.data || response || []).filter((shop) => shop.platform_code); if (!selectedShop.value || selectedShop.value.platform_code !== selectedPlatform.value) { selectedShop.value = filteredShops.value[0] || null; syncSelectedShopForms() } }
const loadPlatformShopSignals = async () => {
  const [followResponse, settlementResponse] = await Promise.all([
    financeApi.getFollowInvestments({ platform_code: selectedPlatform.value }),
    financeApi.getFollowInvestmentSettlements({ platform_code: selectedPlatform.value, period_month: selectedMonth.value })
  ])
  platformFollowInvestments.value = followResponse?.data || followResponse || []
  platformSettlementRows.value = settlementResponse?.data || settlementResponse || []
}
const selectShop = (shop) => { selectedShop.value = shop; syncSelectedShopForms(); financeStore.followInvestmentSettlement.data = { settlement: null, details: [] }; financeStore.profitBasis.data = null; loadProfitBasis(); loadFollowInvestments(); loadFollowInvestmentSettlements() }
const handlePlatformChange = async () => { shopKeyword.value = ''; shopFilterMode.value = 'all'; selectedShop.value = filteredShops.value[0] || null; syncSelectedShopForms(); await loadPlatformShopSignals(); if (selectedShop.value) { loadProfitBasis(); loadFollowInvestments(); loadFollowInvestmentSettlements() } }
const handleMonthChange = async () => { monthlyForm.value.period_month = selectedMonth.value; syncSelectedShopForms(); await loadMonthlySettlement(); await loadPlatformShopSignals(); if (selectedShop.value) { await loadProfitBasis(); await loadFollowInvestments(); await loadFollowInvestmentSettlements() } }
const loadMonthlySettlement = async () => { await financeStore.fetchMonthlyProfitSettlement({ period_month: monthlyForm.value.period_month }); syncMonthlyForm(financeStore.monthlyProfitSettlement.data) }
const rebuildMonthlySettlement = async () => { try { await financeStore.rebuildMonthlyProfitSettlement({ period_month: monthlyForm.value.period_month, personnel_target_ratio: monthlyForm.value.personnel_target_ratio, follow_target_ratio: monthlyForm.value.follow_target_ratio, company_target_ratio: monthlyForm.value.company_target_ratio, adjustment_amount: monthlyForm.value.adjustment_amount, adjustment_reason: monthlyForm.value.adjustment_reason || null }); syncMonthlyForm(financeStore.monthlyProfitSettlement.data); ElMessage.success('月度利润结算已重建') } catch (error) { ElMessage.error('重建月度利润结算失败: ' + error.message) } }
const saveMonthlyTargets = async () => { if (!currentSettlementId.value) return ElMessage.warning('请先查询或重建月结'); try { await financeStore.updateMonthlyProfitSettlementTargets(currentSettlementId.value, { personnel_target_ratio: monthlyForm.value.personnel_target_ratio, follow_target_ratio: monthlyForm.value.follow_target_ratio, company_target_ratio: monthlyForm.value.company_target_ratio, adjustment_amount: monthlyForm.value.adjustment_amount, adjustment_reason: monthlyForm.value.adjustment_reason || null }); syncMonthlyForm(financeStore.monthlyProfitSettlement.data); ElMessage.success('月度目标比例已保存') } catch (error) { ElMessage.error('保存月度目标比例失败: ' + error.message) } }
const approveMonthlySettlement = async () => { if (!currentSettlementId.value) return ElMessage.warning('请先查询月结'); try { await financeStore.approveMonthlyProfitSettlement(currentSettlementId.value); ElMessage.success('月度利润结算已审批'); await loadMonthlySettlement() } catch (error) { ElMessage.error('审批月度利润结算失败: ' + error.message) } }
const reopenMonthlySettlement = async () => { if (!currentSettlementId.value) return ElMessage.warning('请先查询月结'); try { await financeStore.reopenMonthlyProfitSettlement(currentSettlementId.value); ElMessage.success('月度利润结算已回退到草稿'); await loadMonthlySettlement() } catch (error) { ElMessage.error('回退月度利润结算失败: ' + error.message) } }
const loadProfitBasis = async () => { if (!selectedShop.value) return; await financeStore.fetchProfitBasis({ period_month: profitBasisForm.value.period_month, platform_code: profitBasisForm.value.platform_code, shop_id: profitBasisForm.value.shop_id }) }
const rebuildProfitBasis = async () => { if (!selectedShop.value) return; try { await financeStore.rebuildProfitBasis({ period_month: profitBasisForm.value.period_month, platform_code: profitBasisForm.value.platform_code, shop_id: profitBasisForm.value.shop_id, basis_version: 'A_ONLY_V1' }); ElMessage.success('利润分配基准已重算') } catch (error) { ElMessage.error('重算利润基准失败: ' + error.message) } }
const runFollowInvestmentSettlement = async () => { if (!selectedShop.value) return; try { await financeStore.calculateFollowInvestmentSettlement({ period_month: followInvestmentForm.value.period_month, platform_code: followInvestmentForm.value.platform_code, shop_id: followInvestmentForm.value.shop_id, distribution_ratio: followInvestmentForm.value.distribution_ratio }); await loadPlatformShopSignals(); ElMessage.success('跟投收益试算完成') } catch (error) { ElMessage.error('跟投收益试算失败: ' + error.message) } }
const loadFollowInvestments = async () => { if (!selectedShop.value) return; await financeStore.fetchFollowInvestments({ period_month: selectedMonth.value || undefined, platform_code: followInvestmentQuery.value.platform_code || undefined, shop_id: followInvestmentQuery.value.shop_id || undefined, status: followInvestmentQuery.value.status || undefined }) }
const loadFollowInvestmentSettlements = async () => { if (!selectedShop.value) return; await financeStore.fetchFollowInvestmentSettlements({ period_month: settlementQuery.value.period_month || undefined, platform_code: settlementQuery.value.platform_code || undefined, shop_id: settlementQuery.value.shop_id || undefined, status: settlementQuery.value.status || undefined }) }
const viewSettlementDetails = async (row) => { await financeStore.fetchFollowInvestmentSettlementDetails(row.id); showSettlementDetailsDrawer.value = true }
const resetFollowInvestmentRecordForm = () => { followInvestmentRecordForm.value = { investor_user_id: null, platform_code: selectedPlatform.value, shop_id: selectedShop.value?.shop_id || '', contribution_amount: 0, contribution_date: new Date().toISOString().split('T')[0], withdraw_date: '', status: 'active', remark: '' }; editingFollowInvestmentId.value = null }
const openCreateFollowInvestment = () => { followInvestmentDialogMode.value = 'create'; resetFollowInvestmentRecordForm(); showFollowInvestmentDialog.value = true }
const openEditFollowInvestment = (row) => { followInvestmentDialogMode.value = 'edit'; editingFollowInvestmentId.value = row.id; followInvestmentRecordForm.value = { investor_user_id: row.investor_user_id, platform_code: row.platform_code, shop_id: row.shop_id, contribution_amount: row.contribution_amount, contribution_date: row.contribution_date, withdraw_date: row.withdraw_date || '', status: row.status, remark: row.remark || '' }; showFollowInvestmentDialog.value = true }
const submitFollowInvestmentRecord = async () => { try { submitting.value = true; const payload = { ...followInvestmentRecordForm.value, withdraw_date: followInvestmentRecordForm.value.withdraw_date || null }; if (followInvestmentDialogMode.value === 'create') { await financeStore.createFollowInvestment(payload) } else { await financeStore.updateFollowInvestment(editingFollowInvestmentId.value, payload, { platform_code: followInvestmentQuery.value.platform_code || undefined, shop_id: followInvestmentQuery.value.shop_id || undefined, status: followInvestmentQuery.value.status || undefined }) } await loadPlatformShopSignals(); ElMessage.success('跟投记录已保存'); showFollowInvestmentDialog.value = false; resetFollowInvestmentRecordForm(); await loadFollowInvestments() } catch (error) { ElMessage.error('保存跟投记录失败: ' + error.message) } finally { submitting.value = false } }
const archiveFollowInvestment = async (row) => { try { await ElMessageBox.confirm(`确认归档跟投记录 #${row.id} 吗？`, '归档跟投记录', { confirmButtonText: '确认归档', cancelButtonText: '取消', type: 'warning' }); await financeStore.archiveFollowInvestment(row.id, { platform_code: followInvestmentQuery.value.platform_code || undefined, shop_id: followInvestmentQuery.value.shop_id || undefined, status: followInvestmentQuery.value.status || undefined }); await loadPlatformShopSignals(); ElMessage.success('跟投记录已归档') } catch (error) { if (error !== 'cancel') ElMessage.error('归档失败: ' + (error.message || error)) } }
const approveFollowInvestment = async (row) => { try { await financeStore.approveFollowInvestmentSettlement(row.id); await loadPlatformShopSignals(); ElMessage.success('结算已审批'); await loadFollowInvestmentSettlements() } catch (error) { ElMessage.error('审批失败: ' + error.message) } }
const reopenFollowInvestment = async (row) => { try { await financeStore.reopenFollowInvestmentSettlement(row.id); await loadPlatformShopSignals(); ElMessage.success('结算已回退'); await loadFollowInvestmentSettlements() } catch (error) { ElMessage.error('回退失败: ' + error.message) } }
const getShopStatus = (shop) => {
  const hasFollowInvestment = platformFollowInvestments.value.some((item) => item.shop_id === shop.shop_id)
  const hasSettlement = platformSettlementRows.value.some((item) => item.shop_id === shop.shop_id)
  const canSettle = hasFollowInvestment && hasSettlement
  const pendingData = !hasFollowInvestment && !hasSettlement
  const hasException = pendingData || !hasSettlement
  return {
    hasFollowInvestment,
    hasSettlement,
    canSettle,
    pendingData,
    hasException
  }
}
const formatRatioInput = (value) => {
  if (value == null || value === undefined || value === '') return ''
  return `${(Number(value) * 100).toFixed(2)}%`
}
const parseRatioInput = (value) => {
  if (value == null || value === undefined || value === '') return 0
  const numeric = Number(String(value).replace(/[%\s]/g, ''))
  if (Number.isNaN(numeric)) return 0
  return numeric / 100
}
const formatCurrency = (num) => (!num && num !== 0) ? '0.00' : new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num)
const formatPercentValue = (num) => (num == null || num === undefined) ? '-' : `${(Number(num) * 100).toFixed(2)}%`
const formatDateTime = (dateTime) => (!dateTime ? '-' : new Date(dateTime).toLocaleString('zh-CN'))
onMounted(async () => { await loadShopList(); await loadPlatformShopSignals(); monthlyForm.value.period_month = selectedMonth.value; await loadMonthlySettlement(); if (selectedShop.value) { await loadProfitBasis(); await loadFollowInvestments(); await loadFollowInvestmentSettlements() } })
</script>

<style scoped>
.financial-management { padding: 20px; background: #f3f5f7; min-height: 100vh; }
.page-header { margin-bottom: 20px; padding: 24px 28px; border-radius: 14px; color: white; background: linear-gradient(135deg, #1f4d78 0%, #2f7a9a 55%, #5aa0a8 100%); }
.page-header h1 { margin: 0 0 8px; font-size: 30px; font-weight: 700; }
.page-header p { margin: 0; opacity: 0.9; }
.page-alert { margin-bottom: 20px; }
.finance-tabs { background: white; padding: 20px; border-radius: 12px; }
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
.shop-name { font-weight: 600; color: #303133; }
.shop-meta { color: #909399; font-size: 12px; }
.shop-submeta { margin-top: 6px; color: #606266; font-size: 12px; }
.shop-detail-panel { min-width: 0; }
.shop-detail-header { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.shop-detail-title { font-size: 18px; font-weight: 700; color: #303133; }
.shop-detail-meta { color: #909399; margin-top: 4px; }
.shop-detail-signals { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.shop-exception-card { margin-bottom: 16px; border-color: #f7d8a8; background: linear-gradient(180deg, #fffdf8 0%, #fff8eb 100%); }
.shop-exception-list { display: grid; gap: 10px; }
.shop-exception-item { padding: 12px 14px; border-radius: 10px; border: 1px solid #f3d19e; background: rgba(255, 255, 255, 0.8); }
.shop-exception-title { font-weight: 600; color: #ad6800; margin-bottom: 4px; }
.shop-exception-desc { color: #8c6d1f; font-size: 13px; line-height: 1.5; }
.shop-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.inner-card { border: none; box-shadow: none; }
.inner-toolbar { margin-bottom: 16px; }
@media (max-width: 960px) { .platform-overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .workspace-layout { grid-template-columns: 1fr; } .shop-list-panel { border-right: none; padding-right: 0; } .workspace-filters { width: 100%; justify-content: flex-start; flex-wrap: wrap; } .shop-detail-header { flex-direction: column; } .shop-detail-signals { justify-content: flex-start; } }
@media (max-width: 768px) { .financial-management { padding: 12px; } .page-header { padding: 20px; } .page-header h1 { font-size: 24px; } }
</style>
