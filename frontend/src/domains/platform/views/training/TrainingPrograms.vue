<template>
  <div class="erp-page-container">
    <PageHeader
      title="培训项目"
      subtitle="查看正式培训项目、目标角色、承载平台、完成规则和外部学习入口"
      family="admin"
    >
      <template #actions>
        <el-button type="primary" @click="createProgramDialogVisible = true">新建培训项目</el-button>
      </template>
    </PageHeader>

    <el-card shadow="hover">
      <el-table :data="items" empty-text="暂无培训项目">
        <el-table-column prop="name" label="项目名称" min-width="180" />
        <el-table-column prop="category" label="分类" min-width="120" />
        <el-table-column prop="target_role" label="目标角色" min-width="220" />
        <el-table-column prop="external_platform" label="平台" min-width="100" />
        <el-table-column prop="learning_url" label="学习链接" min-width="180" show-overflow-tooltip />
        <el-table-column prop="exam_url" label="考试链接" min-width="180" show-overflow-tooltip />
        <el-table-column prop="materials_url" label="资料链接" min-width="180" show-overflow-tooltip />
        <el-table-column prop="completion_rule" label="完成规则" min-width="220" />
        <el-table-column prop="status" label="状态" min-width="100" />
      </el-table>
    </el-card>

    <el-dialog v-model="createProgramDialogVisible" title="新建培训项目" width="720px">
      <el-form :model="programForm" label-width="120px">
        <el-form-item label="项目名称">
          <el-input v-model="programForm.name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="programForm.category" />
        </el-form-item>
        <el-form-item label="目标角色">
          <el-input v-model="programForm.target_role" />
        </el-form-item>
        <el-form-item label="承载平台">
          <el-input v-model="programForm.external_platform" />
        </el-form-item>
        <el-form-item label="学习链接">
          <el-input v-model="programForm.learning_url" />
        </el-form-item>
        <el-form-item label="考试链接">
          <el-input v-model="programForm.exam_url" />
        </el-form-item>
        <el-form-item label="资料链接">
          <el-input v-model="programForm.materials_url" />
        </el-form-item>
        <el-form-item label="完成规则">
          <el-input v-model="programForm.completion_rule" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="状态">
          <el-input v-model="programForm.status" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createProgramDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateProgram">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const items = ref([])
const createProgramDialogVisible = ref(false)
const programForm = ref({
  name: '',
  category: '入职培训',
  target_role: '',
  external_platform: '飞书',
  learning_url: '',
  exam_url: '',
  materials_url: '',
  completion_rule: '',
  status: '待上线'
})

const resetProgramForm = () => {
  programForm.value = {
    name: '',
    category: '入职培训',
    target_role: '',
    external_platform: '飞书',
    learning_url: '',
    exam_url: '',
    materials_url: '',
    completion_rule: '',
    status: '待上线'
  }
}

const loadPrograms = async () => {
  const response = await trainingApi.getPrograms()
  items.value = response.items || []
}

const handleCreateProgram = async () => {
  const created = await trainingApi.createProgram(programForm.value)
  items.value = [...items.value, created]
  createProgramDialogVisible.value = false
  resetProgramForm()
  ElMessage.success('培训项目已创建')
}

onMounted(() => {
  void loadPrograms()
})
</script>
