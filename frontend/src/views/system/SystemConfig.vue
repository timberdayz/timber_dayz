<template>
  <div class="system-config">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Setting /></el-icon>
          系统配置
        </h1>
        <p class="page-subtitle">管理系统基础配置，包括系统名称、版本、时区、语言和货币设置</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="saveConfig" :loading="loading">
          <el-icon><Check /></el-icon>
          保存配置
        </el-button>
        <el-button @click="loadSystemConfig" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 配置表单 -->
    <el-card class="config-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>基础配置</span>
        </div>
      </template>
      <el-form :model="systemConfig" label-width="120px" :rules="rules" ref="configFormRef">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="系统名称" prop="system_name">
              <el-input
                v-model="systemConfig.system_name"
                placeholder="请输入系统名称"
                maxlength="128"
                show-word-limit
              ></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="系统版本" prop="version">
              <el-input
                v-model="systemConfig.version"
                placeholder="系统版本"
                disabled
              ></el-input>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="时区设置" prop="timezone">
              <el-select
                v-model="systemConfig.timezone"
                placeholder="选择时区"
                style="width: 100%"
              >
                <el-option
                  label="北京时间 (UTC+8)"
                  value="Asia/Shanghai"
                ></el-option>
                <el-option
                  label="纽约时间 (UTC-5)"
                  value="America/New_York"
                ></el-option>
                <el-option
                  label="伦敦时间 (UTC+0)"
                  value="Europe/London"
                ></el-option>
                <el-option
                  label="东京时间 (UTC+9)"
                  value="Asia/Tokyo"
                ></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="语言设置" prop="language">
              <el-select
                v-model="systemConfig.language"
                placeholder="选择语言"
                style="width: 100%"
              >
                <el-option label="简体中文" value="zh-CN"></el-option>
                <el-option label="English" value="en-US"></el-option>
                <el-option label="繁體中文" value="zh-TW"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="货币设置" prop="currency">
              <el-select
                v-model="systemConfig.currency"
                placeholder="选择货币"
                style="width: 100%"
              >
                <el-option label="人民币 (CNY)" value="CNY"></el-option>
                <el-option label="美元 (USD)" value="USD"></el-option>
                <el-option label="欧元 (EUR)" value="EUR"></el-option>
                <el-option label="日元 (JPY)" value="JPY"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 配置说明 -->
    <el-card class="info-card" shadow="hover" style="margin-top: 20px">
      <el-alert
        title="配置说明"
        description="修改系统配置后需要重启系统才能生效。请谨慎操作，建议在维护时间进行配置修改。"
        type="info"
        show-icon
        :closable="false"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Setting, Check, Refresh } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

// 响应式数据
const loading = ref(false);
const configFormRef = ref(null);

const systemConfig = ref({
  system_name: "",
  version: "",
  timezone: "Asia/Shanghai",
  language: "zh-CN",
  currency: "CNY",
});

// 表单验证规则
const rules = {
  system_name: [
    { required: true, message: "请输入系统名称", trigger: "blur" },
    { max: 128, message: "系统名称不能超过128个字符", trigger: "blur" },
  ],
  timezone: [
    { required: true, message: "请选择时区", trigger: "change" },
  ],
  language: [
    { required: true, message: "请选择语言", trigger: "change" },
  ],
  currency: [
    { required: true, message: "请选择货币", trigger: "change" },
  ],
};

// 加载系统配置
const loadSystemConfig = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.getSystemConfig();
    if (response && response.data) {
      systemConfig.value = {
        system_name: response.data.system_name || "",
        version: response.data.version || "",
        timezone: response.data.timezone || "Asia/Shanghai",
        language: response.data.language || "zh-CN",
        currency: response.data.currency || "CNY",
      };
    } else if (response) {
      // 兼容直接返回配置对象的情况
      systemConfig.value = {
        system_name: response.system_name || "",
        version: response.version || "",
        timezone: response.timezone || "Asia/Shanghai",
        language: response.language || "zh-CN",
        currency: response.currency || "CNY",
      };
    }
  } catch (error) {
    console.error("加载系统配置失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
};

// 保存配置
const saveConfig = async () => {
  try {
    await configFormRef.value.validate();
    loading.value = true;
    const response = await systemAPI.updateSystemConfig(systemConfig.value);
    if (response && (response.success !== false)) {
      ElMessage.success("系统配置保存成功");
      await loadSystemConfig();
    } else {
      ElMessage.error(response?.message || "保存系统配置失败");
    }
  } catch (error) {
    if (error.message !== "validation failed") {
      console.error("保存系统配置失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "保存系统配置失败");
    }
  } finally {
    loading.value = false;
  }
};

// 初始化
onMounted(() => {
  loadSystemConfig();
});
</script>

<style scoped>
.system-config {
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

.info-card {
  background-color: #f5f7fa;
}
</style>
