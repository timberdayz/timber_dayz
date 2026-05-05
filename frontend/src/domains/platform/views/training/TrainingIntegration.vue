<template>
  <div class="erp-page-container">
    <PageHeader
      title="飞书接入"
      subtitle="配置飞书应用、绑定课程和考试 ID，并手动同步结果"
      family="admin"
    />

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="hover" class="integration-card">
          <template #header>
            <div class="card-header">
              <span>飞书配置</span>
              <el-button type="primary" @click="handleSaveConfig">保存配置</el-button>
            </div>
          </template>
          <el-form :model="configForm" label-width="120px">
            <el-form-item label="App ID">
              <el-input v-model="configForm.app_id" />
            </el-form-item>
            <el-form-item label="App Secret">
              <el-input v-model="configForm.app_secret" type="password" show-password />
            </el-form-item>
            <el-form-item label="Tenant Key">
              <el-input v-model="configForm.tenant_key" />
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="configForm.base_url" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="configForm.is_enabled" />
            </el-form-item>
            <el-alert
              v-if="configState.has_secret"
              type="success"
              :closable="false"
              title="已保存飞书密钥"
            />
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="hover" class="integration-card">
          <template #header>
            <div class="card-header">
              <span>手动同步结果</span>
              <el-button type="primary" @click="handleSyncResults">执行同步</el-button>
            </div>
          </template>
          <el-form :model="syncForm" label-width="120px">
            <el-form-item label="Program ID">
              <el-input v-model="syncForm.program_id" />
            </el-form-item>
            <el-form-item label="员工编号">
              <el-input v-model="syncForm.employee_code" />
            </el-form-item>
            <el-form-item label="考试成绩">
              <el-input-number v-model="syncForm.exam_score" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="是否通过">
              <el-switch v-model="syncForm.is_passed" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="syncForm.note" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="integration-card">
      <template #header>
        <div class="card-header">
          <span>培训项目飞书绑定</span>
          <el-button type="primary" @click="handleBindProgram">保存绑定</el-button>
        </div>
      </template>

      <el-form :model="bindingForm" label-width="120px" class="binding-form">
        <el-form-item label="Program ID">
          <el-select v-model="bindingForm.program_id" placeholder="选择培训项目" class="erp-w-320">
            <el-option
              v-for="item in programs"
              :key="item.program_id"
              :label="`${item.name} (${item.program_id})`"
              :value="item.program_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="课程 ID">
          <el-input v-model="bindingForm.course_id" />
        </el-form-item>
        <el-form-item label="考试 ID">
          <el-input v-model="bindingForm.exam_id" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const programs = ref([])
const configState = ref({ has_secret: false })
const configForm = ref({
  app_id: '',
  app_secret: '',
  tenant_key: '',
  base_url: 'https://open.feishu.cn',
  is_enabled: false
})

const bindingForm = ref({
  program_id: '',
  course_id: '',
  exam_id: ''
})

const syncForm = ref({
  program_id: '',
  employee_code: '',
  exam_score: 0,
  is_passed: true,
  note: ''
})

const loadPrograms = async () => {
  const response = await trainingApi.getPrograms()
  programs.value = response.items || []
}

const loadFeishuConfig = async () => {
  const response = await trainingApi.getFeishuConfig()
  configState.value = response
  configForm.value = {
    app_id: response.app_id || '',
    app_secret: '',
    tenant_key: response.tenant_key || '',
    base_url: response.base_url || 'https://open.feishu.cn',
    is_enabled: !!response.is_enabled
  }
}

const handleSaveConfig = async () => {
  const response = await trainingApi.saveFeishuConfig(configForm.value)
  configState.value = response
  configForm.value.app_secret = ''
  ElMessage.success('飞书配置已保存')
}

const handleBindProgram = async () => {
  if (!bindingForm.value.program_id) {
    ElMessage.warning('请先选择培训项目')
    return
  }
  await trainingApi.bindFeishu(bindingForm.value.program_id, {
    course_id: bindingForm.value.course_id,
    exam_id: bindingForm.value.exam_id
  })
  await loadPrograms()
  ElMessage.success('飞书绑定已保存')
}

const handleSyncResults = async () => {
  await trainingApi.syncFeishuResults({
    program_id: syncForm.value.program_id,
    results: [
      {
        employee_code: syncForm.value.employee_code,
        exam_score: syncForm.value.exam_score,
        is_passed: syncForm.value.is_passed,
        note: syncForm.value.note
      }
    ]
  })
  ElMessage.success('飞书结果已同步')
}

onMounted(() => {
  void loadPrograms()
  void loadFeishuConfig()
})
</script>

<style scoped>
.integration-card + .integration-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.binding-form {
  max-width: 760px;
}
</style>
