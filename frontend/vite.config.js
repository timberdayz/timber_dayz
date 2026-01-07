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
    rollupOptions: {
      output: {
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]',
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
