<template>
  <div class="security-settings">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Lock /></el-icon>
          安全设置
        </h1>
        <p class="page-subtitle">管理系统安全配置，包括密码策略、登录限制、会话管理和双因素认证</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshAll" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 功能导航 -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- 密码策略 -->
      <el-tab-pane label="密码策略" name="password">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>密码策略配置</span>
              <el-button type="primary" size="small" @click="savePasswordPolicy" :loading="loading">
                <el-icon><Check /></el-icon>
                保存
              </el-button>
            </div>
          </template>
          <el-form :model="passwordPolicy" label-width="180px" ref="passwordPolicyFormRef">
            <el-form-item label="最小密码长度">
              <el-input-number
                v-model="passwordPolicy.min_length"
                :min="8"
                :max="128"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">建议至少8个字符</el-text>
            </el-form-item>
            <el-form-item label="密码复杂度要求">
              <el-checkbox-group v-model="passwordPolicy.requirements">
                <el-checkbox label="require_uppercase">需要大写字母</el-checkbox>
                <el-checkbox label="require_lowercase">需要小写字母</el-checkbox>
                <el-checkbox label="require_digits">需要数字</el-checkbox>
                <el-checkbox label="require_special_chars">需要特殊字符</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="密码最大有效期（天）">
              <el-input-number
                v-model="passwordPolicy.max_age_days"
                :min="30"
                :max="365"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">0表示永不过期</el-text>
            </el-form-item>
            <el-form-item label="密码历史记录数">
              <el-input-number
                v-model="passwordPolicy.history_count"
                :min="0"
                :max="10"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">禁止使用最近N个历史密码</el-text>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 登录限制 -->
      <el-tab-pane label="登录限制" name="login">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>登录限制配置</span>
              <el-button type="primary" size="small" @click="saveLoginRestrictions" :loading="loading">
                <el-icon><Check /></el-icon>
                保存
              </el-button>
            </div>
          </template>
          <el-form :model="loginRestrictions" label-width="180px" ref="loginRestrictionsFormRef">
            <el-form-item label="最大失败次数">
              <el-input-number
                v-model="loginRestrictions.max_failed_attempts"
                :min="3"
                :max="10"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">超过此次数将锁定账户</el-text>
            </el-form-item>
            <el-form-item label="锁定时间（分钟）">
              <el-input-number
                v-model="loginRestrictions.lockout_duration_minutes"
                :min="5"
                :max="1440"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">账户锁定后的持续时间</el-text>
            </el-form-item>
            <el-form-item label="启用IP白名单">
              <el-switch v-model="loginRestrictions.enable_ip_whitelist"></el-switch>
              <el-text type="info" style="margin-left: 10px">启用后仅允许白名单IP访问</el-text>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- IP白名单管理 -->
        <el-card class="config-card" shadow="hover" style="margin-top: 20px">
          <template #header>
            <div class="card-header">
              <span>IP白名单</span>
              <el-button type="primary" size="small" @click="showAddIPDialog">
                <el-icon><Plus /></el-icon>
                添加IP
              </el-button>
            </div>
          </template>
          <el-table :data="ipWhitelist" style="width: 100%">
            <el-table-column prop="ip" label="IP地址" width="200"></el-table-column>
            <el-table-column prop="description" label="描述"></el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  size="small"
                  @click="removeIP(row.ip)"
                  :loading="loading"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 会话管理 -->
      <el-tab-pane label="会话管理" name="session">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>会话配置</span>
              <el-button type="primary" size="small" @click="saveSessionConfig" :loading="loading">
                <el-icon><Check /></el-icon>
                保存
              </el-button>
            </div>
          </template>
          <el-form :model="sessionConfig" label-width="180px" ref="sessionConfigFormRef">
            <el-form-item label="会话超时时间（分钟）">
              <el-input-number
                v-model="sessionConfig.timeout_minutes"
                :min="5"
                :max="1440"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">用户无操作后自动登出时间</el-text>
            </el-form-item>
            <el-form-item label="最大并发会话数">
              <el-input-number
                v-model="sessionConfig.max_concurrent_sessions"
                :min="1"
                :max="10"
                controls-position="right"
              ></el-input-number>
              <el-text type="info" style="margin-left: 10px">同一用户最多同时登录的设备数</el-text>
            </el-form-item>
            <el-form-item label="启用会话超时检查">
              <el-switch v-model="sessionConfig.enable_timeout_check"></el-switch>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 2FA配置 -->
      <el-tab-pane label="双因素认证" name="2fa">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>2FA配置</span>
              <el-button type="primary" size="small" @click="save2FAConfig" :loading="loading">
                <el-icon><Check /></el-icon>
                保存
              </el-button>
            </div>
          </template>
          <el-form :model="twoFactorConfig" label-width="180px" ref="twoFactorConfigFormRef">
            <el-form-item label="启用2FA">
              <el-switch v-model="twoFactorConfig.enabled"></el-switch>
              <el-text type="info" style="margin-left: 10px">启用双因素认证增强安全性</el-text>
            </el-form-item>
            <el-form-item label="2FA方法" v-if="twoFactorConfig.enabled">
              <el-radio-group v-model="twoFactorConfig.method">
                <el-radio label="totp">TOTP（时间-based一次性密码）</el-radio>
                <el-radio label="sms">短信验证码</el-radio>
                <el-radio label="email">邮箱验证码</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="验证码有效期（秒）" v-if="twoFactorConfig.enabled">
              <el-input-number
                v-model="twoFactorConfig.code_validity_seconds"
                :min="60"
                :max="600"
                controls-position="right"
              ></el-input-number>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 添加IP对话框 -->
    <el-dialog v-model="addIPDialogVisible" title="添加IP到白名单" width="500px">
      <el-form :model="newIP" label-width="100px">
        <el-form-item label="IP地址" required>
          <el-input v-model="newIP.ip" placeholder="请输入IP地址或CIDR（如：192.168.1.1 或 192.168.1.0/24）"></el-input>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newIP.description" placeholder="请输入描述（可选）"></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addIPDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addIP" :loading="loading">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Lock, Refresh, Check, Plus } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

// 响应式数据
const loading = ref(false);
const activeTab = ref("password");
const addIPDialogVisible = ref(false);

const passwordPolicyFormRef = ref(null);
const loginRestrictionsFormRef = ref(null);
const sessionConfigFormRef = ref(null);
const twoFactorConfigFormRef = ref(null);

// 密码策略
const passwordPolicy = ref({
  min_length: 8,
  requirements: ["require_uppercase", "require_lowercase", "require_digits"],
  max_age_days: 90,
  history_count: 3,
});

// 登录限制
const loginRestrictions = ref({
  max_failed_attempts: 5,
  lockout_duration_minutes: 30,
  enable_ip_whitelist: false,
});

// IP白名单
const ipWhitelist = ref([]);

// 会话配置
const sessionConfig = ref({
  timeout_minutes: 15,
  max_concurrent_sessions: 5,
  enable_timeout_check: true,
});

// 2FA配置
const twoFactorConfig = ref({
  enabled: false,
  method: "totp",
  code_validity_seconds: 300,
});

// 新IP
const newIP = ref({
  ip: "",
  description: "",
});

// 加载密码策略
const loadPasswordPolicy = async () => {
  try {
    const response = await systemAPI.getPasswordPolicy();
    if (response && response.data) {
      passwordPolicy.value = {
        min_length: response.data.min_length || 8,
        requirements: response.data.requirements || [],
        max_age_days: response.data.max_age_days || 90,
        history_count: response.data.history_count || 3,
      };
    }
  } catch (error) {
    console.error("加载密码策略失败:", error);
  }
};

// 保存密码策略
const savePasswordPolicy = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.updatePasswordPolicy(passwordPolicy.value);
    if (response && (response.success !== false)) {
      ElMessage.success("密码策略保存成功");
    } else {
      ElMessage.error(response?.message || "保存密码策略失败");
    }
  } catch (error) {
    console.error("保存密码策略失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "保存密码策略失败");
  } finally {
    loading.value = false;
  }
};

// 加载登录限制
const loadLoginRestrictions = async () => {
  try {
    const response = await systemAPI.getLoginRestrictions();
    if (response && response.data) {
      loginRestrictions.value = {
        max_failed_attempts: response.data.max_failed_attempts || 5,
        lockout_duration_minutes: response.data.lockout_duration_minutes || 30,
        enable_ip_whitelist: response.data.enable_ip_whitelist || false,
      };
    }
  } catch (error) {
    console.error("加载登录限制失败:", error);
  }
};

// 保存登录限制
const saveLoginRestrictions = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.updateLoginRestrictions(loginRestrictions.value);
    if (response && (response.success !== false)) {
      ElMessage.success("登录限制保存成功");
    } else {
      ElMessage.error(response?.message || "保存登录限制失败");
    }
  } catch (error) {
    console.error("保存登录限制失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "保存登录限制失败");
  } finally {
    loading.value = false;
  }
};

// 加载IP白名单
const loadIPWhitelist = async () => {
  try {
    const response = await systemAPI.getIPWhitelist();
    if (response && response.data) {
      ipWhitelist.value = response.data.ips || [];
    }
  } catch (error) {
    console.error("加载IP白名单失败:", error);
  }
};

// 添加IP
const showAddIPDialog = () => {
  newIP.value = { ip: "", description: "" };
  addIPDialogVisible.value = true;
};

const addIP = async () => {
  if (!newIP.value.ip) {
    ElMessage.warning("请输入IP地址");
    return;
  }
  try {
    loading.value = true;
    const response = await systemAPI.addIPToWhitelist(newIP.value.ip);
    if (response && (response.success !== false)) {
      ElMessage.success("IP添加成功");
      addIPDialogVisible.value = false;
      await loadIPWhitelist();
    } else {
      ElMessage.error(response?.message || "添加IP失败");
    }
  } catch (error) {
    console.error("添加IP失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "添加IP失败");
  } finally {
    loading.value = false;
  }
};

// 删除IP
const removeIP = async (ip) => {
  try {
    loading.value = true;
    const response = await systemAPI.removeIPFromWhitelist(ip);
    if (response && (response.success !== false)) {
      ElMessage.success("IP删除成功");
      await loadIPWhitelist();
    } else {
      ElMessage.error(response?.message || "删除IP失败");
    }
  } catch (error) {
    console.error("删除IP失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "删除IP失败");
  } finally {
    loading.value = false;
  }
};

// 加载会话配置
const loadSessionConfig = async () => {
  try {
    const response = await systemAPI.getSessionConfig();
    if (response && response.data) {
      sessionConfig.value = {
        timeout_minutes: response.data.timeout_minutes || 15,
        max_concurrent_sessions: response.data.max_concurrent_sessions || 5,
        enable_timeout_check: response.data.enable_timeout_check !== false,
      };
    }
  } catch (error) {
    console.error("加载会话配置失败:", error);
  }
};

// 保存会话配置
const saveSessionConfig = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.updateSessionConfig(sessionConfig.value);
    if (response && (response.success !== false)) {
      ElMessage.success("会话配置保存成功");
    } else {
      ElMessage.error(response?.message || "保存会话配置失败");
    }
  } catch (error) {
    console.error("保存会话配置失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "保存会话配置失败");
  } finally {
    loading.value = false;
  }
};

// 加载2FA配置
const load2FAConfig = async () => {
  try {
    const response = await systemAPI.get2FAConfig();
    if (response && response.data) {
      twoFactorConfig.value = {
        enabled: response.data.enabled || false,
        method: response.data.method || "totp",
        code_validity_seconds: response.data.code_validity_seconds || 300,
      };
    }
  } catch (error) {
    console.error("加载2FA配置失败:", error);
  }
};

// 保存2FA配置
const save2FAConfig = async () => {
  try {
    loading.value = true;
    const response = await systemAPI.update2FAConfig(twoFactorConfig.value);
    if (response && (response.success !== false)) {
      ElMessage.success("2FA配置保存成功");
    } else {
      ElMessage.error(response?.message || "保存2FA配置失败");
    }
  } catch (error) {
    console.error("保存2FA配置失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "保存2FA配置失败");
  } finally {
    loading.value = false;
  }
};

// Tab切换
const handleTabChange = (tabName) => {
  if (tabName === "password") {
    loadPasswordPolicy();
  } else if (tabName === "login") {
    loadLoginRestrictions();
    loadIPWhitelist();
  } else if (tabName === "session") {
    loadSessionConfig();
  } else if (tabName === "2fa") {
    load2FAConfig();
  }
};

// 刷新所有
const refreshAll = async () => {
  await Promise.all([
    loadPasswordPolicy(),
    loadLoginRestrictions(),
    loadIPWhitelist(),
    loadSessionConfig(),
    load2FAConfig(),
  ]);
  ElMessage.success("刷新成功");
};

// 初始化
onMounted(() => {
  loadPasswordPolicy();
});
</script>

<style scoped>
.security-settings {
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
</style>
