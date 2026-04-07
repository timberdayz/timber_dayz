/**
 * 诊断 SimpleAccountSwitcher 组件问题
 * 在浏览器控制台运行此脚本
 */

console.log('=== SimpleAccountSwitcher 诊断工具 ===')

// 1. 检查组件是否在DOM中
const switcher = document.querySelector('.simple-account-switcher')
console.log('1. DOM检查:', switcher ? '✅ 找到组件' : '❌ 未找到组件')

if (switcher) {
  const styles = window.getComputedStyle(switcher)
  console.log('2. 样式检查:')
  console.log('   display:', styles.display)
  console.log('   visibility:', styles.visibility)
  console.log('   opacity:', styles.opacity)
  console.log('   width:', styles.width)
  console.log('   height:', styles.height)
  console.log('   position:', styles.position)
  console.log('   z-index:', styles.zIndex)
}

// 2. 检查Header组件
const header = document.querySelector('.header')
const headerActions = document.querySelector('.header-actions')
console.log('3. Header检查:')
console.log('   Header存在:', header ? '✅' : '❌')
console.log('   Header Actions存在:', headerActions ? '✅' : '❌')

if (headerActions) {
  const children = Array.from(headerActions.children)
  console.log('   Header Actions子元素数量:', children.length)
  children.forEach((child, index) => {
    console.log(`   子元素 ${index + 1}:`, child.className, child.tagName)
  })
}

// 3. 检查Vue实例
if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
  console.log('4. Vue DevTools:', '✅ 已安装')
} else {
  console.log('4. Vue DevTools:', '❌ 未安装')
}

// 4. 检查localStorage
console.log('5. localStorage检查:')
console.log('   access_token:', localStorage.getItem('access_token') ? '✅ 存在' : '❌ 不存在')
console.log('   user_info:', localStorage.getItem('user_info') ? '✅ 存在' : '❌ 不存在')
console.log('   activeRole:', localStorage.getItem('activeRole') || '未设置')

// 5. 检查控制台错误
console.log('6. 请检查控制台是否有红色错误信息')

console.log('=== 诊断完成 ===')
console.log('如果组件未找到，请检查：')
console.log('1. 浏览器是否缓存了旧版本（尝试 Ctrl+F5 强制刷新）')
console.log('2. 前端开发服务器是否正在运行（端口5173）')
console.log('3. 组件文件是否正确保存')
console.log('4. 浏览器控制台是否有JavaScript错误')
