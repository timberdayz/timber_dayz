<template>
  <div class="target-person-management erp-page-container erp-page--admin">
    <PageHeader
      title="个人目标管理"
      subtitle="本页属于规划层目标入口，用于维护员工月度目标，不直接写入个人绩效结果层。"
      family="admin"
    />

    <el-alert
      title="个人绩效输入项已迁移到“绩效管理 / 人员”页面；本页保留为个人目标规划入口。"
      type="warning"
      :closable="false"
      style="margin-bottom: 16px;"
    />

    <el-card shadow="never" class="policy-card">
      <template #header>使用说明</template>
      <div class="policy-grid">
        <div class="policy-item">
          <div class="policy-label">当前定位</div>
          <div class="policy-text">本页用于维护个人销售、订单、客户等规划层目标，服务于目标对齐和过程管理。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">边界说明</div>
          <div class="policy-text">真正参与个人绩效计算的月度输入项，请到“绩效管理 / 人员”页面维护，避免目标与绩效混用。</div>
        </div>
        <div class="policy-item">
          <div class="policy-label">收入关系</div>
          <div class="policy-text">工资单和我的收入只认个人绩效结果与工资单，不直接读取这里的目标配置。</div>
        </div>
      </div>
    </el-card>

    <div class="action-bar">
      <el-date-picker
        v-model="filters.month"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        style="width: 160px;"
        @change="loadEmployeeTargets"
      />
      <el-select
        v-model="filters.employeeCode"
        clearable
        filterable
        placeholder="选择员工"
        style="width: 220px;"
        @change="loadEmployeeTargets"
      >
        <el-option
          v-for="item in employeeOptions"
          :key="item.employee_code"
          :label="`${item.name || item.employee_code} (${item.employee_code})`"
          :value="item.employee_code"
        />
      </el-select>
      <el-select
        v-model="filters.targetType"
        clearable
        placeholder="目标类型"
        style="width: 140px;"
        @change="loadEmployeeTargets"
      >
        <el-option label="全部类型" value="" />
        <el-option label="销售目标" value="sales" />
        <el-option label="订单目标" value="orders" />
        <el-option label="客户目标" value="customers" />
      </el-select>
      <el-button @click="goToPerformancePerson">前往人员绩效输入项</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建个人目标</el-button>
      <el-button :icon="Refresh" @click="loadEmployeeTargets">刷新</el-button>
    </div>

    <el-card>
      <el-table :data="targets.data" stripe v-loading="targets.loading" border class="erp-table">
        <el-table-column prop="employee_code" label="员工编号" width="140" />
        <el-table-column label="姓名" width="140">
          <template #default="{ row }">
            {{ employeeNameMap[row.employee_code] || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="year_month" label="月份" width="100" />
        <el-table-column prop="target_type" label="目标类型" width="120" />
        <el-table-column prop="target_value" label="目标值" width="120" align="right" />
      </el-table>
      <div v-if="targets.data.length === 0 && !targets.loading" class="empty-state">
        当前筛选条件下暂无个人目标记录。
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      title="新建个人目标"
      width="560px"
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
        <el-form-item label="员工" prop="employee_code">
          <el-select v-model="form.employee_code" filterable placeholder="选择员工" class="erp-w-full">
            <el-option
              v-for="item in employeeOptions"
              :key="item.employee_code"
              :label="`${item.name || item.employee_code} (${item.employee_code})`"
              :value="item.employee_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="月份" prop="year_month">
          <el-date-picker
            v-model="form.year_month"
            type="month"
            value-format="YYYY-MM"
            placeholder="选择月份"
            class="erp-w-full"
          />
        </el-form-item>
        <el-form-item label="目标类型" prop="target_type">
          <el-select v-model="form.target_type" placeholder="选择类型" class="erp-w-full">
            <el-option label="销售目标" value="sales" />
            <el-option label="订单目标" value="orders" />
            <el-option label="客户目标" value="customers" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标值" prop="target_value">
          <el-input-number v-model="form.target_value" :min="0" :precision="2" class="erp-w-full" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import api from '@/api'

const router = useRouter()

const targets = reactive({
  data: [],
  loading: false
})

const employeeOptions = ref([])
const filters = reactive({
  month: new Date().toISOString().slice(0, 7),
  employeeCode: '',
  targetType: ''
})

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({
  employee_code: '',
  year_month: new Date().toISOString().slice(0, 7),
  target_type: 'sales',
  target_value: 0
})

const formRules = {
  employee_code: [{ required: true, message: '请选择员工', trigger: 'change' }],
  year_month: [{ required: true, message: '请选择月份', trigger: 'change' }],
  target_type: [{ required: true, message: '请选择目标类型', trigger: 'change' }]
}

const employeeNameMap = computed(() => {
  const result = {}
  for (const item of employeeOptions.value) {
    result[item.employee_code] = item.name || item.employee_code
  }
  return result
})

function resetForm() {
  form.employee_code = ''
  form.year_month = filters.month || new Date().toISOString().slice(0, 7)
  form.target_type = 'sales'
  form.target_value = 0
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function goToPerformancePerson() {
  router.push('/hr-performance-management/person')
}

async function loadEmployees() {
  try {
    const response = await api.getHrEmployees({ page: 1, page_size: 500 })
    const data = Array.isArray(response)
      ? response
      : (response?.items || response?.data?.items || response?.data || [])
    employeeOptions.value = Array.isArray(data)
      ? data.filter((item) => !item.status || item.status === 'active')
      : []
  } catch (_error) {
    employeeOptions.value = []
  }
}

async function loadEmployeeTargets() {
  targets.loading = true
  try {
    const response = await api.getHrEmployeeTargets({
      employee_code: filters.employeeCode || undefined,
      year_month: filters.month || undefined,
      target_type: filters.targetType || undefined,
      page: 1,
      page_size: 200
    })
    targets.data = Array.isArray(response)
      ? response
      : (response?.items || response?.data?.items || response?.data || [])
  } catch (error) {
    targets.data = []
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载个人目标失败')
  } finally {
    targets.loading = false
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await api.createHrEmployeeTarget({
        employee_code: form.employee_code,
        year_month: form.year_month,
        target_type: form.target_type,
        target_value: Number(form.target_value || 0)
      })
      ElMessage.success('个人目标创建成功')
      dialogVisible.value = false
      await loadEmployeeTargets()
    } catch (error) {
      ElMessage.error(error?.response?.data?.detail || error?.message || '创建个人目标失败')
    } finally {
      submitting.value = false
    }
  })
}

onMounted(async () => {
  await loadEmployees()
  await loadEmployeeTargets()
})
</script>

<style scoped>
.target-person-management {
  min-height: calc(100vh - var(--header-height));
}

.policy-card {
  margin-bottom: 20px;
}

.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.policy-item {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.policy-label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.policy-text {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.action-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.empty-state {
  padding: 32px;
  text-align: center;
  color: #909399;
}
</style>
