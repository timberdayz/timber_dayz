<template>
  <div class="expense-management erp-page-container erp-page--admin">
    <PageHeader
      title="费用管理"
      subtitle="按月份或按店铺维护经营成本。人力费用为店铺成本分摊，不作为员工工资单录入入口。"
      family="admin"
    />

    <!-- 模式切换 Tab -->
    <el-tabs
      v-model="viewMode"
      @tab-change="handleModeChange"
      class="erp-mb-lg"
    >
      <el-tab-pane label="按月份查看" name="monthly">
        <template #label>
          <span
            ><el-icon><Calendar /></el-icon> 按月份查看</span
          >
        </template>
      </el-tab-pane>
      <el-tab-pane label="按店铺查看" name="shop">
        <template #label>
          <span
            ><el-icon><Shop /></el-icon> 按店铺查看</span
          >
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 按月份查看模式 -->
    <div v-if="viewMode === 'monthly'">
      <!-- 操作栏 -->
      <div class="action-bar erp-mb-lg">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          class="erp-w-180"
          @change="handleMonthChange"
        />
        <el-radio-group
          v-model="platformScope"
          size="default"
          class="erp-ml-sm"
          @change="handlePlatformScopeChange"
        >
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="shopee">Shopee</el-radio-button>
          <el-radio-button value="tiktok">TikTok</el-radio-button>
        </el-radio-group>
        <el-button
          type="primary"
          @click="openQuickSplitDialog"
          class="erp-ml-sm"
        >
          快速拆分
        </el-button>
        <el-button
          type="success"
          @click="handleBatchSave"
          :loading="batchSaving"
          class="erp-ml-sm"
        >
          批量保存
        </el-button>
        <el-button
          :icon="Refresh"
          @click="loadMonthlyExpenses"
          class="erp-ml-sm"
        >
          刷新
        </el-button>
        <div class="erp-flex-spacer"></div>
      </div>

      <!-- 统计卡片（月度 + 年度） -->
      <el-row :gutter="20" class="erp-mb-lg">
        <el-col :span="4">
          <el-card class="stat-card monthly">
            <div class="stat-item">
              <div class="stat-label">本月总费用</div>
              <div class="stat-value primary">
                {{ formatNumber(monthlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">
                年度累计<span class="stat-label-hint">（全部平台）</span>
              </div>
              <div class="stat-value warning">
                {{ formatNumber(yearlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月租金</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月营销费用</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_marketing_fee) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月水电</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月人力费用</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_labor_cost) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月其他</div>
              <div class="stat-value">
                {{ formatNumber(monthlySummary.total_other) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 月度费用表格 -->
      <el-card>
        <!-- 错误状态显示 -->
        <div v-if="monthlyError && !loading" class="error-state">
          <el-result icon="error" :title="monthlyError.message">
            <template #sub-title>
              <span>{{ monthlyError.recovery }}</span>
            </template>
            <template #extra>
              <el-button type="primary" @click="loadMonthlyExpenses">重新加载</el-button>
            </template>
          </el-result>
        </div>

        <!-- 正常表格（无错误时显示） -->
        <el-table
          v-if="!monthlyError"
          :data="visibleMonthlyRows"
          stripe
          v-loading="loading"
          class="erp-table"
          border
        >
          <el-table-column
            prop="shop_name"
            label="店铺"
            width="200"
            fixed="left"
          >
            <template #default="{ row }">
              <el-select
                v-model="row.shop_key"
                placeholder="选择店铺"
                class="erp-w-full"
                :disabled="!!row.id"
                @change="handleShopChange(row)"
              >
                <el-option
                  v-for="shop in allShops"
                  :key="`${shop.platform_code}|${shop.shop_id}`"
                  :label="shop.option_label || shop.shop_name"
                  :value="buildExpenseRowKey(shop)"
                >
                  <div>{{ shop.shop_name }}</div>
                  <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
                </el-option>
              </el-select>
              <div v-if="row.main_account_name || row.main_account_id" class="shop-option-secondary">
                租户：{{ row.main_account_name || row.main_account_id }}
              </div>
              <el-tag v-if="row.enabled === false" type="info" size="small">
                已停用
              </el-tag>
              <el-tag v-else-if="row.enabled === null" type="warning" size="small">
                状态未知
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="marketing_fee"
            label="营销费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.marketing_fee"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="ai_token_cost"
            label="AI Token费用"
            width="140"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.ai_token_cost"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="labor_cost"
            label="系统人力成本"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <span>{{ formatNumber(row.labor_cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="220">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                type="textarea"
                :rows="1"
                autosize
                placeholder="可选"
                @change="() => {}"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total_cost"
            label="成本合计"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>{{ formatNumber(row.total_cost ?? row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                @click="handleSaveRow(row)"
                :loading="row.saving"
              >
                保存
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDeleteRow(row)"
                :disabled="!row.id"
              >
                删除
              </el-button>
              <el-button
                v-if="row.id"
                size="small"
                type="warning"
                plain
                @click="handleRestoreRow(row)"
              >
                恢复
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="deletedMonthlyData.length" class="erp-mt-md">
          <div class="deleted-expenses-title">已删除费用记录</div>
          <el-table :data="deletedMonthlyData" size="small" border>
            <el-table-column prop="year_month" label="月份" width="110" />
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column prop="shop_id" label="店铺" min-width="180">
              <template #default="{ row }">
                <ShopDisplayText :row="row" />
              </template>
            </el-table-column>
            <el-table-column prop="total_cost" label="成本合计" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button size="small" type="warning" plain @click="handleRestoreRow(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-dialog
        v-model="quickSplitDialogVisible"
        title="快速拆分"
        width="520px"
      >
        <div class="quick-split-tip">
          按所选范围分摊到在营店铺。会覆盖这些店铺的现有金额，保存前仍可逐店修改。
        </div>
        <div class="quick-split-meta">当前月份：{{ selectedMonth || '-' }}</div>
        <div class="quick-split-meta">拆分店铺数：{{ countSplitTargets(visibleMonthlyRows, quickSplitScope) }}</div>
        <el-form label-position="top" class="quick-split-form">
          <el-form-item label="分摊范围">
            <el-select
              v-model="quickSplitScope.platform_code"
              placeholder="全部在营店铺"
              class="erp-w-full"
              @change="handleQuickSplitScopeChange"
            >
              <el-option label="全部在营店铺" value="" />
              <el-option label="仅 Shopee" value="shopee" />
              <el-option label="仅 TikTok" value="tiktok" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="quickSplitScope.platform_code" label="按租户收窄（可选）">
            <el-select
              v-model="quickSplitScope.main_account_id"
              placeholder="该平台全部租户"
              clearable
              class="erp-w-full"
            >
              <el-option
                v-for="tenant in tenantOptions"
                :key="tenant.main_account_id"
                :label="tenant.label"
                :value="tenant.main_account_id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="总租金">
            <el-input-number
              v-model="quickSplitForm.rent"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总营销费用">
            <el-input-number
              v-model="quickSplitForm.marketing_fee"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总水电费">
            <el-input-number
              v-model="quickSplitForm.utilities"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总AI Token费用">
            <el-input-number
              v-model="quickSplitForm.ai_token_cost"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
          <el-form-item label="总其他费用">
            <el-input-number
              v-model="quickSplitForm.other_costs"
              :min="0"
              :precision="2"
              :controls="false"
              class="erp-w-full"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="quickSplitDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleApplyQuickSplit">应用拆分</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 按店铺查看模式 -->
    <div v-else-if="viewMode === 'shop'">
      <!-- 操作栏 -->
      <div class="action-bar erp-mb-lg">
        <el-select
          v-model="selectedShopKey"
          placeholder="选择店铺"
          class="erp-w-250"
          @change="handleShopSelectChange"
          filterable
        >
          <el-option
            v-for="shop in shopViewOptions"
            :key="`${shop.platform_code}|${shop.shop_id}`"
            :label="shop.option_label || shop.shop_name"
            :value="buildExpenseRowKey(shop)"
          >
            <div>{{ shop.shop_name }}</div>
            <div v-if="shop.secondary_name" class="shop-option-secondary">{{ shop.secondary_name }}</div>
            <el-tag v-if="shop.enabled === false" type="info" size="small">已停用</el-tag>
          </el-option>
        </el-select>
        <el-date-picker
          v-model="selectedYear"
          type="year"
          placeholder="选择年份"
          value-format="YYYY"
          size="default"
          class="erp-w-150 erp-ml-sm"
          @change="loadShopExpenses"
        />
        <el-button
          :icon="Refresh"
          @click="loadShopExpenses"
          class="erp-ml-sm"
        >
          刷新
        </el-button>
        <div class="erp-flex-spacer"></div>
      </div>

      <!-- 店铺年度汇总卡片 -->
      <el-row :gutter="20" class="erp-mb-lg">
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">年度总费用</div>
              <div class="stat-value primary">
                {{ formatNumber(shopSummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">月均费用</div>
              <div class="stat-value">
                {{
                  formatNumber(
                    shopSummary.month_count > 0
                      ? shopSummary.total_amount / shopSummary.month_count
                      : 0,
                  )
                }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度租金</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度营销费用</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_marketing_fee) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度水电</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度人力费用</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_labor_cost) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度其他</div>
              <div class="stat-value">
                {{ formatNumber(shopSummary.total_other_costs) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 店铺费用表格（按月份） -->
      <el-card>
        <el-empty
          v-if="!selectedShopId"
          description="请先选择店铺"
        />
        <el-table
          v-else
          :data="shopTableData"
          empty-text="该店铺该年度暂无费用记录"
          stripe
          v-loading="loading"
          class="erp-table"
          border
        >
          <el-table-column
            prop="year_month"
            label="月份"
            width="120"
            fixed="left"
          >
            <template #default="{ row }">
              <el-tag v-if="row.id" type="primary">{{ row.year_month }}</el-tag>
              <el-date-picker
                v-else
                v-model="row.year_month"
                type="month"
                placeholder="选择月份"
                value-format="YYYY-MM"
                size="small"
                class="erp-w-full"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="marketing_fee"
            label="营销费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.marketing_fee"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="ai_token_cost"
            label="AI Token费用"
            width="140"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.ai_token_cost"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="labor_cost"
            label="系统人力成本"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <span>{{ formatNumber(row.labor_cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他费用"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                class="erp-w-full"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="220">
            <template #default="{ row }">
              <el-input
                v-model="row.note"
                type="textarea"
                :rows="1"
                autosize
                placeholder="可选"
                @change="() => {}"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total_cost"
            label="成本合计"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>{{ formatNumber(row.total_cost ?? row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row, $index }">
              <el-button
                size="small"
                type="primary"
                @click="handleSaveShopRow(row)"
                :loading="row.saving"
              >
                保存
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDeleteShopRow(row, $index)"
                :disabled="!row.id"
              >
                删除
              </el-button>
              <el-button
                v-if="row.id"
                size="small"
                type="warning"
                plain
                @click="handleRestoreShopRow(row)"
              >
                恢复
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="deletedShopData.length" class="erp-mt-md">
          <div class="deleted-expenses-title">已删除费用记录</div>
          <el-table :data="deletedShopData" size="small" border>
            <el-table-column prop="year_month" label="月份" width="110" />
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column prop="total_cost" label="成本合计" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.total_cost) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button size="small" type="warning" plain @click="handleRestoreShopRow(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 添加新月份按钮 -->
        <div class="erp-mt-md">
          <el-button
            type="primary"
            :icon="Plus"
            @click="handleAddMonthRow"
            :disabled="!selectedShopId"
          >
            添加月份
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Calendar, Shop } from '@element-plus/icons-vue'
import api from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import employeeTasksApi from '@/api/employeeTasks.js'
import { buildShopAccountLookup, resolveShopDisplay } from '@/utils/shopDisplay'
import {
  buildExpenseRowKey,
  countSplitTargets,
  distributeEvenly,
  resolveQuickSplitTargets,
  sortExpenseRows,
  splitShopsByAvailability
} from '@/utils/expenseViewModel.js'
import ShopDisplayText from '@/components/common/ShopDisplayText.vue'

const route = useRoute()
let shopAccountLookup = new Map()

// ==================== 公共状态 ====================
const viewMode = ref('monthly') // monthly | shop
const allShops = ref([]) // 全部运营店铺（含停用）：标注、按店铺下拉、查 platform_code
const operatingShops = ref([]) // 在营店铺：空白行生成、分摊范围
const platformScope = ref('all') // 'all' | 'shopee' | 'tiktok'
const loading = ref(false)
const monthlyError = ref(null) // 月度数据加载错误状态
const shopError = ref(null) // 店铺数据加载错误状态

// ==================== 按月份查看模式 ====================
const selectedMonth = ref(null)
const monthlyTableData = ref([])
const batchSaving = ref(false)
const quickSplitDialogVisible = ref(false)
const quickSplitForm = reactive({
  rent: 0,
  marketing_fee: 0,
  utilities: 0,
  ai_token_cost: 0,
  other_costs: 0
})

// 快速拆分的分摊范围：**唯一**的范围来源（界面计数与实际应用都读它）
const quickSplitScope = reactive({
  platform_code: '',
  main_account_id: ''
})

// 当前平台分段下的可见行（表格与月度汇总都用它）
const visibleMonthlyRows = computed(() => {
  const rows = monthlyTableData.value
  if (platformScope.value === 'all') return rows
  return rows.filter((row) => row.platform_code === platformScope.value)
})

// 租户选项（按当前分段内的在营店铺去重，并按分摊范围收窄）
const tenantOptions = computed(() => {
  const platform = quickSplitScope.platform_code
  const ids = [...new Set(
    visibleMonthlyRows.value
      .filter((row) => row.enabled === true)
      .filter((row) => !platform || row.platform_code === platform)
      .map((row) => row.main_account_id)
      .filter(Boolean)
  )]
  return ids.map((id) => ({ main_account_id: id, label: id }))
})

// 月度汇总
const monthlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_labor_cost: 0,
  total_other: 0
})

// 年度汇总
const yearlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_labor_cost: 0,
  total_other_costs: 0
})

// ==================== 按店铺查看模式 ====================
const selectedShopId = ref(null)
const selectedShopKey = ref('') // 复合键（平台 + 店铺账号 ID），跨平台不撞车
const selectedShopPlatform = ref('')
const selectedYear = ref(null)
const shopTableData = ref([])
const deletedMonthlyData = ref([])
const deletedShopData = ref([])

// 某年有费用记录的店铺集合：用于「按店铺」下拉把停用店也列出来
const shopViewRecordedIds = ref(new Set())

// 「按店铺查看」下拉选项：在营店 ＋ 当年有记录的停用店
const shopViewOptions = computed(() => {
  const recorded = shopViewRecordedIds.value
  return allShops.value.filter(
    (shop) => shop.enabled === true || recorded.has(shop.shop_id)
  )
})

// 店铺汇总
const shopSummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_marketing_fee: 0,
  total_utilities: 0,
  total_ai_token_cost: 0,
  total_labor_cost: 0,
  total_other_costs: 0,
  month_count: 0
})

const taskContext = reactive({
  taskId: '',
  yearMonth: '',
  shopId: '',
  platformCode: ''
})

// ==================== 公共方法 ====================
const formatNumber = (num) => {
  if (num === null || num === undefined) return '0.00'
  return Number(num).toFixed(2)
}

const normalizeExpenseRow = (item = {}) => {
  const marketingFee = Number(item.marketing_fee) || 0
  const aiTokenCost = Number(item.ai_token_cost) || 0
  const laborCost = Number(item.labor_cost) || 0
  const displayMeta = resolveShopDisplay(item, shopAccountLookup)
  return {
    ...item,
    platform_code: item.platform_code ?? null,
    marketing_fee: marketingFee,
    ai_token_cost: aiTokenCost,
    labor_cost: laborCost,
    note: item.note ?? '',
    total_cost: Number(item.total_cost ?? item.total) || 0,
    shop_name: displayMeta.display_name,
    secondary_name: displayMeta.secondary_name,
    canonical_shop_name: displayMeta.canonical_name,
    option_label: displayMeta.option_label,
    search_text: displayMeta.search_text
  }
}

const isMeaningfulExpenseRow = (row = {}) => {
  const note = String(row.note || '').trim()
  const attachments = Array.isArray(row.attachments) ? row.attachments : []
  return (
    (Number(row.rent) || 0) > 0 ||
    (Number(row.marketing_fee) || 0) > 0 ||
    (Number(row.utilities) || 0) > 0 ||
    (Number(row.ai_token_cost) || 0) > 0 ||
    (Number(row.labor_cost) || 0) > 0 ||
    (Number(row.other_costs) || 0) > 0 ||
    note.length > 0 ||
    attachments.length > 0
  )
}

const laborCostForPayload = (row = {}) =>
  row.labor_cost_source === 'system' ? 0 : (Number(row.labor_cost) || 0)

const initTaskContext = () => {
  taskContext.taskId = typeof route.query.task_id === 'string' ? route.query.task_id : ''
  taskContext.yearMonth = typeof route.query.year_month === 'string' ? route.query.year_month : ''
  taskContext.shopId = typeof route.query.shop_id === 'string' ? route.query.shop_id : ''
  taskContext.platformCode = typeof route.query.platform_code === 'string' ? route.query.platform_code : ''
  if (taskContext.yearMonth) {
    selectedMonth.value = taskContext.yearMonth
  }
}

const tryCompleteTaskFromExpenseRow = async (row, yearMonthOverride = '') => {
  if (!taskContext.taskId) return
  const currentYearMonth = String(yearMonthOverride || row.year_month || selectedMonth.value || '')
  if (currentYearMonth !== String(taskContext.yearMonth || '')) return
  if (String(row.shop_id || '') !== String(taskContext.shopId || '')) return
  await employeeTasksApi.submitTask(taskContext.taskId, {
    completion_payload: {
      year_month: currentYearMonth,
      shop_id: row.shop_id,
      total: Number(row.total) || 0
    },
    result_comment: 'monthly cost entry submitted from expense management',
    requires_confirmation: true
  })
}

// 加载店铺列表（含已停用：用于「已停用」标注与按店铺查历史）
const loadShops = async () => {
  try {
    const [expenseShopsResult, shopDirectoryResult] = await Promise.allSettled([
      api.get('/expenses/shops', { params: { include_disabled: true } }),
      api.getShopDirectory({ enabled: true })
    ])
    if (expenseShopsResult.status !== 'fulfilled') {
      throw expenseShopsResult.reason
    }
    const shopDirectory = shopDirectoryResult.status === 'fulfilled' ? shopDirectoryResult.value : []
    shopAccountLookup = buildShopAccountLookup(Array.isArray(shopDirectory) ? shopDirectory : [])
    const expenseShops = expenseShopsResult.value
    const rawShops = Array.isArray(expenseShops)
      ? expenseShops
      : (expenseShops?.data ?? expenseShops ?? [])

    const decorated = rawShops.map((shop) => {
      const displayMeta = resolveShopDisplay(shop, shopAccountLookup)
      return {
        ...shop,
        shop_name: displayMeta.display_name,
        secondary_name: displayMeta.secondary_name,
        canonical_shop_name: displayMeta.canonical_name,
        option_label: displayMeta.option_label,
        search_text: displayMeta.search_text
      }
    })

    // 店铺集合按启用状态拆分：全部（含停用）vs 在营
    const split = splitShopsByAvailability(decorated)
    allShops.value = split.all
    operatingShops.value = split.operating
  } catch (error) {
    console.error('加载店铺列表失败:', error)
    ElMessage.error(error.message || '加载店铺列表失败')
    allShops.value = []
    operatingShops.value = []
  }
}

// 模式切换处理
const handleModeChange = (mode) => {
  if (mode === 'monthly' && selectedMonth.value) {
    loadMonthlyExpenses()
  } else if (mode === 'shop' && selectedShopId.value) {
    loadShopExpenses()
  }
}

// ==================== 按月份模式方法 ====================

// 加载月度费用
const loadMonthlyExpenses = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  loading.value = true
  monthlyError.value = null // 重置错误状态
  try {
    // 并行加载月度数据和年度汇总
    const [monthlyRes, yearlyRes, deletedRes] = await Promise.all([
      api.get('/expenses', {
        params: { year_month: selectedMonth.value, page_size: 1000 }
      }),
      api.get('/expenses/summary/yearly', {
        params: { year: selectedMonth.value.substring(0, 4) }
      }),
      api.get('/expenses/deleted', {
        params: { year_month: selectedMonth.value }
      })
    ])

    // 处理月度数据
    const existingData = monthlyRes.items || []
    const shopKeySet = new Set(existingData.map((item) => buildExpenseRowKey(item)))

    // 为没有数据的**在营**店铺创建空白行（停用店不生成空白行）
    const newRows = operatingShops.value
      .filter((shop) => !shopKeySet.has(buildExpenseRowKey(shop)))
      .map((shop) => ({
        id: null,
        platform_code: shop.platform_code,
        shop_id: shop.shop_id,
        shop_key: buildExpenseRowKey(shop),
        shop_account_id: shop.shop_account_id ?? null,
        shop_name: shop.shop_name,
        main_account_id: shop.main_account_id,
        main_account_name: shop.main_account_name,
        enabled: shop.enabled,
        year_month: selectedMonth.value,
        rent: 0,
        marketing_fee: 0,
        utilities: 0,
        ai_token_cost: 0,
        labor_cost: 0,
        other_costs: 0,
        total_cost: 0,
        total: 0,
        note: '',
        attachments: [],
        saving: false
      }))

    // 合并现有数据和空白行，只保留当月数据；平台/租户/店铺排序
    const merged = [
      ...existingData
        .filter((item) => item.year_month === selectedMonth.value)
        .map((item) => {
          const matched = allShops.value.find(
            (s) => buildExpenseRowKey(s) === buildExpenseRowKey(item)
          )
          // shop_enabled 为 null = 店铺账号已不存在（历史孤儿行）：
          // 显示原始 ID，不丢弃该行
          const isOrphan = item.shop_enabled === null
          return {
            ...normalizeExpenseRow(item),
            shop_name: matched?.shop_name || item.shop_id,
            shop_account_id: matched?.shop_account_id ?? item.shop_shop_account_id ?? null,
            shop_key: isOrphan ? String(item.shop_id || '') : buildExpenseRowKey(item),
            main_account_id: item.shop_main_account_id || matched?.main_account_id || '',
            main_account_name: item.shop_main_account_name || matched?.main_account_name || '',
            enabled: item.shop_enabled,
            saving: false
          }
        }),
      ...newRows
    ]

    monthlyTableData.value = sortExpenseRows(merged)

    // 计算月度汇总（只计算已保存的数据）
    calculateMonthlySummary()

    // 更新年度汇总
    if (yearlyRes) {
      yearlySummary.total_amount = yearlyRes.total_amount || 0
      yearlySummary.total_rent = yearlyRes.total_rent || 0
      yearlySummary.total_marketing_fee = yearlyRes.total_marketing_fee || 0
      yearlySummary.total_utilities = yearlyRes.total_utilities || 0
      yearlySummary.total_ai_token_cost = yearlyRes.total_ai_token_cost || 0
      yearlySummary.total_labor_cost = yearlyRes.total_labor_cost || 0
      yearlySummary.total_other_costs = yearlyRes.total_other_costs || 0
    }
    deletedMonthlyData.value = deletedRes.items || []
  } catch (error) {
    console.error('加载费用数据失败:', error)
    // 设置错误状态，区分"无数据"和"加载失败"
    monthlyError.value = {
      message: error.message || '加载费用数据失败',
      recovery: error.recovery_suggestion || '请检查网络连接或联系管理员'
    }
    monthlyTableData.value = []
    deletedMonthlyData.value = []
    ElMessage.error(monthlyError.value.message)
  } finally {
    loading.value = false
  }
}

// 计算月度汇总
const calculateMonthlySummary = () => {
  monthlySummary.total_amount = 0
  monthlySummary.total_rent = 0
  monthlySummary.total_marketing_fee = 0
  monthlySummary.total_utilities = 0
  monthlySummary.total_ai_token_cost = 0
  monthlySummary.total_labor_cost = 0
  monthlySummary.total_other = 0

  visibleMonthlyRows.value
    .forEach((item) => {
      const rent = Number(item.rent) || 0
      const marketingFee = Number(item.marketing_fee) || 0
      const utilities = Number(item.utilities) || 0
      const aiTokenCost = Number(item.ai_token_cost) || 0
      const laborCost = Number(item.labor_cost) || 0
      const otherCosts = Number(item.other_costs) || 0

      monthlySummary.total_amount += rent + marketingFee + utilities + aiTokenCost + laborCost + otherCosts
      monthlySummary.total_rent += rent
      monthlySummary.total_marketing_fee += marketingFee
      monthlySummary.total_utilities += utilities
      monthlySummary.total_ai_token_cost += aiTokenCost
      monthlySummary.total_labor_cost += laborCost
      monthlySummary.total_other += otherCosts
    })
}

// 更新行合计
const updateRowTotal = (row) => {
  row.total_cost =
    (Number(row.rent) || 0) +
    (Number(row.marketing_fee) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.ai_token_cost) || 0) +
    (Number(row.labor_cost) || 0) +
    (Number(row.other_costs) || 0)
  row.total = row.total_cost
  calculateMonthlySummary()
}

// 店铺选择变化
const handleShopChange = (row) => {
  // 目录条目：用 view-model 的行键口径匹配（平台 + 店铺账号 ID），
  // 不用裸 shop_id —— 跨平台同 id 会撞车
  const shop = allShops.value.find(
    (s) => buildExpenseRowKey(s) === row.shop_key
  )
  if (shop) {
    row.platform_code = shop.platform_code
    row.shop_id = shop.shop_id
    row.shop_account_id = shop.shop_account_id ?? null
    row.shop_name = shop.shop_name
    row.main_account_id = shop.main_account_id
    row.main_account_name = shop.main_account_name
    row.enabled = shop.enabled
  }
}

// 平台分段切换
const handlePlatformScopeChange = () => {
  // 分段只影响展示与拆分范围，不改数据；分摊范围跟随分段（唯一来源 quickSplitScope）
  quickSplitScope.platform_code = platformScope.value === 'all' ? '' : platformScope.value
  const stillValid = tenantOptions.value.some(
    (tenant) => tenant.main_account_id === quickSplitScope.main_account_id
  )
  if (quickSplitScope.main_account_id && !stillValid) {
    quickSplitScope.main_account_id = ''
  }
  calculateMonthlySummary()
}

// 快速拆分的平台范围切换
const handleQuickSplitScopeChange = () => {
  // 平台变了，租户收窄要重新选（旧租户可能不在新平台里）
  quickSplitScope.main_account_id = ''
}

// 月份变化
const handleMonthChange = () => {
  if (selectedMonth.value) {
    loadMonthlyExpenses()
  } else {
    monthlyTableData.value = []
    calculateMonthlySummary()
  }
}

const resetQuickSplitForm = () => {
  quickSplitForm.rent = 0
  quickSplitForm.marketing_fee = 0
  quickSplitForm.utilities = 0
  quickSplitForm.ai_token_cost = 0
  quickSplitForm.other_costs = 0
  // 分摊范围跟随平台分段（唯一来源 quickSplitScope）
  quickSplitScope.platform_code = platformScope.value === 'all' ? '' : platformScope.value
  quickSplitScope.main_account_id = ''
}

const openQuickSplitDialog = () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  if (visibleMonthlyRows.value.length === 0) {
    ElMessage.warning('当前月份没有可拆分的店铺')
    return
  }

  resetQuickSplitForm()
  quickSplitDialogVisible.value = true
}

const handleApplyQuickSplit = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  // 行源与界面计数完全一致（同一 scope + 同一行源），杜绝「显示 N 家、实际改 M 家」
  const targets = resolveQuickSplitTargets(visibleMonthlyRows.value, quickSplitScope)

  if (targets.length === 0) {
    ElMessage.warning('当前范围没有可拆分的在营店铺')
    return
  }

  const scopeLabel = quickSplitScope.main_account_id
    ? `租户 ${quickSplitScope.main_account_id}`
    : quickSplitScope.platform_code === 'shopee'
      ? '仅 Shopee'
      : quickSplitScope.platform_code === 'tiktok'
        ? '仅 TikTok'
        : '全部在营店铺'

  try {
    await ElMessageBox.confirm(
      `将按「${scopeLabel}」共 ${targets.length} 家在营店铺平均拆分，并覆盖这些店铺的现有金额。是否继续？`,
      '确认快速拆分',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') {
      return
    }
    throw error
  }

  const rentAllocations = distributeEvenly(quickSplitForm.rent, targets.length)
  const marketingAllocations = distributeEvenly(quickSplitForm.marketing_fee, targets.length)
  const utilityAllocations = distributeEvenly(quickSplitForm.utilities, targets.length)
  const aiTokenAllocations = distributeEvenly(quickSplitForm.ai_token_cost, targets.length)
  const otherAllocations = distributeEvenly(quickSplitForm.other_costs, targets.length)

  // ⚠️ 只覆盖目标集合的行；范围外的既有金额保持不变
  targets.forEach((row, index) => {
    row.rent = rentAllocations[index]
    row.marketing_fee = marketingAllocations[index]
    row.utilities = utilityAllocations[index]
    row.ai_token_cost = aiTokenAllocations[index]
    row.other_costs = otherAllocations[index]
    updateRowTotal(row)
  })

  quickSplitDialogVisible.value = false
  ElMessage.success(`快速拆分已应用到 ${targets.length} 家店铺，可继续逐店修改后保存`)
}

// 保存单行
const handleSaveRow = async (row) => {
  if (!row.shop_id) {
    ElMessage.warning('请选择店铺')
    return
  }

  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }
  if (!isMeaningfulExpenseRow(row)) {
    ElMessage.warning('空白费用记录无需保存，请直接保留空白行')
    return
  }

  row.saving = true
  try {
    const payload = {
      platform_code: row.platform_code,
      shop_id: row.shop_id,
      year_month: selectedMonth.value,
      rent: Number(row.rent) || 0,
      marketing_fee: Number(row.marketing_fee) || 0,
      utilities: Number(row.utilities) || 0,
      ai_token_cost: Number(row.ai_token_cost) || 0,
      labor_cost: laborCostForPayload(row),
      other_costs: Number(row.other_costs) || 0,
      note: row.note || null
    }

    await api.post('/expenses', payload)
    await tryCompleteTaskFromExpenseRow(row, selectedMonth.value)
    ElMessage.success('保存成功')
    await loadMonthlyExpenses()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    row.saving = false
  }
}

// 删除单行
const handleDeleteRow = async (row) => {
  if (!row.id) {
    // 表格数据源是 visibleMonthlyRows（平台分段过滤后），$index 是过滤后的下标，
    // 不能直接拿来删全量数据 —— 按行对象定位。
    const targetIndex = monthlyTableData.value.indexOf(row)
    if (targetIndex >= 0) {
      monthlyTableData.value.splice(targetIndex, 1)
    }
    calculateMonthlySummary()
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${selectedMonth.value} / ${row.platform_code || '-'} / ${row.shop_name || row.shop_id} 的本月费用记录吗？删除后会保留一条空白编辑行，可重新保存恢复。`,
      '确认删除本月费用',
      { type: 'warning' }
    )

    await api.delete(`/expenses/${row.id}`)
    ElMessage.success('删除成功')
    await loadMonthlyExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(error.message || '删除失败')
    }
  }
}

// 批量保存
const handleBatchSave = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }

  const rowsToSave = monthlyTableData.value.filter(
    (row) =>
      row.shop_id &&
      (row.rent > 0 ||
        row.marketing_fee > 0 ||
        row.utilities > 0 ||
        row.ai_token_cost > 0 ||
        laborCostForPayload(row) > 0 ||
        row.other_costs > 0 ||
        (row.note && String(row.note).trim().length > 0))
  )

  if (rowsToSave.length === 0) {
    ElMessage.warning('没有需要保存的数据')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要批量保存 ${rowsToSave.length} 条费用记录吗？`,
      '确认批量保存',
      { type: 'info' }
    )

    batchSaving.value = true
    let successCount = 0
    let failCount = 0

    for (const row of rowsToSave) {
      try {
        const payload = {
          platform_code: row.platform_code,
          shop_id: row.shop_id,
          year_month: selectedMonth.value,
          rent: Number(row.rent) || 0,
          marketing_fee: Number(row.marketing_fee) || 0,
          utilities: Number(row.utilities) || 0,
          ai_token_cost: Number(row.ai_token_cost) || 0,
          labor_cost: laborCostForPayload(row),
          other_costs: Number(row.other_costs) || 0,
          note: row.note || null
        }

        await api.post('/expenses', payload)
        await tryCompleteTaskFromExpenseRow(row, selectedMonth.value)
        successCount++
      } catch (error) {
        console.error(`保存店铺 ${row.shop_name || row.shop_id} 失败:`, error)
        failCount++
      }
    }

    if (failCount === 0) {
      ElMessage.success(`成功保存 ${successCount} 条记录`)
    } else {
      ElMessage.warning(`成功保存 ${successCount} 条，失败 ${failCount} 条`)
    }

    await loadMonthlyExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量保存失败:', error)
      ElMessage.error(error.message || '批量保存失败')
    }
  } finally {
    batchSaving.value = false
  }
}

// ==================== 按店铺模式方法 ====================

// 店铺选择变化
const handleShopSelectChange = (key) => {
  // 目录条目：用 view-model 的行键口径匹配（平台 + 店铺账号 ID），跨平台同 id 不会撞车
  const shop = allShops.value.find((s) => buildExpenseRowKey(s) === key)
  selectedShopId.value = shop?.shop_id ?? null
  selectedShopPlatform.value = shop?.platform_code ?? ''
  if (selectedShopId.value) {
    loadShopExpenses()
  } else {
    shopTableData.value = []
    resetShopSummary()
  }
}

// 某年有费用记录的店铺集合：用于「按店铺」下拉把停用店也列出来
// ⚠️ 不能用 shopTableData 推导 —— 它只有当前选中店的行，会让停用店永远进不了下拉
const loadShopViewRecordedShops = async (year) => {
  if (!year) {
    shopViewRecordedIds.value = new Set()
    return
  }
  try {
    const res = await api.get('/expenses', {
      params: { year, page_size: 1000 }
    })
    shopViewRecordedIds.value = new Set((res.items || []).map((item) => item.shop_id))
  } catch (error) {
    console.error('加载年度店铺费用记录失败:', error)
    shopViewRecordedIds.value = new Set()
  }
}

// 加载店铺费用
const loadShopExpenses = async () => {
  // ⚠️ 必须在早退之前刷新年度记录集合，否则停用店永远进不了下拉
  await loadShopViewRecordedShops(selectedYear.value)
  if (!selectedShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }

  loading.value = true
  try {
    // 目录条目：用行键口径匹配（平台 + 店铺账号 ID）
    const selectedShop = allShops.value.find(
      (s) => buildExpenseRowKey(s) === selectedShopKey.value
    )
    const params = { shop_id: selectedShopId.value }
    if (selectedShop?.platform_code) {
      params.platform_code = selectedShop.platform_code
    }
    if (selectedYear.value) {
      params.year = selectedYear.value
    }

    const [res, deletedRes] = await Promise.all([
      api.get('/expenses/by-shop', { params }),
      api.get('/expenses/deleted', { params })
    ])

    // 处理数据
    shopTableData.value = (res.items || []).map((item) => ({
      ...normalizeExpenseRow(item),
      saving: false
    }))
    deletedShopData.value = deletedRes.items || []

    // 更新汇总
    if (res.summary) {
      shopSummary.total_amount = res.summary.total_amount || 0
      shopSummary.total_rent = res.summary.total_rent || 0
      shopSummary.total_marketing_fee = res.summary.total_marketing_fee || 0
      shopSummary.total_utilities = res.summary.total_utilities || 0
      shopSummary.total_ai_token_cost = res.summary.total_ai_token_cost || 0
      shopSummary.total_labor_cost = res.summary.total_labor_cost || 0
      shopSummary.total_other_costs = res.summary.total_other_costs || 0
      shopSummary.month_count = res.summary.month_count || 0
    } else {
      resetShopSummary()
    }
  } catch (error) {
    console.error('加载店铺费用失败:', error)
    ElMessage.error(error.message || '加载店铺费用失败')
    deletedShopData.value = []
  } finally {
    loading.value = false
  }
}

// 重置店铺汇总
const resetShopSummary = () => {
  shopSummary.total_amount = 0
  shopSummary.total_rent = 0
  shopSummary.total_marketing_fee = 0
  shopSummary.total_utilities = 0
  shopSummary.total_ai_token_cost = 0
  shopSummary.total_labor_cost = 0
  shopSummary.total_other_costs = 0
  shopSummary.month_count = 0
}

const handleRestoreRow = async (row) => {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(
      '恢复该费用记录？若这是占位行批次（备注以「[占位行清理」开头），恢复后会重新计入成本口径。',
      '确认恢复',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') return
    throw error
  }
  try {
    await api.post(`/expenses/${row.id}/restore`)
    ElMessage.success('恢复成功')
    await loadMonthlyExpenses()
  } catch (error) {
    console.error('恢复失败:', error)
    ElMessage.error(error.message || '恢复失败')
  }
}

// 更新店铺行合计
const updateShopRowTotal = (row) => {
  row.total_cost =
    (Number(row.rent) || 0) +
    (Number(row.marketing_fee) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.ai_token_cost) || 0) +
    (Number(row.labor_cost) || 0) +
    (Number(row.other_costs) || 0)
  row.total = row.total_cost
}

// 添加月份行
const handleAddMonthRow = () => {
  if (!selectedShopId.value) {
    ElMessage.warning('请先选择店铺')
    return
  }

  // 目录条目：用行键口径匹配（平台 + 店铺账号 ID）取回 platform_code
  const shop = allShops.value.find(
    (s) => buildExpenseRowKey(s) === selectedShopKey.value
  )

  shopTableData.value.push({
    id: null,
    platform_code: shop?.platform_code || selectedShopPlatform.value || null,
    shop_id: selectedShopId.value,
    year_month: '',
    rent: 0,
    marketing_fee: 0,
    utilities: 0,
    ai_token_cost: 0,
    labor_cost: 0,
    other_costs: 0,
    total_cost: 0,
    total: 0,
    note: '',
    attachments: [],
    saving: false
  })
}

// 保存店铺行
const handleSaveShopRow = async (row) => {
  if (!row.year_month) {
    ElMessage.warning('请选择月份')
    return
  }
  if (!isMeaningfulExpenseRow(row)) {
    ElMessage.warning('空白费用记录无需保存，请直接保留空白行')
    return
  }

  row.saving = true
  try {
    const payload = {
      platform_code: row.platform_code,
      shop_id: selectedShopId.value,
      year_month: row.year_month,
      rent: Number(row.rent) || 0,
      marketing_fee: Number(row.marketing_fee) || 0,
      utilities: Number(row.utilities) || 0,
      ai_token_cost: Number(row.ai_token_cost) || 0,
      labor_cost: laborCostForPayload(row),
      other_costs: Number(row.other_costs) || 0,
      note: row.note || null
    }

    await api.post('/expenses', payload)
    await tryCompleteTaskFromExpenseRow(row, row.year_month)
    ElMessage.success('保存成功')
    await loadShopExpenses()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    row.saving = false
  }
}

// 删除店铺行
const handleDeleteShopRow = async (row, index) => {
  if (!row.id) {
    shopTableData.value.splice(index, 1)
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${row.year_month} / ${row.platform_code || '-'} / ${selectedShopId.value} 的费用记录吗？删除后可重新新增同月记录恢复。`,
      '确认删除费用记录',
      { type: 'warning' }
    )

    await api.delete(`/expenses/${row.id}`)
    ElMessage.success('删除成功')
    await loadShopExpenses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(error.message || '删除失败')
    }
  }
}

const handleRestoreShopRow = async (row) => {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(
      '恢复该费用记录？若这是占位行批次（备注以「[占位行清理」开头），恢复后会重新计入成本口径。',
      '确认恢复',
      { type: 'warning' }
    )
  } catch (error) {
    if (error === 'cancel') return
    throw error
  }
  try {
    await api.post(`/expenses/${row.id}/restore`)
    ElMessage.success('恢复成功')
    await loadShopExpenses()
  } catch (error) {
    console.error('恢复失败:', error)
    ElMessage.error(error.message || '恢复失败')
  }
}

// ==================== 生命周期 ====================
onMounted(async () => {
  initTaskContext()
  // 默认选择当前月份和年份
  const now = new Date()
  if (!selectedMonth.value) {
    selectedMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  }
  selectedYear.value = `${now.getFullYear()}`
  // 必须先等店铺列表就绪，否则空白行不生成（首屏会少一整批店铺）
  await loadShops()
  // 默认选中第一家在营店（「按店铺查看」首屏不再空白）
  if (!selectedShopKey.value) {
    const firstShop = operatingShops.value[0]
    if (firstShop) {
      selectedShopKey.value = buildExpenseRowKey(firstShop)
      selectedShopId.value = firstShop.shop_id
      selectedShopPlatform.value = firstShop.platform_code || ''
    }
  }
  if (selectedShopId.value) {
    await loadShopExpenses()
  }
  await loadMonthlyExpenses()
})
</script>

<style scoped>
.expense-management {
  min-height: calc(100vh - var(--header-height));
}

.action-bar {
  display: flex;
  align-items: center;
}

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-label-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: bold;
  color: #303133;
}

.stat-value.primary {
  color: #409eff;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-card.monthly {
  border-left: 4px solid #409eff;
}

.stat-card.yearly {
  border-left: 4px solid #e6a23c;
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number__input) {
  text-align: right;
}

:deep(.el-tabs__item) {
  font-size: 15px;
}

:deep(.el-tabs__item .el-icon) {
  margin-right: 5px;
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

.quick-split-tip {
  margin-bottom: 12px;
  color: #606266;
  line-height: 1.6;
}

.quick-split-meta {
  margin-bottom: 8px;
  color: #909399;
  font-size: 13px;
}

.quick-split-form {
  margin-top: 16px;
}

.shop-option-secondary {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
</style>
