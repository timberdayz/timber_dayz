<template>
  <div class="notification-config">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Bell /></el-icon>
          通知配置
        </h1>
        <p class="page-subtitle">管理系统通知配置，包括SMTP服务器、通知模板和告警规则</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshAll" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- SMTP配置 -->
      <el-tab-pane label="SMTP配置" name="smtp">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>SMTP服务器配置</span>
              <div>
                <el-button type="success" size="small" @click="testSMTP" :loading="testing">
                  测试连接
                </el-button>
                <el-button type="primary" size="small" @click="saveSMTPConfig" :loading="loading">
                  <el-icon><Check /></el-icon>
                  保存
                </el-button>
              </div>
            </div>
          </template>
          <el-form :model="smtpConfig" label-width="150px" ref="smtpFormRef">
            <el-form-item label="SMTP服务器" required>
              <el-input v-model="smtpConfig.smtp_server" placeholder="smtp.example.com"></el-input>
            </el-form-item>
            <el-form-item label="SMTP端口" required>
              <el-input-number v-model="smtpConfig.smtp_port" :min="1" :max="65535"></el-input-number>
            </el-form-item>
            <el-form-item label="使用TLS">
              <el-switch v-model="smtpConfig.use_tls"></el-switch>
            </el-form-item>
            <el-form-item label="用户名" required>
              <el-input v-model="smtpConfig.username"></el-input>
            </el-form-item>
            <el-form-item label="密码" required>
              <el-input v-model="smtpConfig.password" type="password" show-password></el-input>
            </el-form-item>
            <el-form-item label="发件人邮箱" required>
              <el-input v-model="smtpConfig.from_email"></el-input>
            </el-form-item>
            <el-form-item label="发件人名称">
              <el-input v-model="smtpConfig.from_name"></el-input>
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="smtpConfig.is_active"></el-switch>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 通知模板 -->
      <el-tab-pane label="通知模板" name="templates">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>通知模板管理</span>
              <el-button type="primary" size="small" @click="showTemplateDialog">
                <el-icon><Plus /></el-icon>
                新建模板
              </el-button>
            </div>
          </template>
          <el-table :data="templates" style="width: 100%" v-loading="loading">
            <el-table-column prop="template_name" label="模板名称"></el-table-column>
            <el-table-column prop="template_type" label="类型"></el-table-column>
            <el-table-column prop="subject" label="主题"></el-table-column>
            <el-table-column prop="is_active" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="editTemplate(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="deleteTemplate(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 告警规则 -->
      <el-tab-pane label="告警规则" name="alerts">
        <el-card class="config-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>告警规则管理</span>
              <el-button type="primary" size="small" @click="showAlertRuleDialog">
                <el-icon><Plus /></el-icon>
                新建规则
              </el-button>
            </div>
          </template>
          <el-table :data="alertRules" style="width: 100%" v-loading="loading">
            <el-table-column prop="rule_name" label="规则名称"></el-table-column>
            <el-table-column prop="alert_level" label="告警级别" width="120">
              <template #default="{ row }">
                <el-tag :type="row.alert_level === 'critical' ? 'danger' : row.alert_level === 'warning' ? 'warning' : 'info'">
                  {{ row.alert_level === 'critical' ? '严重' : row.alert_level === 'warning' ? '警告' : '信息' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="editAlertRule(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="deleteAlertRule(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Bell, Refresh, Check, Plus } from "@element-plus/icons-vue";
import * as systemAPI from "@/api/system";

const loading = ref(false);
const testing = ref(false);
const activeTab = ref("smtp");
const smtpFormRef = ref(null);

const smtpConfig = ref({
  smtp_server: "",
  smtp_port: 587,
  use_tls: true,
  username: "",
  password: "",
  from_email: "",
  from_name: "",
  is_active: true,
});

const templates = ref([]);
const alertRules = ref([]);

const loadSMTPConfig = async () => {
  try {
    const response = await systemAPI.getSMTPConfig();
    if (response && response.data) {
      smtpConfig.value = {
        smtp_server: response.data.smtp_server || "",
        smtp_port: response.data.smtp_port || 587,
        use_tls: response.data.use_tls !== false,
        username: response.data.username || "",
        password: "", // 密码不显示
        from_email: response.data.from_email || "",
        from_name: response.data.from_name || "",
        is_active: response.data.is_active !== false,
      };
    }
  } catch (error) {
    console.error("加载SMTP配置失败:", error);
  }
};

const saveSMTPConfig = async () => {
  try {
    await smtpFormRef.value.validate();
    loading.value = true;
    const response = await systemAPI.updateSMTPConfig(smtpConfig.value);
    if (response && (response.success !== false)) {
      ElMessage.success("SMTP配置保存成功");
    } else {
      ElMessage.error(response?.message || "保存SMTP配置失败");
    }
  } catch (error) {
    if (error.message !== "validation failed") {
      console.error("保存SMTP配置失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "保存SMTP配置失败");
    }
  } finally {
    loading.value = false;
  }
};

const testSMTP = async () => {
  try {
    await smtpFormRef.value.validate();
    testing.value = true;
    const response = await systemAPI.testSMTPConnection({
      smtp_server: smtpConfig.value.smtp_server,
      smtp_port: smtpConfig.value.smtp_port,
      use_tls: smtpConfig.value.use_tls,
      username: smtpConfig.value.username,
      password: smtpConfig.value.password,
    });
    if (response && response.data && response.data.success) {
      ElMessage.success("SMTP连接测试成功");
    } else {
      ElMessage.error(response?.data?.message || response?.message || "SMTP连接测试失败");
    }
  } catch (error) {
    if (error.message !== "validation failed") {
      console.error("测试SMTP连接失败:", error);
      ElMessage.error(error.response?.data?.message || error.message || "测试SMTP连接失败");
    }
  } finally {
    testing.value = false;
  }
};

const loadTemplates = async () => {
  try {
    const response = await systemAPI.getNotificationTemplates();
    if (response && response.data) {
      templates.value = response.data.templates || response.data || [];
    }
  } catch (error) {
    console.error("加载通知模板失败:", error);
  }
};

const loadAlertRules = async () => {
  try {
    const response = await systemAPI.getAlertRules();
    if (response && response.data) {
      alertRules.value = response.data.rules || response.data || [];
    }
  } catch (error) {
    console.error("加载告警规则失败:", error);
  }
};

const showTemplateDialog = () => {
  ElMessage.info("模板编辑功能开发中");
};

const editTemplate = (template) => {
  ElMessage.info("模板编辑功能开发中");
};

const deleteTemplate = async (templateId) => {
  try {
    const response = await systemAPI.deleteNotificationTemplate(templateId);
    if (response && (response.success !== false)) {
      ElMessage.success("模板删除成功");
      await loadTemplates();
    } else {
      ElMessage.error(response?.message || "删除模板失败");
    }
  } catch (error) {
    console.error("删除模板失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "删除模板失败");
  }
};

const showAlertRuleDialog = () => {
  ElMessage.info("告警规则编辑功能开发中");
};

const editAlertRule = (rule) => {
  ElMessage.info("告警规则编辑功能开发中");
};

const deleteAlertRule = async (ruleId) => {
  try {
    const response = await systemAPI.deleteAlertRule(ruleId);
    if (response && (response.success !== false)) {
      ElMessage.success("告警规则删除成功");
      await loadAlertRules();
    } else {
      ElMessage.error(response?.message || "删除告警规则失败");
    }
  } catch (error) {
    console.error("删除告警规则失败:", error);
    ElMessage.error(error.response?.data?.message || error.message || "删除告警规则失败");
  }
};

const handleTabChange = (tabName) => {
  if (tabName === "smtp") {
    loadSMTPConfig();
  } else if (tabName === "templates") {
    loadTemplates();
  } else if (tabName === "alerts") {
    loadAlertRules();
  }
};

const refreshAll = async () => {
  await Promise.all([loadSMTPConfig(), loadTemplates(), loadAlertRules()]);
  ElMessage.success("刷新成功");
};

onMounted(() => {
  loadSMTPConfig();
});
</script>

<style scoped>
.notification-config {
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
