<template>
  <footer class="icp-footer" :class="{ 'icp-footer--fixed': fixed }">
    <div class="icp-footer__inner">
      <p v-if="companyName" class="icp-footer__company">{{ companyName }}</p>
      <p class="icp-footer__icp">
        ICP备案号：
        <a
          :href="icpUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="icp-footer__link"
        >{{ icpNumber }}</a>
      </p>
    </div>
  </footer>
</template>

<script setup>
/**
 * ICP 备案号页脚组件
 * 用于登录页与登录后全站底部悬挂备案号，满足中国网络备案展示要求
 * 展示格式与业界主流一致：ICP备案号：粤ICP备xxxxxx号，链接至工信部
 */
const props = defineProps({
  /** 备案号，如 粤ICP备2026008583号 */
  icpNumber: {
    type: String,
    default: '粤ICP备2026008583号'
  },
  /** 工信部备案查询页 */
  icpUrl: {
    type: String,
    default: 'https://beian.miit.gov.cn/'
  },
  /** 可选：备案主体名称（公司全称），显示在备案号上一行 */
  companyName: {
    type: String,
    default: ''
  },
  /** 是否固定于视口底部左侧（登录页、登录后布局均可用 true） */
  fixed: {
    type: Boolean,
    default: true
  }
})
</script>

<style scoped>
.icp-footer {
  text-align: left;
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  padding: 8px 12px;
}

.icp-footer--fixed {
  position: fixed;
  bottom: 0;
  left: 0;
  right: auto;
  z-index: 100;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 -1px 0 rgba(0, 0, 0, 0.05);
}

.icp-footer__inner {
  padding: 0 16px;
}

.icp-footer__company {
  margin: 0 0 2px 0;
  font-size: 12px;
  color: #888;
}

.icp-footer__icp {
  margin: 0;
}

.icp-footer__link {
  color: #666;
  text-decoration: none;
}

.icp-footer__link:hover {
  text-decoration: underline;
  color: #333;
}
</style>
