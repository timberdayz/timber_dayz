<!--
数据同步 - 文件列表页面
v4.6.0新增：独立的数据同步系统
-->

<template>
  <div class="data-sync-files erp-page-container erp-page--admin">
    <PageHeader
      title="数据同步文件列表"
      subtitle="选择待同步文件，支持筛选、批量同步、失败重试和治理巡检。"
      family="admin"
    />

    <!-- 数据治理概览 -->
    <el-card class="governance-card erp-card">
      <template #header>
        <div class="card-header-row">
          <span>数据治理概览</span>
          <el-button
            size="small"
            @click="loadGovernanceStats"
            :loading="statsLoading"
          >
            <el-icon><Refresh /></el-icon>
            刷新统计
          </el-button>
        </div>
      </template>
      <div class="governance-stats">
        <div class="stat-item">
          <div class="stat-icon stat-icon-primary">
            <el-icon><Document /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">待同步文件</div>
            <div class="stat-value">
              {{ governanceStats.pending_count || 0 }}
            </div>
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-icon stat-icon-success">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">已同步文件</div>
            <div class="stat-value">
              {{ governanceStats.ingested_count || 0 }}
            </div>
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-icon stat-icon-danger">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">失败文件</div>
            <div class="stat-value">
              {{ governanceStats.failed_count || 0 }}
            </div>
          </div>
        </div>
      </div>
      <div class="governance-actions">
        <el-button
          type="primary"
          @click="handleRefreshFiles"
          :loading="refreshing"
        >
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button
          type="success"
          @click="handleSyncAll"
          :loading="syncingAll"
          :disabled="(governanceStats.pending_count || 0) === 0"
        >
          <el-icon><Upload /></el-icon>
          手动全部数据同步
        </el-button>
        <el-button
          type="warning"
          @click="retryAllFailed"
          :loading="syncing"
          :disabled="(governanceStats.failed_count || 0) === 0"
        >
          <el-icon><RefreshRight /></el-icon>
          批量重试失败
        </el-button>
        <el-button
          type="danger"
          @click="handleCleanupDatabase"
          :loading="cleaning"
        >
          <el-icon><Delete /></el-icon>
          清理数据库
        </el-button>
      </div>
    </el-card>

    <!-- 筛选器 -->
    <el-card class="filter-card erp-card">
      <el-form :inline="true" :model="filters">
        <el-form-item label="平台">
          <el-select
            v-model="filters.platform"
            placeholder="全部平台"
            clearable
            class="filter-select"
          >
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
            <el-option label="妙手ERP" value="miaoshou" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据域">
          <el-select
            v-model="filters.domain"
            placeholder="全部数据域"
            clearable
            class="filter-select"
          >
            <el-option label="订单" value="orders" />
            <el-option label="产品" value="products" />
            <el-option label="流量" value="analytics" />
            <el-option label="服务" value="services" />
            <el-option label="库存" value="inventory" />
          </el-select>
        </el-form-item>
        <!-- ⭐ 新增：子类型筛选（仅当数据域为services时显示） -->
        <el-form-item label="子类型" v-if="filters.domain === 'services'">
          <el-select
            v-model="filters.sub_domain"
            placeholder="全部子类型"
            clearable
            class="filter-select"
          >
            <el-option label="AI助手" value="ai_assistant" />
            <el-option label="人工聊天" value="agent" />
          </el-select>
        </el-form-item>
        <el-form-item label="粒度">
          <el-select
            v-model="filters.granularity"
            placeholder="全部粒度"
            clearable
            class="filter-select"
          >
            <el-option label="日度" value="daily" />
            <el-option label="周度" value="weekly" />
            <el-option label="月度" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            class="filter-select"
          >
            <el-option label="待同步" value="pending" />
            <el-option label="需要指派店铺" value="needs_shop" />
            <el-option label="部分成功" value="partial_success" />
            <el-option label="失败" value="failed" />
            <el-option label="隔离" value="quarantined" />
            <el-option label="已同步" value="ingested" />
            <el-option label="处理中" value="processing" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadFiles" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 同步进度显示 -->
    <el-card
      v-if="activeProgressTasks.length > 0"
      class="progress-card erp-card"
    >
      <template #header>
        <div class="card-header-row">
          <span
            ><el-icon class="is-loading"><Loading /></el-icon> 同步进度</span
          >
          <el-button size="small" text @click="clearCompletedTasks">
            清除已完成
          </el-button>
        </div>
      </template>
      <div class="progress-list">
        <div
          v-for="task in activeProgressTasks"
          :key="task.task_id"
          class="progress-item"
        >
          <div class="progress-header">
            <span class="task-id"
              >任务: {{ task.task_id?.substring(0, 8) }}...</span
            >
            <el-tag :type="getTaskStatusType(task.status)" size="small">
              {{ getTaskStatusText(task.status) }}
            </el-tag>
          </div>
          <div class="progress-info">
            <span
              >{{ task.processed_files || 0 }} /
              {{ task.total_files || 0 }} 文件</span
            >
            <span v-if="task.current_file" class="current-file">
              当前: {{ truncateFileName(task.current_file) }}
            </span>
          </div>
          <el-progress
            :percentage="task.percentage || 0"
            :status="
              task.status === 'completed'
                ? 'success'
                : task.status === 'failed'
                ? 'exception'
                : ''
            "
            :stroke-width="12"
            class="erp-mt-sm"
          />
          <div class="progress-stats" v-if="task.success_files !== undefined">
            <span class="stat-success"
              >成功: {{ task.success_files || 0 }}</span
            >
            <span class="stat-failed" v-if="task.failed_files"
              >失败: {{ task.failed_files }}</span
            >
            <span class="stat-skipped" v-if="task.skipped_files"
              >跳过: {{ task.skipped_files }}</span
            >
          </div>
        </div>
      </div>
    </el-card>

    <!-- 批量操作 -->
    <el-card
      class="action-card erp-card"
      v-if="selectedFiles.length > 0"
    >
      <div class="card-header-row">
        <span>已选择 {{ selectedFiles.length }} 个文件</span>
        <div>
          <el-button type="primary" @click="batchSync" :loading="syncing">
            <el-icon><Upload /></el-icon>
            同步选中
          </el-button>
          <el-button @click="selectedFiles = []">
            <el-icon><Close /></el-icon>
            取消选择
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 文件列表 -->
    <el-card>
      <template #header>
        <div class="card-header-row">
          <span>待同步文件（共 {{ files.length }} 个）</span>
          <el-button
            type="primary"
            @click="syncAll"
            :loading="syncing"
            :disabled="files.length === 0"
          >
            <el-icon><Upload /></el-icon>
            同步全部
          </el-button>
        </div>
      </template>

      <el-table
        :data="files"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        stripe
        class="erp-w-full"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="file_name" label="文件名" min-width="200" />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="domain" label="数据域" width="100" />
        <el-table-column prop="granularity" label="粒度" width="100" />
        <el-table-column prop="sub_domain" label="子类型" width="120" />
        <el-table-column label="模板状态" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.has_template" type="success" size="small">
              <el-icon><Check /></el-icon>
              有模板
            </el-tag>
            <el-tag v-else type="warning" size="small">
              <el-icon><Warning /></el-icon>
              无模板
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="同步状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="
                row.status === 'pending'
                  ? 'warning'
                  : row.status === 'ingested'
                  ? 'success'
                  : row.status === 'failed'
                  ? 'danger'
                  : row.status === 'processing'
                  ? 'primary'
                  : row.status === 'needs_shop'
                  ? 'info'
                  : row.status === 'partial_success'
                  ? 'warning'
                  : 'info'
              "
              size="small"
            >
              {{
                row.status === "pending"
                  ? "待同步"
                  : row.status === "ingested"
                  ? "已同步"
                  : row.status === "failed"
                  ? "失败"
                  : row.status === "processing"
                  ? "处理中"
                  : row.status === "needs_shop"
                  ? "需指派店铺"
                  : row.status === "partial_success"
                  ? "部分成功"
                  : row.status || "未知"
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="文件大小" width="100">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>
        <el-table-column prop="collected_at" label="采集时间" width="180" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="viewDetail(row.id)">
              <el-icon><View /></el-icon>
              详情
            </el-button>
            <el-button
              v-if="row.status === 'failed' || row.status === 'partial_success'"
              size="small"
              type="warning"
              @click="retrySingle(row.id)"
              :loading="syncingFiles.includes(row.id)"
            >
              <el-icon><RefreshRight /></el-icon>
              重试
            </el-button>
            <el-button
              v-else
              size="small"
              @click="syncSingle(row.id)"
              :loading="syncingFiles.includes(row.id)"
              :disabled="row.status === 'ingested'"
            >
              <el-icon><Upload /></el-icon>
              同步
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- v4.18.0新增：分页组件 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <!-- v4.18.0新增：同步历史记录 -->
    <el-card class="sync-history-card">
      <template #header>
        <div class="card-header-row">
          <span>同步历史记录</span>
          <el-button type="primary" link @click="() => loadSyncHistory(true)">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="syncHistory"
        v-loading="historyLoading"
        stripe
        class="erp-w-full"
        max-height="400"
      >
        <el-table-column prop="task_id" label="任务ID" width="200">
          <template #default="{ row }">
            <span class="mono-task-id"
              >{{ row.task_id?.substring(0, 16) }}...</span
            >
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="任务类型" width="120">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.task_type === 'bulk_ingest' ? 'primary' : 'info'"
            >
              {{ row.task_type === "bulk_ingest" ? "批量同步" : "单文件同步" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="getTaskStatusType(row.status)">
              {{ getTaskStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="row.file_progress || 0"
              :status="
                row.status === 'completed'
                  ? 'success'
                  : row.status === 'failed'
                  ? 'exception'
                  : undefined
              "
              :stroke-width="8"
            />
          </template>
        </el-table-column>
        <el-table-column label="文件统计" width="150">
          <template #default="{ row }">
            <span
              >{{ row.processed_files || 0 }} / {{ row.total_files || 0 }}</span
            >
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.start_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="end_time" label="结束时间" width="180">
          <template #default="{ row }">
            {{ row.end_time ? formatTime(row.end_time) : "-" }}
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            {{ calculateDuration(row.start_time, row.end_time) }}
          </template>
        </el-table-column>
        <el-table-column label="失败原因" width="300" min-width="200">
          <template #default="{ row }">
            <div v-if="row.status === 'failed' && row.message">
              <el-tooltip
                :content="row.message"
                placement="top"
                :disabled="row.message.length <= 50"
              >
                <span class="history-error-text">
                  {{ truncateText(row.message, 50) }}
                </span>
              </el-tooltip>
            </div>
            <span
              v-else-if="row.status === 'completed'"
              class="history-success-text"
            >
              同步成功
            </span>
            <span v-else class="history-muted-text"> - </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ⭐ v4.14.0新增：表头变化错误提示对话框 -->
    <el-dialog
      v-model="showHeaderChangeDialog"
      title="表头字段已变化"
      width="800px"
      :close-on-click-modal="false"
    >
      <div v-if="errorDetails">
        <el-alert type="error" :closable="false" class="erp-mb-lg">
          <strong>检测到表头字段变化，请更新模板后再同步。</strong>
          <br />
          任何表头变化都需要用户手动确认，系统不会自动匹配字段。
        </el-alert>

        <!-- 新增字段 -->
        <div
          v-if="errorDetails.added_fields?.length > 0"
          class="erp-mb-lg"
        >
          <h4 class="comparison-title comparison-title-success">
            <el-icon><Plus /></el-icon>
            新增字段（{{ errorDetails.added_fields.length }}个）：
          </h4>
          <div class="erp-flex-wrap-gap-sm">
            <el-tag
              v-for="field in errorDetails.added_fields"
              :key="field"
              type="success"
              size="large"
            >
              {{ field }}
            </el-tag>
          </div>
        </div>

        <!-- 删除字段 -->
        <div
          v-if="errorDetails.removed_fields?.length > 0"
          class="erp-mb-lg"
        >
          <h4 class="comparison-title comparison-title-danger">
            <el-icon><Minus /></el-icon>
            删除字段（{{ errorDetails.removed_fields.length }}个）：
          </h4>
          <div class="erp-flex-wrap-gap-sm">
            <el-tag
              v-for="field in errorDetails.removed_fields"
              :key="field"
              type="danger"
              size="large"
            >
              {{ field }}
            </el-tag>
          </div>
        </div>

        <!-- 字段顺序变化 -->
        <div
          v-if="
            !errorDetails.added_fields?.length &&
            !errorDetails.removed_fields?.length
          "
          class="erp-mb-lg"
        >
          <el-alert type="warning" :closable="false">
            字段顺序已变化（字段名相同但顺序不同）
          </el-alert>
        </div>

        <!-- 表头对比表格 -->
        <div class="erp-mt-lg" v-if="headerComparisonData.length > 0">
          <h4 class="erp-mb-sm">表头对比：</h4>
          <el-table
            :data="headerComparisonData"
            border
            size="small"
            max-height="300"
          >
            <el-table-column
              prop="index"
              label="序号"
              width="60"
              align="center"
            />
            <el-table-column prop="template_column" label="模板字段" />
            <el-table-column prop="current_column" label="文件字段" />
            <el-table-column
              prop="status"
              label="状态"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                <el-tag
                  :type="
                    row.status === 'match'
                      ? 'success'
                      : row.status === 'added'
                      ? 'success'
                      : 'danger'
                  "
                  size="small"
                >
                  {{
                    row.status === "match"
                      ? "匹配"
                      : row.status === "added"
                      ? "新增"
                      : row.status === "removed"
                      ? "删除"
                      : "变化"
                  }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 匹配率 -->
        <div class="erp-mt-lg">
          <strong>表头匹配率：</strong>
          <el-progress
            :percentage="errorDetails.match_rate || 0"
            :status="errorDetails.match_rate < 100 ? 'exception' : 'success'"
            class="erp-mt-sm"
          />
        </div>
      </div>

      <template #footer>
        <el-button @click="showHeaderChangeDialog = false">关闭</el-button>
        <el-button type="primary" @click="goToTemplateEditor">
          <el-icon><Edit /></el-icon>
          前往模板编辑
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Document,
  Check,
  Warning,
  Refresh,
  Upload,
  Delete,
  Plus,
  Minus,
  Edit,
  View,
  Loading,
  Close,
  RefreshRight,
} from "@element-plus/icons-vue";
import api from "@/api";
import PageHeader from "@/components/common/PageHeader.vue";

const router = useRouter();

// 状态
const loading = ref(false);
const syncing = ref(false);
const syncingFiles = ref([]);
const files = ref([]);
const selectedFiles = ref([]);
const statsLoading = ref(false);
const refreshing = ref(false);
const syncingAll = ref(false);
const cleaning = ref(false);
const governanceStats = ref({
  pending_count: 0,
  ingested_count: 0,
  failed_count: 0,
  total_count: 0,
});
const filters = ref({
  platform: null,
  domain: null,
  granularity: null,
  sub_domain: null,
  status: "pending", // ⭐ 修复：默认只显示待同步状态，符合"待同步文件"列表的语义
});

// v4.18.0新增：分页相关
const pagination = ref({
  page: 1,
  pageSize: 50,
  total: 0,
  totalPages: 1,
});

// v4.18.0新增：同步历史记录
const syncHistory = ref([]);
const historyLoading = ref(false);

// 进度轮询相关
const pollingTasks = ref(new Map()); // task_id -> interval_id
const taskProgress = ref(new Map()); // task_id -> progress_data

// 进度显示计算属性
const activeProgressTasks = computed(() => {
  return Array.from(taskProgress.value.values());
});

// 获取任务状态类型
const getTaskStatusType = (status) => {
  const types = {
    completed: "success",
    success: "success",
    failed: "danger",
    error: "danger",
    processing: "primary",
    running: "primary",
    pending: "warning",
  };
  return types[status] || "info";
};

// 获取任务状态文本
const getTaskStatusText = (status) => {
  const texts = {
    completed: "已完成",
    success: "成功",
    failed: "失败",
    error: "错误",
    processing: "处理中",
    running: "运行中",
    pending: "等待中",
  };
  return texts[status] || status;
};

// 截断文本（用于显示失败原因）
const truncateText = (text, maxLength = 50) => {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
};

// 截断文件名
const truncateFileName = (fileName) => {
  if (!fileName) return "";
  if (fileName.length <= 30) return fileName;
  return fileName.substring(0, 27) + "...";
};

// 清除已完成任务
const clearCompletedTasks = () => {
  const completedStatuses = ["completed", "success", "failed", "error"];
  for (const [taskId, progress] of taskProgress.value.entries()) {
    if (completedStatuses.includes(progress.status)) {
      taskProgress.value.delete(taskId);
      stopProgressPolling(taskId);
    }
  }
};

// 获取友好的错误信息
const getErrorMessage = (error) => {
  // 从错误对象中提取原始信息
  const rawMessage =
    error.message || error.detail || error.response?.data?.message || "";
  const errorCode = error.code || error.response?.data?.error?.code || "";
  const errorType = error.type || error.response?.data?.error?.type || "";
  const errorDetail = error.response?.data?.error?.detail || error.detail || "";

  // 错误类型映射
  const errorTypeMessages = {
    FILE_NOT_FOUND: "文件不存在或已被删除",
    TEMPLATE_NOT_FOUND: "未找到匹配的模板，请先创建模板",
    HEADER_MISMATCH: "文件表头与模板不匹配",
    PARSE_ERROR: "文件解析失败，请检查文件格式",
    PERMISSION_DENIED: "权限不足",
    DATABASE_ERROR: "数据库操作失败",
    VALIDATION_ERROR: "数据验证失败",
    NETWORK_ERROR: "网络连接失败，请检查网络",
    TIMEOUT: "操作超时，请稍后重试",
  };

  // HTTP状态码映射
  const httpStatusMessages = {
    400: "请求参数错误",
    401: "未登录或登录已过期",
    403: "无权限执行此操作",
    404: "资源不存在",
    500: "服务器内部错误",
    502: "服务暂时不可用",
    503: "服务繁忙，请稍后重试",
    504: "请求超时",
  };

  // 优先使用错误类型映射
  if (errorType && errorTypeMessages[errorType]) {
    return errorTypeMessages[errorType];
  }

  // 使用HTTP状态码映射
  const httpStatus = error.response?.status || error.code;
  if (httpStatus && httpStatusMessages[httpStatus]) {
    return httpStatusMessages[httpStatus];
  }

  // 使用原始消息，但做一些友好化处理
  if (rawMessage) {
    // 移除技术性前缀
    let friendlyMessage = rawMessage
      .replace(/^\[.*?\]\s*/, "") // 移除[xxx]前缀
      .replace(/^Error:\s*/i, ""); // 移除Error:前缀

    // 如果消息太长，截断显示
    if (friendlyMessage.length > 100) {
      friendlyMessage = friendlyMessage.substring(0, 100) + "...";
    }

    return friendlyMessage;
  }

  return "同步失败，请稍后重试";
};

// ⭐ v4.14.0新增：表头变化对话框相关
const showHeaderChangeDialog = ref(false);
const errorDetails = ref(null);
const headerComparisonData = ref([]);

// 构建表头对比数据
const buildHeaderComparison = (templateColumns, currentColumns) => {
  const maxLength = Math.max(templateColumns.length, currentColumns.length);
  const comparison = [];

  for (let i = 0; i < maxLength; i++) {
    const templateCol = templateColumns[i] || "";
    const currentCol = currentColumns[i] || "";

    let status = "match";
    if (templateCol && !currentCol) {
      status = "removed";
    } else if (!templateCol && currentCol) {
      status = "added";
    } else if (templateCol !== currentCol) {
      status = "changed";
    }

    comparison.push({
      index: i + 1,
      template_column: templateCol,
      current_column: currentCol,
      status: status,
    });
  }

  return comparison;
};

// 前往模板编辑页面
const goToTemplateEditor = () => {
  router.push("/field-mapping");
  showHeaderChangeDialog.value = false;
};

// 加载文件列表
// ⭐ v4.19.0修复：支持后台刷新，避免全局阻塞
const loadFiles = async (showLoading = true) => {
  // 防重复加载
  if (loading.value && showLoading) {
    return;
  }

  if (showLoading) {
    loading.value = true;
  }

  try {
    // v4.18.0: 支持分页参数
    const params = {
      ...filters.value,
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
    };

    // ⭐ v4.19.0新增：添加超时机制，避免长时间阻塞
    const API_TIMEOUT = 10000; // 10秒超时

    const data = await Promise.race([
      api.getDataSyncFiles(params),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("加载文件列表超时")), API_TIMEOUT)
      ),
    ]);

    files.value = data.files || [];
    // 更新分页信息
    pagination.value.total = data.total || 0;
    pagination.value.totalPages = data.total_pages || 1;
    pagination.value.page = data.page || 1;
  } catch (error) {
    if (error.message !== "加载文件列表超时") {
      if (showLoading) {
        ElMessage.error(error.message || "加载文件列表失败");
      } else {
        console.error("后台刷新文件列表失败:", error);
      }
    } else {
      console.warn("加载文件列表超时，但可能仍在后台加载");
    }
  } finally {
    if (showLoading) {
      loading.value = false;
    }
  }
};

// v4.18.0新增：分页切换
const handlePageChange = (newPage) => {
  pagination.value.page = newPage;
  loadFiles();
};

// v4.18.0新增：每页数量切换
const handlePageSizeChange = (newSize) => {
  pagination.value.pageSize = newSize;
  pagination.value.page = 1; // 重置到第一页
  loadFiles();
};

// v4.18.0新增：加载同步历史记录
// ⭐ v4.19.0修复：支持后台刷新，避免阻塞UI
const loadSyncHistory = async (showLoading = false) => {
  // 防重复加载
  if (historyLoading.value && showLoading) {
    return;
  }

  if (showLoading) {
    historyLoading.value = true;
  }

  try {
    const data = await api.getSyncHistory({ limit: 50 });
    syncHistory.value = data || [];
  } catch (error) {
    console.error("加载同步历史失败:", error);
    // 不显示错误提示，历史记录加载失败不影响主功能
  } finally {
    if (showLoading) {
      historyLoading.value = false;
    }
  }
};

// v4.18.0新增：格式化时间
const formatTime = (timeStr) => {
  if (!timeStr) return "-";

  // ⭐ 修复：如果时间字符串没有时区信息，假设是UTC时间，添加Z
  let dateStr = timeStr;
  if (
    !timeStr.endsWith("Z") &&
    !timeStr.includes("+") &&
    !timeStr.match(/[+-]\d{2}:\d{2}$/)
  ) {
    // 没有时区信息，假设是UTC，添加Z
    dateStr = timeStr + "Z";
  }

  const date = new Date(dateStr);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

// v4.18.0新增：计算耗时
const calculateDuration = (startTime, endTime) => {
  if (!startTime) return "-";
  const start = new Date(startTime);
  const end = endTime ? new Date(endTime) : new Date();
  const diffMs = end - start;

  if (diffMs < 1000) {
    return `${diffMs}ms`;
  } else if (diffMs < 60000) {
    return `${Math.round(diffMs / 1000)}s`;
  } else if (diffMs < 3600000) {
    const mins = Math.floor(diffMs / 60000);
    const secs = Math.round((diffMs % 60000) / 1000);
    return `${mins}m ${secs}s`;
  } else {
    const hours = Math.floor(diffMs / 3600000);
    const mins = Math.round((diffMs % 3600000) / 60000);
    return `${hours}h ${mins}m`;
  }
};

// 重置筛选器
const resetFilters = () => {
  filters.value = {
    platform: null,
    domain: null,
    granularity: null,
    sub_domain: null,
    status: "pending", // ⭐ 修复：重置时也默认只显示待同步状态
  };
  pagination.value.page = 1; // v4.18.0: 重置到第一页
  loadFiles();
};

// ⭐ 新增：监听数据域变化，当不是services时自动清空子类型筛选
watch(
  () => filters.value.domain,
  (newDomain) => {
    if (newDomain !== "services") {
      filters.value.sub_domain = null;
    }
  }
);

// 选择变化
const handleSelectionChange = (selection) => {
  selectedFiles.value = selection.map((f) => f.id);
};

// 查看详情
const viewDetail = (fileId) => {
  router.push(`/data-sync/file-detail/${fileId}`);
};

// 单文件同步 v4.18.0更新：改为异步处理，支持进度轮询
// ⭐ v4.18.2修复：符合异步架构的单文件同步
const syncSingle = async (fileId) => {
  // ⭐ 关键修改：立即标记为"提交中"（不等待API响应）
  syncingFiles.value.push(fileId);

  // ⭐ 关键修改：添加超时机制
  const API_TIMEOUT = 5000; // 5秒超时

  try {
    const result = await Promise.race([
      api.startSingleAutoIngest(fileId, true, true, true),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("API响应超时")), API_TIMEOUT)
      ),
    ]);

    // ⭐ v4.18.2修复：立即处理响应，启动轮询
    // ⭐ v4.19.6修复：兼容pending状态（数据库约束允许的状态）
    if (result?.task_id && (result?.status === "submitted" || result?.status === "pending")) {
      ElMessage.info(`同步任务已提交: ${result.file_name || fileId}`);

      // ⭐ 关键修改：立即启动轮询，不等待
      startProgressPolling(result.task_id);

      // ⭐ v4.19.0修复：移除任务提交后的自动刷新
      // 任务进行中，文件状态不会立即改变，不需要刷新
      // 只在任务完成时刷新（在 pollTaskProgress 中处理）

      return;
    }

    // 兼容旧模式：同步返回结果
    // ⭐ v4.14.0新增：检查是否有表头变化错误
    if (result?.error_code === "HEADER_CHANGED") {
      errorDetails.value = result.error_details || {};

      // 构建表头对比数据
      if (
        result.error_details?.template_columns &&
        result.error_details?.current_columns
      ) {
        headerComparisonData.value = buildHeaderComparison(
          result.error_details.template_columns,
          result.error_details.current_columns
        );
      }

      showHeaderChangeDialog.value = true;
      return;
    }

    // 检查响应结果（统一响应格式：{success, data, message}）
    if (result) {
      // 如果result是响应拦截器处理后的data字段
      if (result.success === false) {
        // ⭐ v4.14.0新增：检查是否是表头变化错误
        if (result.error_code === "HEADER_CHANGED") {
          errorDetails.value = result.error_details || {};

          // 构建表头对比数据
          if (
            result.error_details?.template_columns &&
            result.error_details?.current_columns
          ) {
            headerComparisonData.value = buildHeaderComparison(
              result.error_details.template_columns,
              result.error_details.current_columns
            );
          }

          showHeaderChangeDialog.value = true;
          return;
        }

        ElMessage.error(result.message || result.detail || "同步失败");
      } else if (result.success === true || result.status === "success") {
        ElMessage.success(result.message || "同步成功");
        // ⭐ v4.19.0修复：后台刷新，不显示loading
        setTimeout(async () => {
          await loadFiles(false);
          await loadGovernanceStats(false);
        }, 500);
      } else {
        // 兼容旧格式：直接检查status字段
        if (result.status === "success") {
          ElMessage.success(result.message || "同步成功");
          setTimeout(async () => {
            await loadFiles(false);
            await loadGovernanceStats(false);
          }, 500);
        } else {
          ElMessage.error(result.message || "同步失败");
        }
      }
    } else {
      ElMessage.error("同步失败：未知错误");
    }
  } catch (error) {
    // ⭐ 关键修改：超时错误不阻塞UI
    if (error.message === "API响应超时") {
      ElMessage.warning("API响应超时，但任务可能已提交，请查看任务进度");
      // 尝试启动轮询（使用fileId估算taskId）
      const estimatedTaskId = `single_file_${fileId}_${Date.now()}`;
      startProgressPolling(estimatedTaskId);
      return;
    }

    console.error("单文件同步失败:", error);

    // ⭐ v4.14.0新增：检查响应中的表头变化错误
    // 检查方式1：从error.data中获取（新格式）
    if (
      error.data?.error_code === "HEADER_CHANGED" ||
      error.error_code === "HEADER_CHANGED"
    ) {
      const errorData = error.data || error.response?.data?.data || {};
      errorDetails.value = errorData.error_details || errorData || {};

      // 构建表头对比数据
      if (
        errorDetails.value.template_columns &&
        errorDetails.value.current_columns
      ) {
        headerComparisonData.value = buildHeaderComparison(
          errorDetails.value.template_columns,
          errorDetails.value.current_columns
        );
      } else if (errorData.header_changes) {
        // 从header_changes中获取
        const headerChanges = errorData.header_changes || {};
        errorDetails.value = {
          ...errorDetails.value,
          template_columns: headerChanges.template_columns || [],
          current_columns: headerChanges.current_columns || [],
          added_fields: headerChanges.added_fields || [],
          removed_fields: headerChanges.removed_fields || [],
          match_rate: headerChanges.match_rate || 0,
        };
        if (
          errorDetails.value.template_columns &&
          errorDetails.value.current_columns
        ) {
          headerComparisonData.value = buildHeaderComparison(
            errorDetails.value.template_columns,
            errorDetails.value.current_columns
          );
        }
      }

      showHeaderChangeDialog.value = true;
      return;
    }

    // 检查方式2：从error.response.data中获取（旧格式兼容）
    if (error.response?.data?.data?.error_code === "HEADER_CHANGED") {
      const errorData = error.response.data.data;
      errorDetails.value = errorData.error_details || {};

      // 构建表头对比数据
      if (
        errorDetails.value.template_columns &&
        errorDetails.value.current_columns
      ) {
        headerComparisonData.value = buildHeaderComparison(
          errorDetails.value.template_columns,
          errorDetails.value.current_columns
        );
      }

      showHeaderChangeDialog.value = true;
      return;
    }

    // 显示友好的错误信息
    const errorMsg = getErrorMessage(error);
    ElMessage.error(errorMsg);
  }
  // ⭐ 关键修改：注意：不要在这里移除syncingFiles
  // 应该在轮询完成时移除（在 pollTaskProgress 中处理）
};

// ⭐ v4.18.2修复：重试失败文件，符合异步架构
const retrySingle = async (fileId) => {
  syncingFiles.value.push(fileId);

  // ⭐ 关键修改：添加超时机制
  const API_TIMEOUT = 5000;

  try {
    const result = await Promise.race([
      api.startSingleAutoIngest(fileId, true, true, true),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("API响应超时")), API_TIMEOUT)
      ),
    ]);

    // v4.18.0: 异步模式 - 返回task_id，启动轮询
    if (result?.task_id && result?.status === "submitted") {
      ElMessage.info(`重试任务已提交: ${result.file_name || fileId}`);

      // 启动进度轮询
      startProgressPolling(result.task_id);

      // ⭐ v4.19.0修复：移除任务提交后的自动刷新
      // 任务进行中，文件状态不会立即改变，不需要刷新
      // 只在任务完成时刷新（在 pollTaskProgress 中处理）

      return;
    }

    // 兼容旧模式
    if (result) {
      if (result.success === false) {
        ElMessage.error(result.message || "重试失败");
      } else if (result.success === true || result.status === "success") {
        ElMessage.success("重试成功");
        // ⭐ v4.19.0修复：后台刷新，不显示loading
        setTimeout(async () => {
          await loadFiles(false);
          await loadGovernanceStats(false);
        }, 500);
      }
    }
  } catch (error) {
    if (error.message === "API响应超时") {
      ElMessage.warning("API响应超时，但任务可能已提交，请查看任务进度");
      const estimatedTaskId = `single_file_${fileId}_${Date.now()}`;
      startProgressPolling(estimatedTaskId);
      return;
    }

    console.error("重试失败:", error);
    const errorMsg = getErrorMessage(error);
    ElMessage.error(errorMsg);
  }
  // ⭐ 关键修改：注意：不要在这里移除syncingFiles
  // 应该在轮询完成时移除（在 pollTaskProgress 中处理）
};

// 批量重试失败文件
const retryAllFailed = async () => {
  // 获取所有失败的文件
  const failedFiles = files.value.filter(
    (f) => f.status === "failed" || f.status === "partial_success"
  );

  if (failedFiles.length === 0) {
    ElMessage.info("没有失败的文件需要重试");
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要重试所有 ${failedFiles.length} 个失败文件吗？`,
      "确认批量重试",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    );

    // ⭐ v4.18.2修复：不设置 syncing.value = true（避免阻塞UI）
    // syncing.value = true  // ❌ 删除这行

    // ⭐ 关键修改：添加超时机制
    const API_TIMEOUT = 5000;

    // 调用批量同步API
    const result = await Promise.race([
      api.syncBatchByFileIds({
        fileIds: failedFiles.map((f) => f.id),
        onlyWithTemplate: true,
        allowQuarantine: true,
        useTemplateHeaderRow: true,
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("API响应超时")), API_TIMEOUT)
      ),
    ]);

    if (result && result.task_id) {
      ElMessage.success(`批量重试任务已启动（${result.total_files}个文件）`);
      startProgressPolling(result.task_id);

      // ⭐ v4.19.0修复：移除任务提交后的自动刷新
      // 任务进行中，文件状态不会立即改变，不需要刷新
      // 只在任务完成时刷新（在 pollTaskProgress 中处理）
    } else {
      ElMessage.error(result?.message || "批量重试失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      if (error.message === "API响应超时") {
        ElMessage.warning("API响应超时，但任务可能已提交，请查看任务进度");
      } else {
        console.error("批量重试失败:", error);
        ElMessage.error(error.message || "批量重试失败");
      }
    }
  }
  // ⭐ 关键修改：不设置 syncing.value = false（因为已经移除了）
};

// 批量同步
const batchSync = async () => {
  if (selectedFiles.value.length === 0) {
    ElMessage.warning("请先选择文件");
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要同步选中的 ${selectedFiles.value.length} 个文件吗？`,
      "确认批量同步",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    );

    // ⭐ v4.18.2修复：不设置 syncing.value = true（避免阻塞UI）
    // syncing.value = true  // ❌ 删除这行

    // ⭐ 关键修改：添加超时机制
    const API_TIMEOUT = 5000;

    // 调用批量同步API
    const result = await Promise.race([
      api.syncBatchByFileIds({
        fileIds: selectedFiles.value,
        onlyWithTemplate: true,
        allowQuarantine: true,
        useTemplateHeaderRow: true,
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("API响应超时")), API_TIMEOUT)
      ),
    ]);

    if (result && result.task_id) {
      ElMessage.success(
        result.message || `批量同步任务已启动（${result.total_files}个文件）`
      );

      // 清空选择
      selectedFiles.value = [];

      // 开始轮询进度
      startProgressPolling(result.task_id);

      // ⭐ v4.19.0修复：移除任务提交后的自动刷新
      // 任务进行中，文件状态不会立即改变，不需要刷新
      // 只在任务完成时刷新（在 pollTaskProgress 中处理）
    } else {
      ElMessage.error(result?.message || "批量同步失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      if (error.message === "API响应超时") {
        ElMessage.warning("API响应超时，但任务可能已提交，请查看任务进度");
      } else {
        console.error("批量同步失败:", error);
        const errorMessage = error.message || error.detail || "批量同步失败";
        ElMessage.error(`批量同步失败: ${errorMessage}`);
      }
    }
  }
  // ⭐ 关键修改：不设置 syncing.value = false（因为已经移除了）
};

// 同步全部（当前列表中的所有文件）
const syncAll = async () => {
  if (files.value.length === 0) {
    ElMessage.warning("没有可同步的文件");
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要同步全部 ${files.value.length} 个文件吗？`,
      "确认同步全部",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    );

    // ⭐ v4.18.2修复：不设置 syncing.value = true（避免阻塞UI）
    // syncing.value = true  // ❌ 删除这行

    // 获取当前列表中的所有文件ID
    const fileIds = files.value.map((f) => f.id);

    // ⭐ 关键修改：添加超时机制
    const API_TIMEOUT = 5000;

    // 调用批量同步API
    const result = await Promise.race([
      api.syncBatchByFileIds({
        fileIds: fileIds,
        onlyWithTemplate: true,
        allowQuarantine: true,
        useTemplateHeaderRow: true,
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("API响应超时")), API_TIMEOUT)
      ),
    ]);

    if (result && result.task_id) {
      ElMessage.success(
        result.message || `批量同步任务已启动（${result.total_files}个文件）`
      );

      // 立即开始轮询进度
      startProgressPolling(result.task_id);

      // ⭐ v4.19.0修复：移除任务提交后的自动刷新
      // 任务进行中，文件状态不会立即改变，不需要刷新
      // 只在任务完成时刷新（在 pollTaskProgress 中处理）
    } else {
      ElMessage.error(result?.message || "同步全部失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      if (error.message === "API响应超时") {
        ElMessage.warning("API响应超时，但任务可能已提交，请查看任务进度");
      } else {
        console.error("同步全部失败:", error);
        const errorMessage = error.message || error.detail || "同步全部失败";
        ElMessage.error(`同步全部失败: ${errorMessage}`);
      }
    }
  }
  // ⭐ 关键修改：不设置 syncing.value = false（因为已经移除了）
};

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
};

// 加载数据治理统计
// ⭐ v4.19.0修复：支持后台刷新，避免阻塞UI
const loadGovernanceStats = async (showLoading = false) => {
  if (showLoading) {
    statsLoading.value = true;
  }

  try {
    const data = await api.getDataSyncGovernanceStats();
    if (data) {
      governanceStats.value = data;
    }
  } catch (error) {
    console.error("加载数据治理统计失败:", error);
    // 后台刷新失败不显示错误提示
    if (showLoading) {
      ElMessage.error(error.message || "加载数据治理统计失败");
    }
  } finally {
    if (showLoading) {
      statsLoading.value = false;
    }
  }
};

// 刷新待同步文件
const handleRefreshFiles = async () => {
  refreshing.value = true;
  try {
    await ElMessageBox.confirm(
      "确定要刷新待同步文件列表吗？这将重新扫描采集文件。",
      "确认刷新",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "info",
      }
    );

    const result = await api.refreshPendingFiles();
    ElMessage.success(result.message || "刷新成功");
    await loadFiles();
    await loadGovernanceStats();
  } catch (error) {
    if (error !== "cancel") {
      console.error("刷新文件失败:", error);
      ElMessage.error(error.message || "刷新文件失败");
    }
  } finally {
    refreshing.value = false;
  }
};

// 手动全部数据同步
const handleSyncAll = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要同步所有有模板的待同步文件吗？当前有 ${
        governanceStats.value.pending_count || 0
      } 个待同步文件。`,
      "确认全部同步",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    );

    syncingAll.value = true;
    const result = await api.syncAllWithTemplate();

    if (result.task_id) {
      ElMessage.success(
        result.message || `批量同步任务已启动（${result.file_count}个文件）`
      );
      // 可以跳转到任务页面查看进度
      router.push(`/data-sync/tasks?task_id=${result.task_id}`);
    } else {
      ElMessage.warning(result.message || "没有找到有模板的待同步文件");
    }

    await loadGovernanceStats();
  } catch (error) {
    if (error !== "cancel") {
      console.error("全部同步失败:", error);
      ElMessage.error(error.message || "全部同步失败");
    }
  } finally {
    syncingAll.value = false;
  }
};

// 清理数据库
const handleCleanupDatabase = async () => {
  try {
    await ElMessageBox.confirm(
      "⚠️ 警告：此操作将删除所有已入库的数据，并重置文件状态为待同步。\n\n此操作不可恢复，确定要继续吗？",
      "确认清理数据库",
      {
        confirmButtonText: "确定清理",
        cancelButtonText: "取消",
        type: "warning",
        dangerouslyUseHTMLString: false,
      }
    );

    cleaning.value = true;
    const result = await api.cleanupDatabase();

    ElMessage.success(
      result.message ||
        `数据库清理完成：删除${result.total_deleted_rows || 0}行数据，重置${
          result.reset_files_count || 0
        }个文件状态`
    );

    await loadFiles();
    await loadGovernanceStats();
  } catch (error) {
    if (error !== "cancel") {
      console.error("清理数据库失败:", error);
      ElMessage.error(error.message || "清理数据库失败");
    }
  } finally {
    cleaning.value = false;
  }
};

// 进度轮询
const startProgressPolling = (taskId) => {
  // 如果已经在轮询，先清除
  if (pollingTasks.value.has(taskId)) {
    clearInterval(pollingTasks.value.get(taskId));
  }

  // ⭐ v4.19.0新增：任务开始时立即刷新同步历史记录（显示"处理中"状态）
  // 后台刷新，不显示loading
  loadSyncHistory(false).catch((err) =>
    console.error("刷新同步历史失败:", err)
  );

  // 立即查询一次
  pollTaskProgress(taskId);

  // 每2秒轮询一次
  const intervalId = setInterval(() => {
    pollTaskProgress(taskId);
  }, 2000);

  pollingTasks.value.set(taskId, intervalId);
};

// 查询任务进度
const pollTaskProgress = async (taskId) => {
  try {
    const progress = await api.getSyncTaskProgress(taskId);

    if (progress) {
      taskProgress.value.set(taskId, progress);

      // ⭐ v4.17.1修复：更健壮的完成检测
      const isCompleted =
        progress.status === "completed" ||
        progress.status === "success" ||
        (progress.processed_files >= progress.total_files &&
          progress.status !== "processing");
      const isFailed =
        progress.status === "failed" || progress.status === "error";

      // ⭐ v4.19.0修复：任务进行中时也刷新同步历史记录（显示"处理中"状态）
      // 每5次轮询刷新一次历史记录（约10秒一次），避免频繁请求
      const currentProgress = taskProgress.value.get(taskId);
      const refreshCount = (currentProgress?._refreshCount || 0) + 1;
      if (currentProgress) {
        currentProgress._refreshCount = refreshCount;
      }

      // 任务进行中时定期刷新（每5次轮询刷新一次）
      if (!isCompleted && !isFailed && refreshCount % 5 === 0) {
        // ⭐ v4.19.0修复：后台刷新，不显示loading
        loadSyncHistory(false).catch((err) =>
          console.error("后台刷新同步历史失败:", err)
        );
      }

      // 如果任务完成或失败，停止轮询并刷新
      if (isCompleted || isFailed) {
        stopProgressPolling(taskId);

        // ⭐ v4.18.2修复：异步刷新，不阻塞
        // ⭐ v4.19.0修复：任务完成时局部刷新（后台刷新，不显示loading）
        setTimeout(async () => {
          try {
            // 后台刷新文件列表（不显示loading）
            await loadFiles(false);
            // 后台刷新统计（不显示loading）
            await loadGovernanceStats(false);
            // 延迟刷新同步历史记录，确保数据库已提交（后台刷新）
            await new Promise((resolve) => setTimeout(resolve, 1000));
            await loadSyncHistory(false);
          } catch (err) {
            console.error("后台刷新失败:", err);
          }
        }, 1000);

        // v4.18.0: 区分单文件同步和批量同步
        const isSingleFile =
          progress.task_type === "single_file" || progress.total_files === 1;

        // 单文件同步：从syncingFiles中移除（通过task_id提取file_id）
        if (isSingleFile && taskId.startsWith("single_file_")) {
          const fileIdMatch = taskId.match(/single_file_(\d+)_/);
          if (fileIdMatch) {
            const fileId = parseInt(fileIdMatch[1]);
            syncingFiles.value = syncingFiles.value.filter(
              (id) => id !== fileId
            );
          }
        }

        // 显示详细的完成消息
        if (isCompleted) {
          const successCount = progress.success_files || 0;
          const failedCount = progress.failed_files || 0;
          const skippedCount = progress.skipped_files || 0;

          if (isSingleFile) {
            // 单文件同步消息
            if (successCount > 0) {
              ElMessage.success("文件同步成功");
            } else if (failedCount > 0) {
              ElMessage.warning("文件同步失败");
            } else {
              ElMessage.info("文件已处理");
            }
          } else {
            // 批量同步消息
            let message = `批量同步完成：成功${successCount}个`;
            if (failedCount > 0) {
              message += `，失败${failedCount}个`;
            }
            if (skippedCount > 0) {
              message += `，跳过${skippedCount}个（重复数据）`;
            }
            ElMessage.success(message);
          }
        } else {
          const errorMsg = isSingleFile ? "文件同步失败" : "批量同步失败";
          ElMessage.warning(`${errorMsg}：${progress.message || "未知错误"}`);
        }
      }
    }
  } catch (error) {
    console.error("查询任务进度失败:", error);
    // ⭐ v4.17.1修复：如果查询失败（404），可能是任务已完成并被清理，刷新页面
    if (error.response?.status === 404) {
      // 任务不存在，可能已完成并被清理，刷新页面
      stopProgressPolling(taskId);
      // ⭐ v4.18.2修复：异步刷新，不阻塞
      // ⭐ v4.19.0修复：局部刷新（后台刷新，不显示loading）
      setTimeout(async () => {
        try {
          // 后台刷新文件列表（不显示loading）
          await loadFiles(false);
          // 后台刷新统计（不显示loading）
          await loadGovernanceStats(false);
          // 延迟刷新同步历史记录，确保数据库已提交（后台刷新）
          await new Promise((resolve) => setTimeout(resolve, 1000));
          await loadSyncHistory(false);
        } catch (err) {
          console.error("后台刷新失败:", err);
        }
      }, 1000);

      ElMessage.info("同步任务已完成，页面已刷新");
    }
    // 其他错误不显示消息，避免干扰用户
  }
};

// 停止进度轮询
const stopProgressPolling = (taskId) => {
  if (pollingTasks.value.has(taskId)) {
    clearInterval(pollingTasks.value.get(taskId));
    pollingTasks.value.delete(taskId);
  }
};

// 清理：组件卸载时停止所有轮询
onUnmounted(() => {
  pollingTasks.value.forEach((intervalId) => {
    clearInterval(intervalId);
  });
  pollingTasks.value.clear();
});

// 初始化
onMounted(() => {
  loadFiles();
  loadGovernanceStats();
  loadSyncHistory(); // v4.18.0新增：加载同步历史
});
</script>

<style scoped>
.data-sync-files {
  min-height: calc(100vh - var(--header-height));
}

.governance-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
  flex: 1;
  min-width: 200px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 24px;
}

.stat-icon-primary {
  background: #409eff;
}

.stat-icon-success {
  background: #67c23a;
}

.stat-icon-danger {
  background: #f56c6c;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.governance-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
  padding-top: 15px;
  border-top: 1px solid #ebeef5;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.filter-select {
  width: 150px;
}

/* 进度卡片样式 */
.progress-card {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 1px solid #bae6fd;
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.progress-item {
  padding: 16px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.task-id {
  font-weight: 600;
  color: #1d4ed8;
  font-size: 13px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #64748b;
}

.current-file {
  color: #0ea5e9;
  font-style: italic;
}

.progress-stats {
  display: flex;
  gap: 16px;
  margin-top: 10px;
  font-size: 13px;
}

.stat-success {
  color: #16a34a;
  font-weight: 500;
}

.stat-failed {
  color: #dc2626;
  font-weight: 500;
}

.stat-skipped {
  color: #d97706;
  font-weight: 500;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.sync-history-card {
  margin-top: 20px;
}

.mono-task-id {
  font-family: monospace;
  font-size: 12px;
}

.history-error-text {
  color: #f56c6c;
  font-size: 12px;
}

.history-success-text {
  color: #67c23a;
  font-size: 12px;
}

.history-muted-text {
  color: #909399;
  font-size: 12px;
}

.comparison-title {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.comparison-title-success {
  color: #67c23a;
}

.comparison-title-danger {
  color: #f56c6c;
}
</style>
