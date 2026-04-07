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
        title="验证码信息已提交，系统正在恢复执行，请勿重复提交。"
        type="info"
        :closable="false"
        show-icon
      />

      <el-alert
        :title="instructionTitle"
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
        v-if="showScreenshot && screenshotUrl && !screenshotLoadFailed"
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
        <el-image
          :src="screenshotUrl"
          :preview-src-list="[screenshotUrl]"
          :initial-index="0"
          fit="contain"
          preview-teleported
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
        v-else-if="showScreenshot"
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
        验证码截图暂时不可用，请根据当前页面操作或稍后重试。
      </div>

      <div
        v-if="isManualContinue"
        style="
          padding: 12px;
          border-radius: 8px;
          background: #f5f7fa;
          border: 1px solid #e4e7ed;
          font-size: 13px;
          color: #606266;
          line-height: 1.7;
        "
      >
        <div>{{ manualContinueSummary }}</div>
        <div>完成后点击下方“我已处理完，继续”。</div>
        <div>不要关闭浏览器，也不要刷新当前页面。</div>
      </div>

      <el-input
        v-else
        ref="inputRef"
        v-model="localValue"
        :placeholder="inputPlaceholder"
        clearable
        :disabled="submitting"
        @keyup.enter="submit"
      />

      <div style="display: flex; justify-content: flex-end; gap: 12px">
        <el-button :disabled="submitting" @click="$emit('cancel')">
          {{ cancelText }}
        </el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ resolvedSubmitText }}
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
  verificationInputMode: { type: String, default: "" },
  screenshotUrl: { type: String, default: "" },
  submitting: { type: Boolean, default: false },
  message: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
  expiresAt: { type: String, default: "" },
  title: { type: String, default: "需要验证" },
  subtitle: {
    type: String,
    default: "当前流程已暂停，请先完成验证后继续。",
  },
  submitText: { type: String, default: "提交并继续" },
  cancelText: { type: String, default: "取消" },
});

const emit = defineEmits(["submit", "cancel"]);
const localValue = ref("");
const inputRef = ref(null);
const screenshotLoadFailed = ref(false);

const normalizedType = computed(() =>
  String(props.verificationType || "").toLowerCase(),
);

const isOtp = computed(() =>
  ["otp", "sms", "email_code"].includes(normalizedType.value),
);

const isManualContinue = computed(
  () => String(props.verificationInputMode || "").toLowerCase() === "manual_continue",
);

const isManualIntervention = computed(
  () => normalizedType.value === "manual_intervention",
);

const showScreenshot = computed(() => Boolean(props.screenshotUrl));

const instructionTitle = computed(() => {
  if (isManualContinue.value) {
    return isManualIntervention.value
      ? "检测到特殊情况需要用户处理，请在浏览器中处理完成后点击继续。"
      : "请在浏览器中手动完成滑块或人工验证，完成后点击继续。";
  }

  return isOtp.value
    ? "请输入收到的短信或邮件验证码"
    : "请根据下方截图输入图形验证码";
});

const manualContinueSummary = computed(() =>
  isManualIntervention.value
    ? "请在当前有头浏览器中处理特殊情况页面。"
    : "请在当前有头浏览器中手动完成滑块或人工验证。",
);

const inputPlaceholder = computed(() =>
  isOtp.value ? "请输入短信或邮件验证码" : "请输入图片中的验证码",
);

const resolvedSubmitText = computed(() => {
  if (isManualContinue.value) {
    return "我已处理完，继续";
  }

  return props.submitText;
});

const submit = () => {
  if (isManualContinue.value) {
    emit("submit", { manualCompleted: true });
    return;
  }

  const value = String(localValue.value || "").trim();
  if (!value) return;
  emit("submit", { value });
};

const handleImageError = () => {
  screenshotLoadFailed.value = true;
};

watch(
  () => [props.visible, props.screenshotUrl, props.verificationInputMode],
  async ([visible]) => {
    if (!visible) {
      localValue.value = "";
      screenshotLoadFailed.value = false;
      return;
    }

    screenshotLoadFailed.value = false;
    await nextTick();
    if (!isManualContinue.value) {
      inputRef.value?.focus?.();
    }
  },
);
</script>
