# Tasks: 网站悬挂 ICP 备案号

## 1. 公共组件

- [x] 1.1 新建 `frontend/src/components/common/IcpFooter.vue`
  - 展示文案：**ICP备案号：粤ICP备2026008583号**（与工信部及业界主流一致）；链接可仅包号码或整段，点击跳转 https://beian.miit.gov.cn/（新开窗口，`target="_blank"`，`rel="noopener noreferrer"`）
  - 样式：字号约 12px，颜色 #666 或 #888，底部左对齐，行高适中，不干扰主内容；链接 hover 可下划线或颜色加深
- [x] 1.2 备案号、链接地址可配置为 props 或常量，便于后续更换；可选支持「备案主体名称」props（如公司全称），有则显示在备案号上一行，便于后续扩展公安备案等

## 2. 登录页

- [x] 2.1 在 `frontend/src/views/Login.vue` 底部左侧引入 IcpFooter（固定于视口底部左侧或置于 login-container 底部）

## 3. 登录后布局

- [x] 3.1 在 `frontend/src/App.vue` 的 `.app-layout` 或 `.main-container` 底部引入 IcpFooter，确保所有需登录页面底部左侧可见

## 4. 验收

- [x] 4.1 登录页：底部左侧显示「ICP备案号：粤ICP备2026008583号」，号码可点击，新开窗口跳转工信部
- [x] 4.2 登录后任意页（如业务概览）：底部左侧显示同一格式备案号与链接
