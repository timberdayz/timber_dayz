<template>
  <div class="database-config">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Connection /></el-icon>
          数据库配置
        </h1>
        <p class="page-subtitle">管理数据库连接配置，包括主机、端口、数据库名、用户名和密码</p>
      </div>
      <div class="header-actions">
        <el-button type="success" @click="testConnection" :loading="testing">
          <el-icon><Connection /></el-icon>
          测试连接
        </el-button>
        <el-button type="primary" @click="saveConfig" :loading="loading">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
        <el-button @click="loadDatabaseConfig" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 配置表单 -->
    <el-card class="config-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>数据库连接配置</span>
        </div>
      </template>
      <el-form :model="databaseConfig" label-width="120px" :rules="rules" ref="configFormRef">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="数据库类型" prop="type">
              <el-select
                v-model="databaseConfig.type"
                placeholder="选择数据库类型"
                style="width: 100%"
                disabled
              >
                <el-option label="PostgreSQL" value="postgresql"></el-option>
                <el-option label="MySQL" value="mysql"></el-option>
                <el-option label="SQLite" value="sqlite"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="主机地址" prop="host">
              <el-input
                v-model="databaseConfig.host"
                placeholder="请输入主机地址"
                maxlength="256"
              ></el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="端口号" prop="port">
              <el-input-number
                v-model="databaseConfig.port"
                :min="1"
                :max="65535"
                controls-position="right"
                style="width: 100%"
              ></el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据库名" prop="database">
              <el-input
                v-model="databaseConfig.database"
                placeholder="请输入数据库名"
                maxlength="64"
              ></el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="databaseConfig.username"
                placeholder="请输入用户名"
                maxlength="64"
              ></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="databaseConfig.password"
                type="password"
                placeholder="请输入密码（留空则不修改）"
                show-password
                maxlength="256"
              ></el-input>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 连接测试结果 -->
    <el-card class="test-result-card" shadow="hover" style="margin-top: 20px" v-if="testResult">
      <el-alert
        :title="testResult.success ? '连接成功' : '连接失败'"
        :description="testResult.message"
        :type="testResult.success ? 'success' : 'error'"
        show-icon
        :closable="false"
      />
      <div v-if="testResult.success && testResult.response_time_ms" style="margin-top: 10px">
        <el-text type="info">响应时间: {{ testResult.response_time_ms }}ms</el-text>
      </div>
    </el-card>

    <!-- 配置说明 -->
    <el-card class="info-card" shadow="hover" style="margin-top: 20px">
      <el-alert
        title="配置说明"
        description="数据库配置修改后需要重启系统才能生效。请谨慎操作，建议在维护时间进行配置修改。密码字段留空表示不修改现有密码。"
        type="warning"
        show-icon
        :closable="false"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Connection, Check, Refresh } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

// 响应式数据
const loading = ref(false);
const testing = ref(false);
const configFormRef = ref(null);
const testResult = ref(null);

const databaseConfig = ref({
  type: "postgresql",
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
});

// 表单验证规则
const rules = {
  host: [
    { required: true, message: "请输入主机地址", trigger: "blur" },
    { max: 256, message: "主机地址不能超过256个字符", trigger: "blur" },
  ],
  port: [
    { required: true, message: "请输入端口号", trigger: "blur" },
    { type: "number", min: 1, max: 65535, message: "端口号必须在1-65535之间", trigger: "blur" },
  ],
  database: [
    { required: true, message: "请输入数据库名", trigger: "blur" },
    { max: 64, message: "数据库名不能超过64个字符", trigger: "blur" },
  ],
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { max: 64, message: "用户名不能超过64个字符", trigger: "blur" },
  ],
};

// 加载数据库配置
const loadDatabaseConfig = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.getDatabaseConfig();
    if (response && response.data) {
      databaseConfig.value = {
        type: response.data.type || "postgresql",
        host: response.data.host || "",
        port: response.data.port || 5432,
        database: response.data.database || "",
        username: response.data.username || "",
        password: "", // 密码不显示，留空
      };
    } else if (response) {
      // 兼容直接返回配置对象的情况
      databaseConfig.value = {
        type: response.type || "postgresql",
        host: response.host || "",
        port: response.port || 5432,
        database: response.database || "",
        username: response.username || "",
        password: "", // 密码不显示，留空
      };
    }
  } catch (error) {
    console.error("加载数据库配置失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "加载数据库配置失败");
  } finally {
    loading.value = false;
  }
};

// 测试连接
const testConnection = async () => {
  try {
    await configFormRef.value.validate();
    testing.value = true;
    testResult.value = null;
    
    const response = await systemAPI.testDatabaseConnection({
      host: databaseConfig.value.host,
      port: databaseConfig.value.port,
      database: databaseConfig.value.database,
      username: databaseConfig.value.username,
      password: databaseConfig.value.password || undefined, // 如果密码为空，不发送
    });
    
    if (response && response.data) {
      testResult.value = {
        success: response.data.success,
        message: response.data.message || (response.data.success ? "连接成功" : "连接失败"),
        response_time_ms: response.data.response_time_ms,
      };
      if (response.data.success) {
        ElMessage.success("数据库连接测试成功");
      } else {
        ElMessage.error("数据库连接测试失败");
      }
    } else if (response) {
      // 兼容直接返回结果的情况
      testResult.value = {
        success: response.success,
        message: response.message || (response.success ? "连接成功" : "连接失败"),
        response_time_ms: response.response_time_ms,
      };
      if (response.success) {
        ElMessage.success("数据库连接测试成功");
      } else {
        ElMessage.error("数据库连接测试失败");
      }
    }
  } catch (error) {
    if (error.message !== "validation failed") {
      console.error("测试数据库连接失败:", error);
      testResult.value = {
        success: false,
        message: error.response?.data?.message || error.message || "测试连接失败",
      };
      ElMessage.error(error.response?.data?.message || error.message || "测试数据库连接失败");
    }
  } finally {
    testing.value = false;
  }
};

// 保存配置
const saveConfig = async () => {
  try {
    await configFormRef.value.validate();
    
    // 确认保存
    await ElMessageBox.confirm(
      "数据库配置修改后需要重启系统才能生效。确定要保存配置吗？",
      "确认保存",
      {
        type: "warning",
        confirmButtonText: "确定保存",
        cancelButtonText: "取消",
      }
    );
    
    loading.value = true;
    const configToSave = {
      type: databaseConfig.value.type,
      host: databaseConfig.value.host,
      port: databaseConfig.value.port,
      database: databaseConfig.value.database,
      username: databaseConfig.value.username,
      // 只有密码不为空时才发送
      ...(databaseConfig.value.password ? { password: databaseConfig.value.password } : {}),
    };
    
    const response = await systemAPI.updateDatabaseConfig(configToSave);
    if (response && (response.success !== false)) {
      ElMessage.success("数据库配置保存成功，请重启系统使配置生效");
      await loadDatabaseConfig();
      testResult.value = null; // 清空测试结果
    } else {
      ElMessage.error(response?.message || "保存数据库配置失败");
    }
  } catch (error) {
    if (error !== "cancel" && error.message !== "validation failed") {
      console.error("保存数据库配置失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "保存数据库配置失败");
    }
  } finally {
    loading.value = false;
  }
};

// 初始化
onMounted(() => {
  loadDatabaseConfig();
});
</script>

<style scoped>
.database-config {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-content {
  flex: 1;
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

.header-actions {
  display: flex;
  gap: 12px;
}

.config-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.test-result-card {
  background-color: #f5f7fa;
}

.info-card {
  background-color: #f5f7fa;
}
</style>
