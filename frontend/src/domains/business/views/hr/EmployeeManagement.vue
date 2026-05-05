<template>
  <div class="employee-management-page">
    <div class="page-header">
      <h1>我的档案</h1>
      <p>查看与维护您的联系方式等自助信息</p>
    </div>

    <el-card v-if="noProfile" class="empty-card">
      <el-empty description="您尚未关联员工档案，请联系管理员" />
    </el-card>

    <el-card v-else v-loading="loading" class="profile-card">
      <template #header>
        <span>基本信息（仅部分可自助修改）</span>
        <el-button v-if="!editing" type="primary" size="small" @click="editing = true">编辑</el-button>
        <template v-else>
          <el-button size="small" @click="editing = false">取消</el-button>
          <el-button type="primary" size="small" @click="saveProfile" :loading="saving">保存</el-button>
        </template>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="员工编号">{{ profile.employee_code }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ profile.name }}</el-descriptions-item>
        <el-descriptions-item label="部门">{{ getDepartmentName(profile.department_id) }}</el-descriptions-item>
        <el-descriptions-item label="职位">{{ getPositionName(profile.position_id) }}</el-descriptions-item>
        <el-descriptions-item label="入职日期">{{ profile.hire_date || '—' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ profile.status }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">可自助修改的联系方式</el-divider>
      <el-form v-if="editing" :model="form" label-width="120px" style="max-width: 560px">
        <el-form-item label="手机号码">
          <el-input v-model="form.phone" placeholder="手机号码" maxlength="32" show-word-limit />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="邮箱" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="现居地址">
          <el-input v-model="form.address" type="textarea" :rows="2" placeholder="现居地址" maxlength="512" show-word-limit />
        </el-form-item>
        <el-form-item label="紧急联系人">
          <el-input v-model="form.emergency_contact" placeholder="紧急联系人姓名" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="紧急联系人电话">
          <el-input v-model="form.emergency_phone" placeholder="紧急联系人电话" maxlength="32" show-word-limit />
        </el-form-item>
      </el-form>
      <el-descriptions v-else :column="2" border>
        <el-descriptions-item label="手机号码">{{ profile.phone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ profile.email || '—' }}</el-descriptions-item>
        <el-descriptions-item label="现居地址">{{ profile.address || '—' }}</el-descriptions-item>
        <el-descriptions-item label="紧急联系人">{{ profile.emergency_contact || '—' }}</el-descriptions-item>
        <el-descriptions-item label="紧急联系人电话">{{ profile.emergency_phone || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const loading = ref(true)
const saving = ref(false)
const noProfile = ref(false)
const editing = ref(false)
const profile = ref({})
const form = ref({
  phone: '',
  email: '',
  address: '',
  emergency_contact: '',
  emergency_phone: ''
})
const departments = ref([])
const positions = ref([])

function getDepartmentName(id) {
  if (id == null) return '—'
  const d = departments.value.find((x) => x.id === id)
  return d ? d.department_name : id
}
function getPositionName(id) {
  if (id == null) return '—'
  const p = positions.value.find((x) => x.id === id)
  return p ? p.position_name : id
}

async function loadProfile() {
  loading.value = true
  noProfile.value = false
  try {
    const res = await api.getHrMeProfile()
    const data = res?.data ?? res
    profile.value = data
    form.value = {
      phone: data.phone ?? '',
      email: data.email ?? '',
      address: data.address ?? '',
      emergency_contact: data.emergency_contact ?? '',
      emergency_phone: data.emergency_phone ?? ''
    }
  } catch (e) {
    if (e?.response?.status === 404) {
      noProfile.value = true
    } else {
      ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
    }
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  saving.value = true
  try {
    await api.putHrMeProfile(form.value)
    profile.value = { ...profile.value, ...form.value }
    editing.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const [deptRes, posRes] = await Promise.all([
      api.getHrDepartments({ page: 1, page_size: 500 }),
      api.getHrPositions({ page: 1, page_size: 500 })
    ])
    departments.value = deptRes?.data ?? deptRes ?? []
    positions.value = posRes?.data ?? posRes ?? []
  } catch (_) {
    departments.value = []
    positions.value = []
  }
  await loadProfile()
})
</script>

<style scoped>
.employee-management-page {
  padding: 20px;
}
.page-header {
  margin-bottom: 20px;
}
.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 1.5rem;
}
.page-header p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 0.9rem;
}
.empty-card,
.profile-card {
  max-width: 800px;
}
</style>
