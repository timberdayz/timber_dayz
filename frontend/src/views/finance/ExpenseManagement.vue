<template>
  <div class="expense-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px">
      费用管理
    </h1>

    <!-- 模式切换 Tab -->
    <el-tabs
      v-model="viewMode"
      @tab-change="handleModeChange"
      style="margin-bottom: 20px"
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
      <div class="action-bar" style="margin-bottom: 20px">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          placeholder="选择月份"
          value-format="YYYY-MM"
          size="default"
          style="width: 180px"
          @change="handleMonthChange"
        />
        <el-button
          type="primary"
          :icon="Plus"
          @click="handleAddAllShops"
          style="margin-left: 10px"
        >
          为所有店铺添加
        </el-button>
        <el-button
          type="success"
          @click="handleBatchSave"
          :loading="batchSaving"
          style="margin-left: 10px"
        >
          批量保存
        </el-button>
        <el-button
          :icon="Refresh"
          @click="loadMonthlyExpenses"
          style="margin-left: 10px"
        >
          刷新
        </el-button>
        <div style="flex: 1"></div>
      </div>

      <!-- 统计卡片（月度 + 年度） -->
      <el-row :gutter="20" style="margin-bottom: 20px">
        <el-col :span="4">
          <el-card class="stat-card monthly">
            <div class="stat-item">
              <div class="stat-label">本月总费用</div>
              <div class="stat-value primary">
                ¥{{ formatNumber(monthlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">年度累计</div>
              <div class="stat-value warning">
                ¥{{ formatNumber(yearlySummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月租金</div>
              <div class="stat-value">
                ¥{{ formatNumber(monthlySummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月工资</div>
              <div class="stat-value">
                ¥{{ formatNumber(monthlySummary.total_salary) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月水电</div>
              <div class="stat-value">
                ¥{{ formatNumber(monthlySummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">本月其他</div>
              <div class="stat-value">
                ¥{{ formatNumber(monthlySummary.total_other) }}
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
          :data="monthlyTableData"
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
                v-model="row.shop_id"
                placeholder="选择店铺"
                style="width: 100%"
                :disabled="!!row.id"
                @change="handleShopChange(row)"
              >
                <el-option
                  v-for="shop in availableShops"
                  :key="shop.shop_id"
                  :label="shop.shop_name"
                  :value="shop.shop_id"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="salary"
            label="工资(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.salary"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他成本(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total"
            label="合计(¥)"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>¥{{ formatNumber(row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row, $index }">
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
                @click="handleDeleteRow(row, $index)"
                :disabled="!row.id"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 按店铺查看模式 -->
    <div v-else-if="viewMode === 'shop'">
      <!-- 操作栏 -->
      <div class="action-bar" style="margin-bottom: 20px">
        <el-select
          v-model="selectedShopId"
          placeholder="选择店铺"
          style="width: 250px"
          @change="handleShopSelectChange"
          filterable
        >
          <el-option
            v-for="shop in availableShops"
            :key="shop.shop_id"
            :label="shop.shop_name"
            :value="shop.shop_id"
          />
        </el-select>
        <el-date-picker
          v-model="selectedYear"
          type="year"
          placeholder="选择年份"
          value-format="YYYY"
          size="default"
          style="width: 150px; margin-left: 10px"
          @change="loadShopExpenses"
        />
        <el-button
          :icon="Refresh"
          @click="loadShopExpenses"
          style="margin-left: 10px"
        >
          刷新
        </el-button>
        <div style="flex: 1"></div>
      </div>

      <!-- 店铺年度汇总卡片 -->
      <el-row :gutter="20" style="margin-bottom: 20px">
        <el-col :span="4">
          <el-card class="stat-card yearly">
            <div class="stat-item">
              <div class="stat-label">年度总费用</div>
              <div class="stat-value primary">
                ¥{{ formatNumber(shopSummary.total_amount) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">月均费用</div>
              <div class="stat-value">
                ¥{{
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
                ¥{{ formatNumber(shopSummary.total_rent) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度工资</div>
              <div class="stat-value">
                ¥{{ formatNumber(shopSummary.total_salary) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度水电</div>
              <div class="stat-value">
                ¥{{ formatNumber(shopSummary.total_utilities) }}
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card>
            <div class="stat-item">
              <div class="stat-label">年度其他</div>
              <div class="stat-value">
                ¥{{ formatNumber(shopSummary.total_other_costs) }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 店铺费用表格（按月份） -->
      <el-card>
        <el-table
          :data="shopTableData"
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
                style="width: 100%"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="rent"
            label="租金(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.rent"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="salary"
            label="工资(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.salary"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="utilities"
            label="水电费(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.utilities"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="other_costs"
            label="其他成本(¥)"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <el-input-number
                v-model="row.other_costs"
                :min="0"
                :precision="2"
                :controls="false"
                style="width: 100%"
                @change="updateShopRowTotal(row)"
              />
            </template>
          </el-table-column>
          <el-table-column
            prop="total"
            label="合计(¥)"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <strong>¥{{ formatNumber(row.total) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.id" type="success" size="small">已保存</el-tag>
              <el-tag v-else type="info" size="small">新增</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
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
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加新月份按钮 -->
        <div style="margin-top: 15px">
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
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Calendar, Shop } from "@element-plus/icons-vue";
import api from "@/api";

// ==================== 公共状态 ====================
const viewMode = ref("monthly"); // monthly | shop
const availableShops = ref([]);
const loading = ref(false);
const monthlyError = ref(null); // 月度数据加载错误状态
const shopError = ref(null); // 店铺数据加载错误状态

// ==================== 按月份查看模式 ====================
const selectedMonth = ref(null);
const monthlyTableData = ref([]);
const batchSaving = ref(false);

// 月度汇总
const monthlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_salary: 0,
  total_utilities: 0,
  total_other: 0,
});

// 年度汇总
const yearlySummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_salary: 0,
  total_utilities: 0,
  total_other_costs: 0,
});

// ==================== 按店铺查看模式 ====================
const selectedShopId = ref(null);
const selectedYear = ref(null);
const shopTableData = ref([]);

// 店铺汇总
const shopSummary = reactive({
  total_amount: 0,
  total_rent: 0,
  total_salary: 0,
  total_utilities: 0,
  total_other_costs: 0,
  month_count: 0,
});

// ==================== 公共方法 ====================
const formatNumber = (num) => {
  if (num === null || num === undefined) return "0.00";
  return Number(num).toFixed(2);
};

// 加载店铺列表
const loadShops = async () => {
  try {
    const data = await api.get("/expenses/shops");
    availableShops.value = Array.isArray(data)
      ? data
      : (data?.data ?? data ?? []);
  } catch (error) {
    console.error("加载店铺列表失败:", error);
    ElMessage.error(error.message || "加载店铺列表失败");
    availableShops.value = [];
  }
};

// 模式切换处理
const handleModeChange = (mode) => {
  if (mode === "monthly" && selectedMonth.value) {
    loadMonthlyExpenses();
  } else if (mode === "shop" && selectedShopId.value) {
    loadShopExpenses();
  }
};

// ==================== 按月份模式方法 ====================

// 加载月度费用
const loadMonthlyExpenses = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning("请先选择月份");
    return;
  }

  loading.value = true;
  monthlyError.value = null; // 重置错误状态
  try {
    // 并行加载月度数据和年度汇总
    const [monthlyRes, yearlyRes] = await Promise.all([
      api.get("/expenses", {
        params: { year_month: selectedMonth.value, page_size: 1000 },
      }),
      api.get("/expenses/summary/yearly", {
        params: { year: selectedMonth.value.substring(0, 4) },
      }),
    ]);

    // 处理月度数据
    const existingData = monthlyRes.items || [];
    const shopIdSet = new Set(existingData.map((item) => item.shop_id));

    // 为没有数据的店铺创建空白行
    const newRows = availableShops.value
      .filter((shop) => !shopIdSet.has(shop.shop_id))
      .map((shop) => ({
        id: null,
        shop_id: shop.shop_id,
        shop_name: shop.shop_name,
        year_month: selectedMonth.value,
        rent: 0,
        salary: 0,
        utilities: 0,
        other_costs: 0,
        total: 0,
        saving: false,
      }));

    // 合并现有数据和空白行，只保留当月数据
    monthlyTableData.value = [
      ...existingData
        .filter((item) => item.year_month === selectedMonth.value)
        .map((item) => ({
          ...item,
          shop_name:
            availableShops.value.find((s) => s.shop_id === item.shop_id)
              ?.shop_name || item.shop_id,
          saving: false,
        })),
      ...newRows,
    ];

    // 计算月度汇总（只计算已保存的数据）
    calculateMonthlySummary();

    // 更新年度汇总
    if (yearlyRes) {
      yearlySummary.total_amount = yearlyRes.total_amount || 0;
      yearlySummary.total_rent = yearlyRes.total_rent || 0;
      yearlySummary.total_salary = yearlyRes.total_salary || 0;
      yearlySummary.total_utilities = yearlyRes.total_utilities || 0;
      yearlySummary.total_other_costs = yearlyRes.total_other_costs || 0;
    }
  } catch (error) {
    console.error("加载费用数据失败:", error);
    // 设置错误状态，区分"无数据"和"加载失败"
    monthlyError.value = {
      message: error.message || "加载费用数据失败",
      recovery: error.recovery_suggestion || "请检查网络连接或联系管理员",
    };
    monthlyTableData.value = [];
    ElMessage.error(monthlyError.value.message);
  } finally {
    loading.value = false;
  }
};

// 计算月度汇总
const calculateMonthlySummary = () => {
  monthlySummary.total_amount = 0;
  monthlySummary.total_rent = 0;
  monthlySummary.total_salary = 0;
  monthlySummary.total_utilities = 0;
  monthlySummary.total_other = 0;

  // 只计算已保存的数据（有ID的行）
  monthlyTableData.value
    .filter((item) => item.id)
    .forEach((item) => {
      monthlySummary.total_amount += Number(item.total) || 0;
      monthlySummary.total_rent += Number(item.rent) || 0;
      monthlySummary.total_salary += Number(item.salary) || 0;
      monthlySummary.total_utilities += Number(item.utilities) || 0;
      monthlySummary.total_other += Number(item.other_costs) || 0;
    });
};

// 更新行合计
const updateRowTotal = (row) => {
  row.total =
    (Number(row.rent) || 0) +
    (Number(row.salary) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.other_costs) || 0);
  calculateMonthlySummary();
};

// 店铺选择变化
const handleShopChange = (row) => {
  const shop = availableShops.value.find((s) => s.shop_id === row.shop_id);
  if (shop) {
    row.shop_name = shop.shop_name;
  }
};

// 月份变化
const handleMonthChange = () => {
  if (selectedMonth.value) {
    loadMonthlyExpenses();
  } else {
    monthlyTableData.value = [];
    calculateMonthlySummary();
  }
};

// 为所有店铺添加空白行
const handleAddAllShops = () => {
  if (!selectedMonth.value) {
    ElMessage.warning("请先选择月份");
    return;
  }

  const existingShopIds = new Set(
    monthlyTableData.value.map((row) => row.shop_id),
  );
  const newRows = availableShops.value
    .filter((shop) => !existingShopIds.has(shop.shop_id))
    .map((shop) => ({
      id: null,
      shop_id: shop.shop_id,
      shop_name: shop.shop_name,
      year_month: selectedMonth.value,
      rent: 0,
      salary: 0,
      utilities: 0,
      other_costs: 0,
      total: 0,
      saving: false,
    }));

  if (newRows.length === 0) {
    ElMessage.info("所有店铺已有数据");
    return;
  }

  monthlyTableData.value.push(...newRows);
  ElMessage.success(`已为 ${newRows.length} 个店铺添加空白行`);
};

// 保存单行
const handleSaveRow = async (row) => {
  if (!row.shop_id) {
    ElMessage.warning("请选择店铺");
    return;
  }

  if (!selectedMonth.value) {
    ElMessage.warning("请先选择月份");
    return;
  }

  row.saving = true;
  try {
    const payload = {
      shop_id: row.shop_id,
      year_month: selectedMonth.value,
      rent: Number(row.rent) || 0,
      salary: Number(row.salary) || 0,
      utilities: Number(row.utilities) || 0,
      other_costs: Number(row.other_costs) || 0,
    };

    await api.post("/expenses", payload);
    ElMessage.success("保存成功");
    await loadMonthlyExpenses();
  } catch (error) {
    console.error("保存失败:", error);
    ElMessage.error(error.message || "保存失败");
  } finally {
    row.saving = false;
  }
};

// 删除单行
const handleDeleteRow = async (row, index) => {
  if (!row.id) {
    monthlyTableData.value.splice(index, 1);
    calculateMonthlySummary();
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${row.shop_name || row.shop_id} 的费用记录吗？`,
      "确认删除",
      { type: "warning" },
    );

    await api.delete(`/expenses/${row.id}`);
    ElMessage.success("删除成功");
    await loadMonthlyExpenses();
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除失败:", error);
      ElMessage.error(error.message || "删除失败");
    }
  }
};

// 批量保存
const handleBatchSave = async () => {
  if (!selectedMonth.value) {
    ElMessage.warning("请先选择月份");
    return;
  }

  const rowsToSave = monthlyTableData.value.filter(
    (row) =>
      row.shop_id &&
      (row.rent > 0 ||
        row.salary > 0 ||
        row.utilities > 0 ||
        row.other_costs > 0),
  );

  if (rowsToSave.length === 0) {
    ElMessage.warning("没有需要保存的数据");
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要批量保存 ${rowsToSave.length} 条费用记录吗？`,
      "确认批量保存",
      { type: "info" },
    );

    batchSaving.value = true;
    let successCount = 0;
    let failCount = 0;

    for (const row of rowsToSave) {
      try {
        const payload = {
          shop_id: row.shop_id,
          year_month: selectedMonth.value,
          rent: Number(row.rent) || 0,
          salary: Number(row.salary) || 0,
          utilities: Number(row.utilities) || 0,
          other_costs: Number(row.other_costs) || 0,
        };

        await api.post("/expenses", payload);
        successCount++;
      } catch (error) {
        console.error(`保存店铺 ${row.shop_name || row.shop_id} 失败:`, error);
        failCount++;
      }
    }

    if (failCount === 0) {
      ElMessage.success(`成功保存 ${successCount} 条记录`);
    } else {
      ElMessage.warning(`成功保存 ${successCount} 条，失败 ${failCount} 条`);
    }

    await loadMonthlyExpenses();
  } catch (error) {
    if (error !== "cancel") {
      console.error("批量保存失败:", error);
      ElMessage.error(error.message || "批量保存失败");
    }
  } finally {
    batchSaving.value = false;
  }
};

// ==================== 按店铺模式方法 ====================

// 店铺选择变化
const handleShopSelectChange = () => {
  if (selectedShopId.value) {
    loadShopExpenses();
  } else {
    shopTableData.value = [];
    resetShopSummary();
  }
};

// 加载店铺费用
const loadShopExpenses = async () => {
  if (!selectedShopId.value) {
    ElMessage.warning("请先选择店铺");
    return;
  }

  loading.value = true;
  try {
    const params = { shop_id: selectedShopId.value };
    if (selectedYear.value) {
      params.year = selectedYear.value;
    }

    const res = await api.get("/expenses/by-shop", { params });

    // 处理数据
    shopTableData.value = (res.items || []).map((item) => ({
      ...item,
      saving: false,
    }));

    // 更新汇总
    if (res.summary) {
      shopSummary.total_amount = res.summary.total_amount || 0;
      shopSummary.total_rent = res.summary.total_rent || 0;
      shopSummary.total_salary = res.summary.total_salary || 0;
      shopSummary.total_utilities = res.summary.total_utilities || 0;
      shopSummary.total_other_costs = res.summary.total_other_costs || 0;
      shopSummary.month_count = res.summary.month_count || 0;
    } else {
      resetShopSummary();
    }
  } catch (error) {
    console.error("加载店铺费用失败:", error);
    ElMessage.error(error.message || "加载店铺费用失败");
  } finally {
    loading.value = false;
  }
};

// 重置店铺汇总
const resetShopSummary = () => {
  shopSummary.total_amount = 0;
  shopSummary.total_rent = 0;
  shopSummary.total_salary = 0;
  shopSummary.total_utilities = 0;
  shopSummary.total_other_costs = 0;
  shopSummary.month_count = 0;
};

// 更新店铺行合计
const updateShopRowTotal = (row) => {
  row.total =
    (Number(row.rent) || 0) +
    (Number(row.salary) || 0) +
    (Number(row.utilities) || 0) +
    (Number(row.other_costs) || 0);
};

// 添加月份行
const handleAddMonthRow = () => {
  if (!selectedShopId.value) {
    ElMessage.warning("请先选择店铺");
    return;
  }

  shopTableData.value.push({
    id: null,
    shop_id: selectedShopId.value,
    year_month: "",
    rent: 0,
    salary: 0,
    utilities: 0,
    other_costs: 0,
    total: 0,
    saving: false,
  });
};

// 保存店铺行
const handleSaveShopRow = async (row) => {
  if (!row.year_month) {
    ElMessage.warning("请选择月份");
    return;
  }

  row.saving = true;
  try {
    const payload = {
      shop_id: selectedShopId.value,
      year_month: row.year_month,
      rent: Number(row.rent) || 0,
      salary: Number(row.salary) || 0,
      utilities: Number(row.utilities) || 0,
      other_costs: Number(row.other_costs) || 0,
    };

    await api.post("/expenses", payload);
    ElMessage.success("保存成功");
    await loadShopExpenses();
  } catch (error) {
    console.error("保存失败:", error);
    ElMessage.error(error.message || "保存失败");
  } finally {
    row.saving = false;
  }
};

// 删除店铺行
const handleDeleteShopRow = async (row, index) => {
  if (!row.id) {
    shopTableData.value.splice(index, 1);
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除 ${row.year_month} 的费用记录吗？`,
      "确认删除",
      { type: "warning" },
    );

    await api.delete(`/expenses/${row.id}`);
    ElMessage.success("删除成功");
    await loadShopExpenses();
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除失败:", error);
      ElMessage.error(error.message || "删除失败");
    }
  }
};

// ==================== 生命周期 ====================
onMounted(() => {
  loadShops();
  // 默认选择当前月份和年份
  const now = new Date();
  selectedMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  selectedYear.value = `${now.getFullYear()}`;
  loadMonthlyExpenses();
});
</script>

<style scoped>
.expense-management {
  padding: 20px;
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
</style>
