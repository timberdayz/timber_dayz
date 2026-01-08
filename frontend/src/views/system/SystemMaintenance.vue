<template>
  <div class="system-maintenance">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Tools /></el-icon>
          系统维护
        </h1>
        <p class="page-subtitle">执行系统维护操作，包括缓存清理、数据清理和系统升级检查</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshStatus" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新状态
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 缓存管理 -->
      <el-col :span="12">
        <el-card class="maintenance-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>缓存管理</span>
            </div>
          </template>
          <div class="status-info">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="Redis状态">
                <el-tag :type="cacheStatus.redis_connected ? 'success' : 'danger'">
                  {{ cacheStatus.redis_connected ? '已连接' : '未连接' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="内存使用">
                {{ cacheStatus.memory_used || '0' }} MB
              </el-descriptions-item>
              <el-descriptions-item label="键数量">
                {{ cacheStatus.key_count || 0 }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="action-buttons" style="margin-top: 20px">
            <el-button type="warning" @click="clearCache" :loading="loading">
              <el-icon><Delete /></el-icon>
              清理缓存
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 数据清理 -->
      <el-col :span="12">
        <el-card class="maintenance-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>数据清理</span>
            </div>
          </template>
          <div class="status-info">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="系统日志">
                {{ dataStatus.system_logs_count || 0 }} 条
              </el-descriptions-item>
              <el-descriptions-item label="任务日志">
                {{ dataStatus.task_logs_count || 0 }} 条
              </el-descriptions-item>
              <el-descriptions-item label="临时文件">
                {{ formatFileSize(dataStatus.temp_files_size || 0) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="action-buttons" style="margin-top: 20px">
            <el-button type="danger" @click="cleanData" :loading="loading">
              <el-icon><Delete /></el-icon>
              清理数据
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统升级 -->
    <el-card class="upgrade-card" shadow="hover" style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>系统升级</span>
        </div>
      </template>
      <div class="upgrade-info">
        <el-alert
          title="系统升级说明"
          description="系统升级应通过 CI/CD 流程或手动操作完成，不建议通过 API 实现。如需升级，请联系系统管理员。"
          type="warning"
          show-icon
          :closable="false"
        />
        <div style="margin-top: 20px">
          <el-button type="info" @click="checkUpgrade" :loading="loading">
            <el-icon><Search /></el-icon>
            检查更新
          </el-button>
        </div>
        <div v-if="upgradeInfo" style="margin-top: 20px">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="当前版本">
              {{ upgradeInfo.current_version || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="最新版本">
              {{ upgradeInfo.latest_version || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="更新说明">
              {{ upgradeInfo.release_notes || '无' }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Tools, Refresh, Delete, Search } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

const loading = ref(false);
const cacheStatus = ref({
  redis_connected: false,
  memory_used: 0,
  key_count: 0,
});
const dataStatus = ref({
  system_logs_count: 0,
  task_logs_count: 0,
  temp_files_size: 0,
});
const upgradeInfo = ref(null);

const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
};

const refreshStatus = async () => {
  try {
    loading.value = true;
    await Promise.all([loadCacheStatus(), loadDataStatus()]);
    ElMessage.success("状态刷新成功");
  } catch (error) {
    console.error("刷新状态失败:", error);
  } finally {
    loading.value = false;
  }
};

const loadCacheStatus = async () => {
  try {
    const response = await systemAPI.getCacheStatus();
    if (response && response.data) {
      cacheStatus.value = {
        redis_connected: response.data.redis_connected || false,
        memory_used: response.data.memory_used || 0,
        key_count: response.data.key_count || 0,
      };
    }
  } catch (error) {
    console.error("加载缓存状态失败:", error);
  }
};

const clearCache = async () => {
  try {
    await ElMessageBox.confirm("确定要清理缓存吗？此操作不可逆。", "确认清理", {
      type: "warning",
    });
    loading.value = true;
    const response = await systemAPI.clearCache({ cache_type: "all" });
    if (response && (response.success !== false)) {
      ElMessage.success("缓存清理成功");
      await loadCacheStatus();
    } else {
      ElMessage.error(response?.message || "清理缓存失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("清理缓存失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "清理缓存失败");
    }
  } finally {
    loading.value = false;
  }
};

const loadDataStatus = async () => {
  try {
    const response = await systemAPI.getDataStatus();
    if (response && response.data) {
      dataStatus.value = {
        system_logs_count: response.data.system_logs_count || 0,
        task_logs_count: response.data.task_logs_count || 0,
        temp_files_size: response.data.temp_files_size || 0,
      };
    }
  } catch (error) {
    console.error("加载数据状态失败:", error);
  }
};

const cleanData = async () => {
  try {
    await ElMessageBox.confirm(
      "确定要清理数据吗？此操作不可逆，将删除历史日志和临时文件。",
      "确认清理",
      {
        type: "warning",
        confirmButtonText: "确定清理",
        cancelButtonText: "取消",
      }
    );
    loading.value = true;
    const response = await systemAPI.cleanData({
      clean_system_logs: true,
      clean_task_logs: true,
      clean_temp_files: true,
      retention_days: 30,
    });
    if (response && (response.success !== false)) {
      ElMessage.success("数据清理成功");
      await loadDataStatus();
    } else {
      ElMessage.error(response?.message || "清理数据失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("清理数据失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "清理数据失败");
    }
  } finally {
    loading.value = false;
  }
};

const checkUpgrade = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.checkSystemUpgrade();
    if (response && response.data) {
      upgradeInfo.value = {
        current_version: response.data.current_version,
        latest_version: response.data.latest_version,
        release_notes: response.data.release_notes,
      };
      if (response.data.has_update) {
        ElMessage.info("发现新版本");
      } else {
        ElMessage.success("当前已是最新版本");
      }
    }
  } catch (error) {
    console.error("检查更新失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "检查更新失败");
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  refreshStatus();
});
</script>

<style scoped>
.system-maintenance {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-subtitle {
  color: #909399;
  margin: 0;
}

.card-header {
  font-weight: 600;
}
</style>
