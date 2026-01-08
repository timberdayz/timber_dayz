<template>
  <div class="data-backup">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Folder /></el-icon>
          数据备份
        </h1>
        <p class="page-subtitle">
          管理系统数据备份与恢复，包括手动备份、自动备份配置和备份历史
        </p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="createBackup" :loading="loading">
          <el-icon><Plus /></el-icon>
          创建备份
        </el-button>
        <el-button @click="loadBackupList" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 备份列表 -->
    <el-card class="backup-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>备份历史</span>
        </div>
      </template>
      <el-table :data="backupList" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80"></el-table-column>
        <el-table-column prop="backup_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.backup_type === 'full' ? 'success' : 'info'">
              {{ row.backup_type === "full" ? "完整备份" : "增量备份" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="backup_path" label="备份路径"></el-table-column>
        <el-table-column prop="backup_size" label="大小" width="120">
          <template #default="{ row }">
            {{ formatFileSize(row.backup_size) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="
                row.status === 'completed'
                  ? 'success'
                  : row.status === 'failed'
                  ? 'danger'
                  : 'warning'
              "
            >
              {{
                row.status === "completed"
                  ? "已完成"
                  : row.status === "failed"
                  ? "失败"
                  : "进行中"
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          label="创建时间"
          width="180"
        ></el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              @click="downloadBackup(row.id)"
              :disabled="row.status !== 'completed'"
            >
              下载
            </el-button>
            <el-button
              size="small"
              type="danger"
              @click="restoreBackup(row.id)"
              :disabled="row.status !== 'completed'"
            >
              恢复
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 自动备份配置 -->
    <el-card class="config-card" shadow="hover" style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>自动备份配置</span>
          <el-button
            type="primary"
            size="small"
            @click="saveAutoBackupConfig"
            :loading="loading"
          >
            <el-icon><Check /></el-icon>
            保存
          </el-button>
        </div>
      </template>
      <el-form :model="autoBackupConfig" label-width="180px">
        <el-form-item label="启用自动备份">
          <el-switch v-model="autoBackupConfig.enabled"></el-switch>
        </el-form-item>
        <el-form-item label="备份计划(CRON)" v-if="autoBackupConfig.enabled">
          <el-input
            v-model="autoBackupConfig.schedule"
            style="width: 360px"
            placeholder="例如：0 2 * * *（每天凌晨2点）"
          />
        </el-form-item>
        <el-form-item label="备份类型" v-if="autoBackupConfig.enabled">
          <el-select
            v-model="autoBackupConfig.backup_type"
            style="width: 200px"
          >
            <el-option label="完整备份" value="full"></el-option>
            <el-option label="增量备份" value="incremental"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="保留天数" v-if="autoBackupConfig.enabled">
          <el-input-number
            v-model="autoBackupConfig.retention_days"
            :min="1"
            :max="365"
          ></el-input-number>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Folder, Plus, Refresh, Check } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

const loading = ref(false);
const backupList = ref([]);
const autoBackupConfig = ref({
  enabled: false,
  schedule: "0 2 * * *",
  backup_type: "full",
  retention_days: 30,
});

const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
};

const loadBackupList = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.getBackupList();
    // 后端返回 BackupListResponse: {data: [...], page, page_size, total, total_pages}
    // 响应拦截器在无 success 字段时，会返回原始对象
    if (response && Array.isArray(response.data)) {
      backupList.value = response.data;
    } else if (Array.isArray(response)) {
      backupList.value = response;
    } else {
      backupList.value = [];
    }
  } catch (error) {
    console.error("加载备份列表失败:", error);
    ElMessage.error(
      error.response?.data?.message || error.message || "加载备份列表失败"
    );
  } finally {
    loading.value = false;
  }
};

const createBackup = async () => {
  try {
    await ElMessageBox.confirm("确定要创建备份吗？", "确认备份", {
      type: "warning",
    });
    loading.value = true;
    const response = await systemAPI.createBackup({ backup_type: "full" });
    if (response && response.success !== false) {
      ElMessage.success("备份创建成功");
      await loadBackupList();
    } else {
      ElMessage.error(response?.message || "创建备份失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("创建备份失败:", error);
      ElMessage.error(
        error.response?.data?.message || error.message || "创建备份失败"
      );
    }
  } finally {
    loading.value = false;
  }
};

const downloadBackup = async (backupId) => {
  try {
    loading.value = true;
    const response = await systemAPI.downloadBackup(backupId);
    // 处理文件下载
    const blob = new Blob([response.data]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `backup_${backupId}.tar.gz`;
    link.click();
    window.URL.revokeObjectURL(url);
    ElMessage.success("备份下载成功");
  } catch (error) {
    console.error("下载备份失败:", error);
    ElMessage.error(
      error.response?.data?.message || error.message || "下载备份失败"
    );
  } finally {
    loading.value = false;
  }
};

const restoreBackup = async (backupId) => {
  try {
    await ElMessageBox.confirm(
      "恢复备份将覆盖当前数据，此操作不可逆。确定要继续吗？",
      "确认恢复",
      {
        type: "warning",
        confirmButtonText: "确定恢复",
        cancelButtonText: "取消",
      }
    );
    loading.value = true;
    const response = await systemAPI.restoreBackup(backupId, {
      confirmed: true,
      confirmed_by: [],
    });
    if (response && response.success !== false) {
      ElMessage.success("备份恢复成功");
    } else {
      ElMessage.error(response?.message || "恢复备份失败");
    }
  } catch (error) {
    if (error !== "cancel") {
      console.error("恢复备份失败:", error);
      ElMessage.error(
        error.response?.data?.message || error.message || "恢复备份失败"
      );
    }
  } finally {
    loading.value = false;
  }
};

const loadAutoBackupConfig = async () => {
  try {
    const response = await systemAPI.getAutoBackupConfig();
    // 后端返回 AutoBackupConfigResponse: {enabled, schedule, backup_type, retention_days, ...}
    const data = response?.data || response;
    if (data) {
      autoBackupConfig.value = {
        enabled: Boolean(data.enabled),
        schedule: data.schedule || "0 2 * * *",
        backup_type: data.backup_type || "full",
        retention_days: data.retention_days ?? 30,
      };
    }
  } catch (error) {
    console.error("加载自动备份配置失败:", error);
  }
};

const saveAutoBackupConfig = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.updateAutoBackupConfig(
      autoBackupConfig.value
    );
    if (response && response.success !== false) {
      ElMessage.success("自动备份配置保存成功");
    } else {
      ElMessage.error(response?.message || "保存自动备份配置失败");
    }
  } catch (error) {
    console.error("保存自动备份配置失败:", error);
    ElMessage.error(
      error.response?.data?.message || error.message || "保存自动备份配置失败"
    );
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadBackupList();
  loadAutoBackupConfig();
});
</script>

<style scoped>
.data-backup {
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
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
</style>
