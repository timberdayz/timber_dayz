<template>
  <div class="financial-management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>💰 财务管理中心</h1>
      <p>应收管理 • 收款跟踪 • 利润分析</p>
    </div>

    <!-- 筛选器 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            @change="handleDateChange"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="全部平台" clearable @change="handleFilterChange">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable @change="handleFilterChange">
            <el-option label="待收款" value="pending" />
            <el-option label="已收款" value="paid" />
            <el-option label="已逾期" value="overdue" />
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="refreshData" :loading="financeStore.isLoading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 财务统计卡片 -->
    <el-row :gutter="20" class="stats-section">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card" v-loading="financeStore.overview.loading">
          <div class="stat-icon ar-icon">
            <el-icon><Money /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">应收账款总额 (¥)</div>
            <div class="stat-value">{{ formatCurrency(financeStore.overview.data.totalAR) }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card" v-loading="financeStore.overview.loading">
          <div class="stat-icon received-icon">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">已收款 (¥)</div>
            <div class="stat-value">{{ formatCurrency(financeStore.overview.data.totalReceived) }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card warning" v-loading="financeStore.overview.loading">
          <div class="stat-icon outstanding-icon">
            <el-icon><Clock /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">未收款 (¥)</div>
            <div class="stat-value">{{ formatCurrency(financeStore.overview.data.totalOutstanding) }}</div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card danger" v-loading="financeStore.overview.loading">
          <div class="stat-icon overdue-icon">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">逾期金额 (¥)</div>
            <div class="stat-value">{{ formatCurrency(financeStore.overview.data.overdueAmount) }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- Tab切换 -->
    <el-tabs v-model="activeTab" class="finance-tabs">
      <!-- 应收账款 -->
      <el-tab-pane label="应收账款" name="ar">
        <el-table 
          :data="financeStore.accountsReceivable.data" 
          v-loading="financeStore.accountsReceivable.loading"
          stripe
        >
          <el-table-column prop="order_id" label="订单号" width="150" />
          <el-table-column prop="platform_code" label="平台" width="100">
            <template #default="{ row }">
              <el-tag :type="getPlatformType(row.platform_code)">
                {{ row.platform_code }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="shop_id" label="店铺" width="120" />
          <el-table-column prop="ar_amount_cny" label="应收金额 (¥)" width="120" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.ar_amount_cny) }}
            </template>
          </el-table-column>
          <el-table-column prop="received_amount_cny" label="已收 (¥)" width="120" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.received_amount_cny) }}
            </template>
          </el-table-column>
          <el-table-column prop="outstanding_amount_cny" label="未收 (¥)" width="120" align="right">
            <template #default="{ row }">
              <span :class="row.outstanding_amount_cny > 0 ? 'amount-outstanding' : ''">
                {{ formatCurrency(row.outstanding_amount_cny) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="invoice_date" label="开票日期" width="120" />
          <el-table-column prop="due_date" label="到期日期" width="120" />
          <el-table-column prop="ar_status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getARStatusType(row.ar_status)">
                {{ getARStatusText(row.ar_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="逾期" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_overdue" type="danger">
                {{ row.overdue_days }}天
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="recordPayment(row)">
                记录收款
              </el-button>
              <el-button link type="info" size="small" @click="viewARDetail(row)">
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="arPage"
            :total="financeStore.accountsReceivable.total"
            :page-size="20"
            layout="total, prev, pager, next"
            @current-change="handleARPageChange"
          />
        </div>
      </el-tab-pane>

      <!-- 收款记录 -->
      <el-tab-pane label="收款记录" name="payment">
        <el-table 
          :data="financeStore.paymentReceipts.data" 
          v-loading="financeStore.paymentReceipts.loading"
          stripe
        >
          <el-table-column prop="receipt_date" label="收款日期" width="120" />
          <el-table-column prop="ar_id" label="应收账款ID" width="120" />
          <el-table-column prop="receipt_amount_cny" label="收款金额 (¥)" width="150" align="right">
            <template #default="{ row }">
              <span class="amount-received">{{ formatCurrency(row.receipt_amount_cny) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="payment_method" label="收款方式" width="120">
            <template #default="{ row }">
              <el-tag>{{ getPaymentMethodText(row.payment_method) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="bank_account" label="银行账户" width="200" />
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="paymentPage"
            :total="financeStore.paymentReceipts.total"
            :page-size="20"
            layout="total, prev, pager, next"
            @current-change="handlePaymentPageChange"
          />
        </div>
      </el-tab-pane>

      <!-- 费用管理 -->
      <el-tab-pane label="费用管理" name="expense">
        <el-table 
          :data="financeStore.expenses.data" 
          v-loading="financeStore.expenses.loading"
          stripe
        >
          <el-table-column prop="expense_date" label="费用日期" width="120" />
          <el-table-column prop="platform_code" label="平台" width="100">
            <template #default="{ row }">
              <el-tag :type="getPlatformType(row.platform_code)">
                {{ row.platform_code }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="shop_id" label="店铺" width="120" />
          <el-table-column prop="expense_type" label="费用类型" width="120">
            <template #default="{ row }">
              <el-tag>{{ getExpenseTypeText(row.expense_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="amount_cny" label="金额 (¥)" width="150" align="right">
            <template #default="{ row }">
              <span class="expense-amount">{{ formatCurrency(row.amount_cny) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="order_id" label="关联订单" width="150" />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        </el-table>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="expensePage"
            :total="financeStore.expenses.total"
            :page-size="20"
            layout="total, prev, pager, next"
            @current-change="handleExpensePageChange"
          />
        </div>
      </el-tab-pane>

      <!-- 利润报表 -->
      <el-tab-pane label="利润报表" name="profit">
        <div class="profit-summary" v-loading="financeStore.profitReport.loading">
          <el-row :gutter="20">
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">总营收 (¥)</div>
                <div class="summary-value revenue">{{ formatCurrency(financeStore.profitReport.data.totalRevenue) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">总成本 (¥)</div>
                <div class="summary-value cost">{{ formatCurrency(financeStore.profitReport.data.totalCost) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">净利润 (¥)</div>
                <div class="summary-value profit">{{ formatCurrency(financeStore.profitReport.data.netProfit) }}</div>
              </div>
            </el-col>
          </el-row>
        </div>

        <el-table 
          :data="financeStore.profitReport.data.details || []"
          v-loading="financeStore.profitReport.loading"
          stripe
          show-summary
          :summary-method="getSummaries"
        >
          <el-table-column prop="date" label="日期" width="120" />
          <el-table-column prop="platform_code" label="平台" width="100" />
          <el-table-column prop="revenue_cny" label="营收 (¥)" width="150" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.revenue_cny) }}
            </template>
          </el-table-column>
          <el-table-column prop="cost_cny" label="成本 (¥)" width="150" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.cost_cny) }}
            </template>
          </el-table-column>
          <el-table-column prop="expense_cny" label="费用 (¥)" width="150" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.expense_cny) }}
            </template>
          </el-table-column>
          <el-table-column prop="gross_profit_cny" label="毛利 (¥)" width="150" align="right">
            <template #default="{ row }">
              <span class="profit-positive">{{ formatCurrency(row.gross_profit_cny) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="net_profit_cny" label="净利 (¥)" width="150" align="right">
            <template #default="{ row }">
              <span :class="row.net_profit_cny >= 0 ? 'profit-positive' : 'profit-negative'">
                {{ formatCurrency(row.net_profit_cny) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="profit_margin" label="利润率" width="100" align="right">
            <template #default="{ row }">
              <el-tag :type="getProfitMarginType(row.profit_margin)">
                {{ row.profit_margin }}%
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="利润分配基准" name="profit-basis">
        <el-card class="profit-summary">
          <template #header>
            <div class="card-header">
              <span>统一利润分配基准</span>
              <el-tag type="info">profit_basis_amount</el-tag>
            </div>
          </template>

          <el-form :inline="true" class="filter-form">
            <el-form-item label="月份">
              <el-date-picker
                v-model="profitBasisForm.period_month"
                type="month"
                value-format="YYYY-MM"
                format="YYYY-MM"
                style="width: 140px"
              />
            </el-form-item>
            <el-form-item label="平台">
              <el-select v-model="profitBasisForm.platform_code" style="width: 140px">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            <el-form-item label="店铺ID">
              <el-input v-model="profitBasisForm.shop_id" placeholder="请输入店铺ID" style="width: 180px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadProfitBasis" :loading="financeStore.profitBasis.loading">
                查询基准
              </el-button>
              <el-button @click="rebuildProfitBasis" :loading="financeStore.profitBasis.loading">
                重算基准
              </el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="financeStore.profitBasis.error"
            type="error"
            :closable="false"
            :title="financeStore.profitBasis.error"
            style="margin-bottom: 16px;"
          />

          <el-row v-if="financeStore.profitBasis.data" :gutter="20">
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">订单利润</div>
                <div class="summary-value revenue">{{ formatCurrency(financeStore.profitBasis.data.orders_profit_amount) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">A类成本</div>
                <div class="summary-value cost">{{ formatCurrency(financeStore.profitBasis.data.a_class_cost_amount) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">B类成本</div>
                <div class="summary-value cost">{{ formatCurrency(financeStore.profitBasis.data.b_class_cost_amount) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">结算基准利润</div>
                <div class="summary-value profit">{{ formatCurrency(financeStore.profitBasis.data.profit_basis_amount) }}</div>
              </div>
            </el-col>
          </el-row>
        </el-card>

        <el-card class="profit-summary" style="margin-top: 20px;">
          <template #header>
            <div class="card-header">
              <span>跟投收益试算</span>
            </div>
          </template>

          <el-form :inline="true" class="filter-form">
            <el-form-item label="月份">
              <el-date-picker
                v-model="followInvestmentForm.period_month"
                type="month"
                value-format="YYYY-MM"
                format="YYYY-MM"
                style="width: 140px"
              />
            </el-form-item>
            <el-form-item label="平台">
              <el-select v-model="followInvestmentForm.platform_code" style="width: 140px">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            <el-form-item label="店铺ID">
              <el-input v-model="followInvestmentForm.shop_id" placeholder="请输入店铺ID" style="width: 180px" />
            </el-form-item>
            <el-form-item label="分配比例">
              <el-input-number v-model="followInvestmentForm.distribution_ratio" :min="0" :max="1" :step="0.05" :precision="2" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="runFollowInvestmentSettlement" :loading="financeStore.followInvestmentSettlement.loading">
                试算收益
              </el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="financeStore.followInvestmentSettlement.error"
            type="error"
            :closable="false"
            :title="financeStore.followInvestmentSettlement.error"
            style="margin-bottom: 16px;"
          />

          <el-row v-if="financeStore.followInvestmentSettlement.data?.settlement" :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">结算基准利润</div>
                <div class="summary-value profit">{{ formatCurrency(financeStore.followInvestmentSettlement.data.settlement.profit_basis_amount) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">分配比例</div>
                <div class="summary-value">{{ formatPercentValue(financeStore.followInvestmentSettlement.data.settlement.distribution_ratio) }}</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="summary-item">
                <div class="summary-label">可分配收益</div>
                <div class="summary-value profit">{{ formatCurrency(financeStore.followInvestmentSettlement.data.settlement.distributable_amount) }}</div>
              </div>
            </el-col>
          </el-row>

          <el-table
            :data="financeStore.followInvestmentSettlement.data?.details || []"
            v-loading="financeStore.followInvestmentSettlement.loading"
            stripe
          >
            <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
            <el-table-column prop="contribution_amount_snapshot" label="本金快照 (楼)" width="150" align="right">
              <template #default="{ row }">{{ formatCurrency(row.contribution_amount_snapshot) }}</template>
            </el-table-column>
            <el-table-column prop="occupied_days" label="占用天数" width="100" align="right" />
            <el-table-column prop="weighted_capital" label="加权资金" width="150" align="right">
              <template #default="{ row }">{{ formatCurrency(row.weighted_capital) }}</template>
            </el-table-column>
            <el-table-column prop="share_ratio" label="分配占比" width="120" align="right">
              <template #default="{ row }">{{ formatPercentValue(row.share_ratio) }}</template>
            </el-table-column>
            <el-table-column prop="estimated_income" label="预计收益 (楼)" width="150" align="right">
              <template #default="{ row }">
                <span class="profit-positive">{{ formatCurrency(row.estimated_income) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="profit-summary" style="margin-top: 20px;">
          <template #header>
            <div class="card-header">
              <span>跟投记录</span>
              <el-button type="primary" size="small" @click="openCreateFollowInvestment">
                新增跟投
              </el-button>
            </div>
          </template>

          <el-form :inline="true" class="filter-form">
            <el-form-item label="平台">
              <el-select v-model="followInvestmentQuery.platform_code" style="width: 140px">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            <el-form-item label="店铺ID">
              <el-input v-model="followInvestmentQuery.shop_id" placeholder="请输入店铺ID" style="width: 180px" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="followInvestmentQuery.status" clearable style="width: 140px">
                <el-option label="生效" value="active" />
                <el-option label="停用" value="inactive" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button @click="loadFollowInvestments" :loading="financeStore.followInvestments.loading">
                查询记录
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="financeStore.followInvestments.data" v-loading="financeStore.followInvestments.loading" stripe>
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
            <el-table-column prop="platform_code" label="平台" width="120" />
            <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
            <el-table-column prop="contribution_amount" label="本金 (楼)" width="140" align="right">
              <template #default="{ row }">{{ formatCurrency(row.contribution_amount) }}</template>
            </el-table-column>
            <el-table-column prop="contribution_date" label="投入日期" width="120" />
            <el-table-column prop="withdraw_date" label="退出日期" width="120" />
            <el-table-column prop="status" label="状态" width="100" />
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEditFollowInvestment(row)">
                编辑
              </el-button>
              <el-button link type="danger" size="small" @click="archiveFollowInvestment(row)">
                归档
              </el-button>
            </template>
          </el-table-column>
          </el-table>
        </el-card>

        <el-card class="profit-summary" style="margin-top: 20px;">
          <template #header>
            <div class="card-header">
              <span>结算台账</span>
            </div>
          </template>

          <el-form :inline="true" class="filter-form">
            <el-form-item label="月份">
              <el-date-picker
                v-model="settlementQuery.period_month"
                type="month"
                value-format="YYYY-MM"
                format="YYYY-MM"
                style="width: 140px"
              />
            </el-form-item>
            <el-form-item label="平台">
              <el-select v-model="settlementQuery.platform_code" style="width: 140px">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            <el-form-item label="店铺ID">
              <el-input v-model="settlementQuery.shop_id" placeholder="请输入店铺ID" style="width: 180px" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="settlementQuery.status" clearable style="width: 140px">
                <el-option label="草稿" value="draft" />
                <el-option label="已试算" value="calculated" />
                <el-option label="已审核" value="approved" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button @click="loadFollowInvestmentSettlements" :loading="financeStore.followInvestmentSettlements.loading">
                查询台账
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="financeStore.followInvestmentSettlements.data" v-loading="financeStore.followInvestmentSettlements.loading" stripe>
            <el-table-column prop="id" label="结算ID" width="100" />
            <el-table-column prop="period_month" label="月份" width="120" />
            <el-table-column prop="platform_code" label="平台" width="120" />
            <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
            <el-table-column prop="profit_basis_amount" label="结算基准利润 (楼)" width="160" align="right">
              <template #default="{ row }">{{ formatCurrency(row.profit_basis_amount) }}</template>
            </el-table-column>
            <el-table-column prop="distribution_ratio" label="分配比例" width="120" align="right">
              <template #default="{ row }">{{ formatPercentValue(row.distribution_ratio) }}</template>
            </el-table-column>
            <el-table-column prop="distributable_amount" label="可分配收益 (楼)" width="160" align="right">
              <template #default="{ row }">{{ formatCurrency(row.distributable_amount) }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100" />
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link type="info" size="small" @click="viewSettlementDetails(row)">
                查看明细
              </el-button>
              <el-button v-if="row.status !== 'approved'" link type="success" size="small" @click="approveFollowInvestment(row)">
                审核通过
              </el-button>
              <el-button v-if="row.status === 'approved'" link type="warning" size="small" @click="reopenFollowInvestment(row)">
                撤销审核
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 逾期预警 -->
    <el-card class="alert-card" v-if="financeStore.overdueAlert.data.length > 0">
      <template #header>
        <div class="card-header">
          <span>🚨 逾期预警</span>
          <el-tag type="danger">{{ financeStore.overdueAlert.total }} 笔逾期</el-tag>
        </div>
      </template>

      <el-table 
        :data="financeStore.overdueAlert.data.slice(0, 10)" 
        stripe
        size="small"
      >
        <el-table-column prop="order_id" label="订单号" width="150" />
        <el-table-column prop="outstanding_amount_cny" label="未收金额 (¥)" width="150" align="right">
          <template #default="{ row }">
            <span class="amount-danger">{{ formatCurrency(row.outstanding_amount_cny) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="due_date" label="到期日期" width="120" />
        <el-table-column prop="overdue_days" label="逾期天数" width="100" align="right">
          <template #default="{ row }">
            <el-tag type="danger">{{ row.overdue_days }}天</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="urgentFollow(row)">
              紧急跟进
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 记录收款对话框 -->
    <el-dialog v-model="showPaymentDialog" title="记录收款" width="600px">
      <el-form :model="paymentForm" label-width="120px">
        <el-form-item label="应收账款ID">
          <el-input v-model="paymentForm.arId" disabled />
        </el-form-item>
        <el-form-item label="收款日期">
          <el-date-picker v-model="paymentForm.receiptDate" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="收款金额">
          <el-input-number v-model="paymentForm.receiptAmount" :min="0" :precision="2" />
        </el-form-item>
        <el-form-item label="收款方式">
          <el-select v-model="paymentForm.paymentMethod">
            <el-option label="银行转账" value="bank_transfer" />
            <el-option label="支付宝" value="alipay" />
            <el-option label="微信" value="wechat" />
            <el-option label="PayPal" value="paypal" />
            <el-option label="平台结算" value="platform" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="银行账户">
          <el-input v-model="paymentForm.bankAccount" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="paymentForm.remark" type="textarea" rows="3" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showPaymentDialog = false">取消</el-button>
        <el-button type="primary" @click="submitPayment" :loading="submitting">
          确认收款
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showFollowInvestmentDialog" :title="followInvestmentDialogMode === 'create' ? '新增跟投' : '编辑跟投'" width="600px">
      <el-form :model="followInvestmentRecordForm" label-width="120px">
        <el-form-item label="投资人ID">
          <el-input-number v-model="followInvestmentRecordForm.investor_user_id" :min="1" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="followInvestmentRecordForm.platform_code" style="width: 180px">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺ID">
          <el-input v-model="followInvestmentRecordForm.shop_id" />
        </el-form-item>
        <el-form-item label="本金">
          <el-input-number v-model="followInvestmentRecordForm.contribution_amount" :min="0" :precision="2" />
        </el-form-item>
        <el-form-item label="投入日期">
          <el-date-picker v-model="followInvestmentRecordForm.contribution_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="退出日期">
          <el-date-picker v-model="followInvestmentRecordForm.withdraw_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="followInvestmentRecordForm.status" style="width: 180px">
            <el-option label="生效" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="followInvestmentRecordForm.remark" type="textarea" rows="3" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showFollowInvestmentDialog = false">取消</el-button>
        <el-button type="primary" @click="submitFollowInvestmentRecord" :loading="submitting">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showSettlementDetailsDrawer" title="结算明细" size="50%">
      <el-alert
        v-if="financeStore.followInvestmentSettlementDetails.error"
        type="error"
        :closable="false"
        :title="financeStore.followInvestmentSettlementDetails.error"
        style="margin-bottom: 16px;"
      />

      <el-table
        :data="financeStore.followInvestmentSettlementDetails.data"
        v-loading="financeStore.followInvestmentSettlementDetails.loading"
        stripe
      >
        <el-table-column prop="investor_user_id" label="投资人ID" width="120" />
        <el-table-column prop="contribution_amount_snapshot" label="本金快照 (¥)" width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.contribution_amount_snapshot) }}</template>
        </el-table-column>
        <el-table-column prop="occupied_days" label="占用天数" width="100" align="right" />
        <el-table-column prop="weighted_capital" label="加权资金" width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.weighted_capital) }}</template>
        </el-table-column>
        <el-table-column prop="share_ratio" label="分配占比" width="120" align="right">
          <template #default="{ row }">{{ formatPercentValue(row.share_ratio) }}</template>
        </el-table-column>
        <el-table-column prop="estimated_income" label="预计收益 (¥)" width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.estimated_income) }}</template>
        </el-table-column>
        <el-table-column prop="approved_income" label="已批准 (¥)" width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.approved_income) }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useFinanceStore } from '@/stores/finance'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Money,
  Check,
  Clock,
  Warning,
  Refresh,
  Search
} from '@element-plus/icons-vue'

const financeStore = useFinanceStore()

// Tab
const activeTab = ref('ar')
const currentMonth = new Date().toISOString().slice(0, 7)

const profitBasisForm = ref({
  period_month: currentMonth,
  platform_code: 'shopee',
  shop_id: ''
})

const followInvestmentForm = ref({
  period_month: currentMonth,
  platform_code: 'shopee',
  shop_id: '',
  distribution_ratio: 0.4
})

const followInvestmentQuery = ref({
  platform_code: 'shopee',
  shop_id: '',
  status: ''
})

const settlementQuery = ref({
  period_month: currentMonth,
  platform_code: 'shopee',
  shop_id: '',
  status: ''
})

// 筛选器
const dateRange = ref([])
const filters = ref({
  platform: null,
  shopId: null,
  status: null,
  startDate: null,
  endDate: null
})

// 分页
const arPage = ref(1)
const paymentPage = ref(1)
const expensePage = ref(1)

// 对话框
const showPaymentDialog = ref(false)
const showARDetailDialog = ref(false)
const showFollowInvestmentDialog = ref(false)
const showSettlementDetailsDrawer = ref(false)
const followInvestmentDialogMode = ref('create')
const editingFollowInvestmentId = ref(null)

// 收款表单
const paymentForm = ref({
  arId: null,
  orderId: null,
  receiptDate: new Date().toISOString().split('T')[0],
  receiptAmount: 0,
  paymentMethod: 'bank_transfer',
  bankAccount: '',
  remark: ''
})

const submitting = ref(false)

const followInvestmentRecordForm = ref({
  investor_user_id: null,
  platform_code: 'shopee',
  shop_id: '',
  contribution_amount: 0,
  contribution_date: new Date().toISOString().split('T')[0],
  withdraw_date: '',
  status: 'active',
  remark: ''
})

const loadProfitBasis = async () => {
  if (!profitBasisForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }

  await financeStore.fetchProfitBasis({
    period_month: profitBasisForm.value.period_month,
    platform_code: profitBasisForm.value.platform_code,
    shop_id: profitBasisForm.value.shop_id
  })
}

const rebuildProfitBasis = async () => {
  if (!profitBasisForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }

  try {
    await financeStore.rebuildProfitBasis({
      period_month: profitBasisForm.value.period_month,
      platform_code: profitBasisForm.value.platform_code,
      shop_id: profitBasisForm.value.shop_id,
      basis_version: 'A_ONLY_V1'
    })
    ElMessage.success('利润分配基准已重算')
  } catch (error) {
    ElMessage.error('重算利润基准失败: ' + error.message)
  }
}

const runFollowInvestmentSettlement = async () => {
  if (!followInvestmentForm.value.shop_id) {
    ElMessage.warning('请输入店铺ID')
    return
  }

  try {
    await financeStore.calculateFollowInvestmentSettlement({
      period_month: followInvestmentForm.value.period_month,
      platform_code: followInvestmentForm.value.platform_code,
      shop_id: followInvestmentForm.value.shop_id,
      distribution_ratio: followInvestmentForm.value.distribution_ratio
    })
    ElMessage.success('跟投收益试算完成')
  } catch (error) {
    ElMessage.error('跟投收益试算失败: ' + error.message)
  }
}

const loadFollowInvestments = async () => {
  await financeStore.fetchFollowInvestments({
    platform_code: followInvestmentQuery.value.platform_code || undefined,
    shop_id: followInvestmentQuery.value.shop_id || undefined,
    status: followInvestmentQuery.value.status || undefined
  })
}

const loadFollowInvestmentSettlements = async () => {
  await financeStore.fetchFollowInvestmentSettlements({
    period_month: settlementQuery.value.period_month || undefined,
    platform_code: settlementQuery.value.platform_code || undefined,
    shop_id: settlementQuery.value.shop_id || undefined,
    status: settlementQuery.value.status || undefined
  })
}

const viewSettlementDetails = async (row) => {
  await financeStore.fetchFollowInvestmentSettlementDetails(row.id)
  showSettlementDetailsDrawer.value = true
}

const resetFollowInvestmentRecordForm = () => {
  followInvestmentRecordForm.value = {
    investor_user_id: null,
    platform_code: 'shopee',
    shop_id: '',
    contribution_amount: 0,
    contribution_date: new Date().toISOString().split('T')[0],
    withdraw_date: '',
    status: 'active',
    remark: ''
  }
  editingFollowInvestmentId.value = null
}

const openCreateFollowInvestment = () => {
  followInvestmentDialogMode.value = 'create'
  resetFollowInvestmentRecordForm()
  showFollowInvestmentDialog.value = true
}

const openEditFollowInvestment = (row) => {
  followInvestmentDialogMode.value = 'edit'
  editingFollowInvestmentId.value = row.id
  followInvestmentRecordForm.value = {
    investor_user_id: row.investor_user_id,
    platform_code: row.platform_code,
    shop_id: row.shop_id,
    contribution_amount: row.contribution_amount,
    contribution_date: row.contribution_date,
    withdraw_date: row.withdraw_date || '',
    status: row.status,
    remark: row.remark || ''
  }
  showFollowInvestmentDialog.value = true
}

const submitFollowInvestmentRecord = async () => {
  try {
    submitting.value = true
    const payload = {
      ...followInvestmentRecordForm.value,
      withdraw_date: followInvestmentRecordForm.value.withdraw_date || null
    }
    if (followInvestmentDialogMode.value === 'create') {
      await financeStore.createFollowInvestment(payload)
      ElMessage.success('跟投记录已创建')
    } else {
      await financeStore.updateFollowInvestment(
        editingFollowInvestmentId.value,
        payload,
        {
          platform_code: followInvestmentQuery.value.platform_code || undefined,
          shop_id: followInvestmentQuery.value.shop_id || undefined,
          status: followInvestmentQuery.value.status || undefined
        }
      )
      ElMessage.success('跟投记录已更新')
    }
    showFollowInvestmentDialog.value = false
    resetFollowInvestmentRecordForm()
  } catch (error) {
    ElMessage.error('保存跟投记录失败: ' + error.message)
  } finally {
    submitting.value = false
  }
}

const archiveFollowInvestment = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确认归档跟投记录 #${row.id} 吗？`,
      '归档跟投记录',
      {
        confirmButtonText: '确认归档',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await financeStore.archiveFollowInvestment(row.id, {
      platform_code: followInvestmentQuery.value.platform_code || undefined,
      shop_id: followInvestmentQuery.value.shop_id || undefined,
      status: followInvestmentQuery.value.status || undefined
    })
    ElMessage.success('跟投记录已归档')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('归档失败: ' + (error.message || error))
    }
  }
}

const approveFollowInvestment = async (row) => {
  try {
    await financeStore.approveFollowInvestmentSettlement(row.id)
    ElMessage.success('结算已审核')
    await loadFollowInvestmentSettlements()
  } catch (error) {
    ElMessage.error('审核失败: ' + error.message)
  }
}

const reopenFollowInvestment = async (row) => {
  try {
    await financeStore.reopenFollowInvestmentSettlement(row.id)
    ElMessage.success('结算已撤销审核')
    await loadFollowInvestmentSettlements()
  } catch (error) {
    ElMessage.error('撤销审核失败: ' + error.message)
  }
}

// 初始化数据
const initData = async () => {
  try {
    // 设置默认日期范围（最近30天）
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - 30)
    
    dateRange.value = [
      startDate.toISOString().split('T')[0],
      endDate.toISOString().split('T')[0]
    ]
    
    filters.value.startDate = dateRange.value[0]
    filters.value.endDate = dateRange.value[1]
    
    // 设置筛选器
    financeStore.setFilters(filters.value)
    
    // 加载财务总览
    await financeStore.fetchOverview(filters.value)
    
    // 加载应收账款
    await financeStore.fetchAccountsReceivable()
    
    // 加载逾期预警
    await financeStore.fetchOverdueAlert({ overdueDays: 7 })
    
  } catch (error) {
    ElMessage.error('初始化数据失败: ' + error.message)
  }
}

// 刷新数据
const refreshData = async () => {
  try {
    await financeStore.fetchOverview(filters.value)
    await financeStore.fetchAccountsReceivable()
    await financeStore.fetchOverdueAlert({ overdueDays: 7 })
    ElMessage.success('数据刷新成功')
  } catch (error) {
    ElMessage.error('数据刷新失败: ' + error.message)
  }
}

// 处理筛选变化
const handleFilterChange = () => {
  financeStore.setFilters(filters.value)
  arPage.value = 1
  financeStore.fetchAccountsReceivable()
}

// 处理日期变化
const handleDateChange = (dates) => {
  if (dates && dates.length === 2) {
    filters.value.startDate = dates[0]
    filters.value.endDate = dates[1]
    refreshData()
  }
}

// 处理分页
const handleARPageChange = (page) => {
  financeStore.setPage(page, 'accountsReceivable')
  financeStore.fetchAccountsReceivable()
}

const handlePaymentPageChange = (page) => {
  financeStore.setPage(page, 'paymentReceipts')
  financeStore.fetchPaymentReceipts()
}

const handleExpensePageChange = (page) => {
  financeStore.setPage(page, 'expenses')
  financeStore.fetchExpenses()
}

// 记录收款
const recordPayment = (row) => {
  paymentForm.value.arId = row.ar_id
  paymentForm.value.orderId = row.order_id
  paymentForm.value.receiptAmount = row.outstanding_amount_cny
  showPaymentDialog.value = true
}

// 提交收款
const submitPayment = async () => {
  try {
    submitting.value = true
    
    await financeStore.recordPayment(paymentForm.value)
    
    ElMessage.success('收款记录成功')
    showPaymentDialog.value = false
    
    // 重置表单
    paymentForm.value = {
      arId: null,
      orderId: null,
      receiptDate: new Date().toISOString().split('T')[0],
      receiptAmount: 0,
      paymentMethod: 'bank_transfer',
      bankAccount: '',
      remark: ''
    }
    
  } catch (error) {
    ElMessage.error('记录收款失败: ' + error.message)
  } finally {
    submitting.value = false
  }
}

// 查看详情
const viewARDetail = (row) => {
  ElMessage.info('应收账款详情功能开发中...')
}

// 紧急跟进
const urgentFollow = (row) => {
  ElMessageBox.confirm(
    `订单 ${row.order_id} 已逾期 ${row.overdue_days} 天，未收金额 ¥${row.outstanding_amount_cny}。是否发送催款通知？`,
    '逾期催款',
    {
      confirmButtonText: '发送通知',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    ElMessage.success('催款通知已发送')
  }).catch(() => {
    // 取消操作
  })
}

// 汇总方法
const getSummaries = (param) => {
  const { columns, data } = param
  const sums = []
  
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    
    const values = data.map(item => Number(item[column.property]))
    if (column.property && values.every(value => !isNaN(value))) {
      sums[index] = formatCurrency(values.reduce((prev, curr) => prev + curr, 0))
    } else {
      sums[index] = '-'
    }
  })
  
  return sums
}

// 工具函数
const formatNumber = (num) => {
  if (!num && num !== 0) return '0'
  return new Intl.NumberFormat('zh-CN').format(num)
}

const formatCurrency = (num) => {
  if (!num && num !== 0) return '0.00'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num)
}

const formatPercentValue = (num) => {
  if (num == null || num === undefined) return '-'
  return `${(Number(num) * 100).toFixed(2)}%`
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

const getPlatformType = (platform) => {
  const typeMap = {
    'shopee': 'success',
    'tiktok': 'primary',
    'amazon': 'warning',
    'miaoshou': 'info'
  }
  return typeMap[platform?.toLowerCase()] || 'info'
}

const getARStatusType = (status) => {
  const typeMap = {
    'pending': 'warning',
    'paid': 'success',
    'overdue': 'danger',
    'cancelled': 'info'
  }
  return typeMap[status] || 'info'
}

const getARStatusText = (status) => {
  const textMap = {
    'pending': '待收款',
    'paid': '已收款',
    'overdue': '已逾期',
    'cancelled': '已取消'
  }
  return textMap[status] || status
}

const getPaymentMethodText = (method) => {
  const textMap = {
    'bank_transfer': '银行转账',
    'alipay': '支付宝',
    'wechat': '微信',
    'paypal': 'PayPal',
    'platform': '平台结算',
    'other': '其他'
  }
  return textMap[method] || method
}

const getExpenseTypeText = (type) => {
  const textMap = {
    'commission': '平台佣金',
    'shipping': '运费',
    'ad': '广告费',
    'other': '其他'
  }
  return textMap[type] || type
}

const getProfitMarginType = (margin) => {
  if (margin >= 20) return 'success'
  if (margin >= 10) return ''
  if (margin >= 0) return 'warning'
  return 'danger'
}

onMounted(() => {
  initData()
  loadFollowInvestments()
  loadFollowInvestmentSettlements()
})
</script>

<style scoped>
.financial-management {
  padding: 20px;
  background: #f0f2f5;
  min-height: 100vh;
}

.page-header {
  text-align: center;
  margin-bottom: 30px;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
  padding: 40px 20px;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.page-header h1 {
  margin: 0 0 10px 0;
  font-size: 32px;
  font-weight: 700;
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: 16px;
}

.filter-card {
  margin-bottom: 20px;
  border-radius: 8px;
}

.stats-section {
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
  margin-bottom: 20px;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.stat-card.warning {
  border-left: 4px solid #faad14;
}

.stat-card.danger {
  border-left: 4px solid #f5222d;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
}

.ar-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.received-icon {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.outstanding-icon {
  background: linear-gradient(135deg, #faad14 0%, #ffc53d 100%);
}

.overdue-icon {
  background: linear-gradient(135deg, #f5222d 0%, #ff4d4f 100%);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: #8c8c8c;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #262626;
}

.finance-tabs {
  background: white;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.profit-summary {
  background: #fafafa;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.summary-item {
  text-align: center;
  padding: 20px;
  background: white;
  border-radius: 8px;
}

.summary-label {
  font-size: 14px;
  color: #8c8c8c;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 28px;
  font-weight: 700;
}

.summary-value.revenue {
  color: #1890ff;
}

.summary-value.cost {
  color: #faad14;
}

.summary-value.profit {
  color: #52c41a;
}

.alert-card {
  border-radius: 8px;
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.amount-outstanding {
  color: #faad14;
  font-weight: 600;
}

.amount-danger {
  color: #f5222d;
  font-weight: 700;
}

.amount-received {
  color: #52c41a;
  font-weight: 600;
}

.expense-amount {
  color: #f5222d;
  font-weight: 600;
}

.profit-positive {
  color: #52c41a;
  font-weight: 600;
}

.profit-negative {
  color: #f5222d;
  font-weight: 600;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .financial-management {
    padding: 10px;
  }
  
  .page-header h1 {
    font-size: 24px;
  }
  
  .stat-card {
    flex-direction: column;
    text-align: center;
  }
}
</style>
