<!--
数据同步 - 文件详情页面（核心页面）
v4.6.0新增：独立的数据同步系统
包含：文件详情、表头行选择器、数据预览、原始表头字段列表
-->

<template>
  <div class="data-sync-file-detail erp-page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>📄 数据同步 - 文件详情</h1>
      <p>手动选择表头行，预览数据，保存模板</p>
    </div>

    <!-- 文件详情区域 -->
    <el-card class="file-info-card" style="margin-bottom: 20px">
      <template #header>
        <span>📋 文件详情</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="文件名">
          {{ fileInfo.file_name || "N/A" }}
        </el-descriptions-item>
        <el-descriptions-item label="平台">
          {{ fileInfo.platform || "N/A" }}
        </el-descriptions-item>
        <el-descriptions-item label="数据域">
          {{ fileInfo.domain || "N/A" }}
        </el-descriptions-item>
        <el-descriptions-item label="粒度">
          {{ fileInfo.granularity || "N/A" }}
        </el-descriptions-item>
        <el-descriptions-item label="子类型">
          {{ fileInfo.sub_domain || "N/A" }}
        </el-descriptions-item>
        <el-descriptions-item label="模板状态">
          <el-tag v-if="fileInfo.has_template" type="success" size="small">
            <el-icon><Check /></el-icon>
            有模板 ({{ fileInfo.template_name }})
          </el-tag>
          <el-tag v-else type="warning" size="small">
            <el-icon><Warning /></el-icon>
            无模板
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 表头行选择器 -->
    <el-card class="header-row-card" style="margin-bottom: 20px">
      <template #header>
        <span>📍 表头行选择</span>
      </template>
      <el-alert type="warning" :closable="false" style="margin-bottom: 16px">
        <template #title>
          <strong>⚠️ 重要：请手动选择正确的表头行！</strong>
        </template>
        <template #default>
          大多数文件表头行不在第一行，自动检测效果不佳。请根据文件实际情况选择正确的表头行。
        </template>
      </el-alert>
      <div style="display: flex; align-items: center; gap: 12px">
        <el-input-number
          v-model="headerRow"
          :min="0"
          :max="10"
          :step="1"
          controls-position="right"
          style="width: 150px"
        />
        <span>表头行 (0=Excel第1行, 1=Excel第2行, ...)</span>
        <el-button
          type="primary"
          @click="handlePreview"
          :loading="loadingPreview"
        >
          <el-icon><View /></el-icon>
          ◎预览数据
        </el-button>
        <el-button
          v-if="previewData.length > 0"
          @click="handleRepreview"
          :loading="loadingPreview"
        >
          <el-icon><Refresh /></el-icon>
          重新预览
        </el-button>
      </div>
    </el-card>

    <!-- 数据预览区域 -->
    <el-card
      v-if="showPreview && previewData.length > 0"
      class="preview-card"
      style="margin-bottom: 20px"
    >
      <template #header>
        <div
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
          "
        >
          <span
            >📊 数据预览 ({{ previewData.length }} 行 ×
            {{ headerColumns.length }} 列)</span
          >
          <el-button size="small" type="info" @click="showPreview = false">
            <el-icon><ArrowUp /></el-icon>
            收起预览
          </el-button>
        </div>
      </template>
      <div class="preview-table-container">
        <el-table
          :data="previewData"
          stripe
          border
          size="small"
          style="width: max-content; min-width: 100%"
        >
          <el-table-column
            v-for="(column, index) in headerColumns"
            :key="index"
            :prop="column"
            :label="column"
            width="150"
            min-width="120"
            show-overflow-tooltip
            :fixed="index === 0 ? 'left' : false"
          />
        </el-table>
      </div>
    </el-card>

    <!-- 原始表头字段列表区域 -->
    <el-card v-if="headerColumns.length > 0" class="header-columns-card">
      <template #header>
        <div
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
          "
        >
          <span>📋 原始表头字段列表 ({{ headerColumns.length }} 个字段)</span>
          <el-button
            type="primary"
            @click="handleSaveTemplate"
            :loading="savingTemplate"
            :disabled="
              headerColumns.length === 0 || deduplicationFields.length === 0
            "
          >
            <el-icon><Document /></el-icon>
            保存为模板
          </el-button>
        </div>
      </template>
      <el-table :data="headerColumnsWithSamples" stripe border>
        <el-table-column label="序号" type="index" width="60" align="center" />
        <el-table-column label="原始表头字段" min-width="200">
          <template #default="{ row }">
            <div style="font-weight: bold; color: #303133">{{ row.field }}</div>
          </template>
        </el-table-column>
        <el-table-column label="示例数据" min-width="200">
          <template #default="{ row }">
            <div
              v-if="row.sample"
              style="
                font-size: 12px;
                color: #909399;
                font-style: italic;
                padding: 4px 8px;
                background: #f5f7fa;
                border-radius: 4px;
              "
            >
              {{ row.sample }}
            </div>
            <span v-else style="color: #c0c4cc">暂无数据</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 空状态 -->
    <el-empty
      v-if="!fileInfo.file_name"
      description="请先选择文件"
      :image-size="120"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/api";
import DeduplicationFieldsSelector from "@/components/DeduplicationFieldsSelector.vue";

const route = useRoute();
const router = useRouter();

// 状态
const loadingPreview = ref(false);
const savingTemplate = ref(false);
const fileInfo = ref({});
const headerRow = ref(0);
const showPreview = ref(false);
const previewData = ref([]);
const headerColumns = ref([]);
const sampleData = ref({});
const deduplicationFields = ref([]); // v4.14.0新增：核心字段列表
const deduplicationFieldsValid = ref(false); // v4.14.0新增：核心字段验证状态

// 计算属性
const headerColumnsWithSamples = computed(() => {
  return headerColumns.value.map((field) => ({
    field,
    sample: sampleData.value[field] || null,
  }));
});

// 加载文件信息
const loadFileInfo = async () => {
  const fileId = route.params.fileId;
  if (!fileId) {
    ElMessage.warning("文件ID不存在");
    router.push("/data-sync/files");
    return;
  }

  try {
    // 修复：查询所有状态的文件（status: null），避免已同步/失败文件找不到
    const data = await api.getDataSyncFiles({ limit: 500, status: null });
    const file = data.files?.find((f) => f.id === parseInt(fileId));
    if (file) {
      fileInfo.value = file;
      // 如果有模板，使用模板的表头行
      if (
        file.has_template &&
        file.template_header_row !== undefined &&
        file.template_header_row !== null
      ) {
        headerRow.value = file.template_header_row;
      }
    } else {
      ElMessage.error("文件不存在或未注册");
      router.push("/data-sync/files");
    }
  } catch (error) {
    ElMessage.error(error.message || "加载文件信息失败");
  }
};

// 预览数据
const handlePreview = async () => {
  const fileId = route.params.fileId;
  if (!fileId) {
    ElMessage.warning("文件ID不存在");
    return;
  }

  loadingPreview.value = true;
  try {
    const data = await api.previewFileWithHeaderRow(
      parseInt(fileId),
      headerRow.value
    );
    previewData.value = data.preview_data || [];
    headerColumns.value = data.header_columns || [];
    sampleData.value = data.sample_data || {};
    showPreview.value = true;
    ElMessage.success("预览成功");
  } catch (error) {
    ElMessage.error(error.message || "预览失败");
  } finally {
    loadingPreview.value = false;
  }
};

// 重新预览
const handleRepreview = () => {
  handlePreview();
};

// v4.14.0新增：处理核心字段变化
const handleDeduplicationFieldsChange = (fields) => {
  deduplicationFields.value = fields;
};

// v4.14.0新增：处理验证状态变化
const handleValidationChange = (isValid) => {
  deduplicationFieldsValid.value = isValid;
};

// 保存模板
const handleSaveTemplate = async () => {
  if (headerColumns.value.length === 0) {
    ElMessage.warning("请先预览数据");
    return;
  }

  if (!fileInfo.value.platform || !fileInfo.value.domain) {
    ElMessage.warning("文件信息不完整，无法保存模板");
    return;
  }

  // v4.14.0新增：验证核心字段必填
  if (!deduplicationFields.value || deduplicationFields.value.length === 0) {
    ElMessage.warning("请至少选择1个核心字段用于数据去重");
    return;
  }

  savingTemplate.value = true;
  try {
    const result = await api.saveTemplate({
      platform: fileInfo.value.platform,
      dataDomain: fileInfo.value.domain, // 使用dataDomain参数名
      granularity: fileInfo.value.granularity,
      subDomain: fileInfo.value.sub_domain,
      headerColumns: headerColumns.value,
      headerRow: headerRow.value,
      deduplicationFields: deduplicationFields.value, // v4.14.0新增：核心字段列表（必填）
      template_name: `${fileInfo.value.platform}_${fileInfo.value.domain}_${
        fileInfo.value.granularity
      }_${fileInfo.value.sub_domain || "default"}_v1`,
    });

    // 检查响应结果
    if (result && (result.success || result.template_id)) {
      ElMessage.success(result.message || "模板保存成功");
      // 更新文件信息以刷新"可用模板"状态
      await loadFileInfo();
    } else {
      ElMessage.error(result?.message || "模板保存失败：未知错误");
    }
  } catch (error) {
    console.error("保存模板失败:", error);
    // 显示详细错误信息
    const errorMessage = error.message || error.detail || "保存模板失败";
    ElMessage.error(`模板保存失败: ${errorMessage}`);
  } finally {
    savingTemplate.value = false;
  }
};

// 初始化
onMounted(() => {
  loadFileInfo();
});
</script>

<style scoped>
.data-sync-file-detail {
  padding: 20px;
  /* ⭐ v4.16.0优化：确保页面容器不会超出视口宽度 */
  max-width: 100%;
  overflow-x: hidden;
}

.page-header {
  margin-bottom: 20px;
}

/* ⭐ v4.16.0优化：确保预览卡片不会超出页面宽度 */
.preview-card {
  max-width: 100%;
  overflow: hidden;
}

.preview-card :deep(.el-card__body) {
  max-width: 100%;
  overflow-x: hidden; /* 防止页面横向溢出 */
  overflow-y: visible; /* 允许纵向内容正常显示 */
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

/* 数据预览表格容器 - 固定宽度，防止页面过宽 */
/* 数据预览表格容器 - 固定宽度，防止页面过宽 */
.preview-table-container {
  width: 100%;
  max-width: 100%;
  height: 500px;
  overflow-x: auto;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  box-sizing: border-box;
  /* ⭐ v4.16.0优化：确保容器不会超出页面宽度 */
  position: relative;
  /* 优化滚动条样式 */
  scrollbar-width: thin;
  scrollbar-color: #c1c1c1 #f1f1f1;
}

/* Webkit浏览器滚动条样式 */
.preview-table-container::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.preview-table-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.preview-table-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.preview-table-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.preview-table-container .el-table {
  width: max-content;
  min-width: 100%;
  /* ⭐ v4.16.0优化：确保表格在容器内正确显示 */
  table-layout: auto;
}

/* 兼容旧类名 */
.table-scroll-container-wrapper {
  width: 100%;
  max-width: 100%;
  height: 500px;
  overflow-x: auto;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  box-sizing: border-box;
}

.table-scroll-container {
  width: max-content;
  min-width: 100%;
}
</style>
