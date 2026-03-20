import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ['vue', 'vue-router', 'pinia'],
      dts: true,
    }),
    Components({
      resolvers: [ElementPlusResolver({
        importStyle: false
      })],
      dts: true,
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',  // v4.18.0: 使用0.0.0.0避免Windows权限问题
    strictPort: true,  // ✅ 强制使用5173端口，如果被占用则报错
    open: false,  // 禁用自动打开浏览器，由run.py统一管理
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api')
      }
    }
  },
  build: {
    target: 'es2015',
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]',
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          if (id.includes('vue-echarts')) {
            return 'vendor-vue-echarts'
          }

          if (id.includes('zrender')) {
            return 'vendor-zrender'
          }

          if (id.includes('echarts')) {
            if (id.includes('charts') || id.includes('\\chart\\') || id.includes('/chart/')) {
              return 'vendor-echarts-charts'
            }
            if (id.includes('components') || id.includes('\\component\\') || id.includes('/component/')) {
              return 'vendor-echarts-components'
            }
            return 'vendor-echarts-core'
          }

          if (id.includes('element-plus') || id.includes('@element-plus')) {
            if (
              id.includes('/table') || id.includes('\\table') ||
              id.includes('/pagination') || id.includes('\\pagination') ||
              id.includes('/descriptions') || id.includes('\\descriptions') ||
              id.includes('/statistic') || id.includes('\\statistic')
            ) {
              return 'vendor-element-plus-data'
            }

            if (
              id.includes('/date-picker') || id.includes('\\date-picker') ||
              id.includes('/time-picker') || id.includes('\\time-picker') ||
              id.includes('/calendar') || id.includes('\\calendar')
            ) {
              return 'vendor-element-plus-datetime'
            }

            if (
              id.includes('/form') || id.includes('\\form') ||
              id.includes('/input') || id.includes('\\input') ||
              id.includes('/select') || id.includes('\\select') ||
              id.includes('/checkbox') || id.includes('\\checkbox') ||
              id.includes('/radio') || id.includes('\\radio') ||
              id.includes('/switch') || id.includes('\\switch') ||
              id.includes('/upload') || id.includes('\\upload')
            ) {
              return 'vendor-element-plus-form'
            }

            if (
              id.includes('/message') || id.includes('\\message') ||
              id.includes('/notification') || id.includes('\\notification') ||
              id.includes('/message-box') || id.includes('\\message-box') ||
              id.includes('/loading') || id.includes('\\loading') ||
              id.includes('/dialog') || id.includes('\\dialog') ||
              id.includes('/drawer') || id.includes('\\drawer') ||
              id.includes('/popover') || id.includes('\\popover') ||
              id.includes('/tooltip') || id.includes('\\tooltip') ||
              id.includes('/overlay') || id.includes('\\overlay') ||
              id.includes('/popper') || id.includes('\\popper')
            ) {
              return 'vendor-element-plus-feedback'
            }

            return 'vendor-element-plus-base'
          }

          if (id.includes('vue-router') || id.includes('pinia') || id.includes('/vue/')) {
            return 'vendor-vue-core'
          }

          return 'vendor-misc'
        },
      },
    },
    // 生产环境优化配置（取消注释以启用）
    // 说明: 启用后会移除console.log、压缩代码，提升性能和安全性
    // 使用方法: 删除下面的注释符号（//）即可启用
    // minify: 'terser',
    // terserOptions: {
    //   compress: {
    //     drop_console: true,  // 移除所有console.log
    //     drop_debugger: true,  // 移除debugger语句
    //     pure_funcs: ['console.log', 'console.info']  // 移除特定函数
    //   }
    // }
  },
  optimizeDeps: {
    include: ['vue', 'vue-router', 'pinia', 'element-plus', 'echarts', 'axios'],
  },
})
