<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h1>西虹ERP系统</h1>
        <p>用户登录</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            size="large"
            prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            size="large"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="loginForm.rememberMe">记住我</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            style="width: 100%"
          >
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>

        <el-form-item class="login-links">
          <div style="display: flex; justify-content: space-between; width: 100%">
            <el-link type="primary" :underline="false" @click="$router.push('/register')">
              注册账号
            </el-link>
            <el-link type="info" :underline="false">
              忘记密码
            </el-link>
          </div>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
  rememberMe: false
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

// 验证redirect是否是合法的内部路径（防止Open Redirect漏洞）
const isValidRedirect = (url) => {
  if (!url) return false
  // 禁止协议（http:, https:, javascript:, data: 等）
  if (/^[a-z]+:/i.test(url)) return false
  // 禁止协议相对URL（//evil.com）
  if (url.startsWith("//")) return false
  // 禁止反斜杠（某些浏览器会转换）
  if (url.includes("\\")) return false
  // 只允许以 / 开头
  if (!url.startsWith("/")) return false
  // 防止 /\/evil.com 这种绕过（第二个字符是 / 或 \）
  if (url.length > 1 && (url[1] === "/" || url[1] === "\\")) return false
  return true
}

const handleLogin = async () => {
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const result = await authStore.login({
        username: loginForm.username,
        password: loginForm.password,
        remember_me: loginForm.rememberMe
      })

      if (result.success) {
        // 登录成功后重定向
        const redirect = route.query.redirect
        // 必须验证redirect参数，防止钓鱼攻击
        if (redirect && isValidRedirect(redirect)) {
          router.push(redirect)
        } else {
          router.push('/business-overview')
        }
      } else {
        // 错误处理（由store中的login方法处理，这里不需要额外处理）
      }
    } catch (error) {
      console.error('Login error:', error)
      // 错误消息已由store处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-box {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 10px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  font-size: 28px;
  color: #333;
  margin-bottom: 10px;
}

.login-header p {
  color: #666;
  font-size: 14px;
}

.login-form {
  margin-top: 20px;
}

.login-links {
  margin-bottom: 0;
}

:deep(.el-form-item) {
  margin-bottom: 20px;
}

:deep(.el-input__wrapper) {
  border-radius: 6px;
}
</style>

