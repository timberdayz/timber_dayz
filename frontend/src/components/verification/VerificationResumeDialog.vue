<template>
  <el-dialog
    :model-value="visible"
    width="520px"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :destroy-on-close="false"
    class="verification-dialog"
  >
    <template #header>
      <div style="display: flex; flex-direction: column; gap: 4px">
        <span style="font-size: 18px; font-weight: 600">{{ title }}</span>
        <span style="font-size: 13px; color: #909399">
          {{ subtitle }}
        </span>
      </div>
    </template>

    <div style="display: flex; flex-direction: column; gap: 16px">
      <el-alert
        v-if="submitting"
        title="验证码已提交，系统正在恢复执行，请勿重复提交。"
        type="info"
        :closable="false"
        show-icon
      />

      <el-alert
        :title="
          isOtp
            ? '请输入收到的短信或邮件验证码'
            : '请根据下方截图输入图形验证码'
        "
        type="warning"
        :closable="false"
        show-icon
      />

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <div v-if="message" style="font-size: 13px; color: #606266">
        {{ message }}
      </div>

      <div v-if="expiresAt" style="font-size: 12px; color: #909399">
        有效期至：{{ expiresAt }}
      </div>

      <div
        v-if="!isOtp && screenshotUrl && !screenshotLoadFailed"
        style="
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 180px;
          background: #f5f7fa;
          border: 1px solid #e4e7ed;
          border-radius: 8px;
          padding: 12px;
        "
      >
        <img
          :src="screenshotUrl"
          alt="验证码截图"
          style="
            max-width: 100%;
            max-height: 220px;
            border: 1px solid #dcdfe6;
            border-radius: 4px;
            background: #fff;
          "
          @error="handleImageError"
        />
      </div>

      <div
        v-else-if="!isOtp"
        style="
          min-height: 120px;
          display: flex;
          align-items: center;
          justify-content: center;
          text-align: center;
          background: #fafafa;
          border: 1px dashed #dcdfe6;
          border-radius: 8px;
          color: #909399;
          padding: 12px;
          font-size: 13px;
        "
      >
        验证码截图暂不可用，请根据当前页面或稍后重试。
      </div>

      <el-input
        ref="inputRef"
        v-model="localValue"
        :placeholder="isOtp ? '请输入短信或邮件验证码' : '请输入图片中的验证码'"
        clearable
        :disabled="submitting"
        @keyup.enter="submit"
      />

      <div style="display: flex; justify-content: flex-end; gap: 12px">
        <el-button @click="$emit('cancel')" :disabled="submitting">
          {{ cancelText }}
        </el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ submitText }}
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  verificationType: { type: String, default: "graphical_captcha" },
  screenshotUrl: { type: String, default: "" },
  submitting: { type: Boolean, default: false },
  message: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
  expiresAt: { type: String, default: "" },
  title: { type: String, default: "需要验证码" },
  subtitle: {
    type: String,
    default: "当前流程已暂停，请先完成验证码回填后继续。",
  },
  submitText: { type: String, default: "提交并继续" },
  cancelText: { type: String, default: "取消" },
});

const emit = defineEmits(["submit", "cancel"]);
const localValue = ref("");
const inputRef = ref(null);
const screenshotLoadFailed = ref(false);

const isOtp = computed(() =>
  ["otp", "sms", "email_code"].includes(
    String(props.verificationType || "").toLowerCase()
  )
);

const submit = () => {
  const value = String(localValue.value || "").trim();
  if (!value) return;
  emit("submit", value);
};

const handleImageError = () => {
  screenshotLoadFailed.value = true;
};

watch(
  () => [props.visible, props.screenshotUrl],
  async ([visible]) => {
    if (!visible) {
      localValue.value = "";
      screenshotLoadFailed.value = false;
      return;
    }
    screenshotLoadFailed.value = false;
    await nextTick();
    inputRef.value?.focus?.();
  }
);
</script>
