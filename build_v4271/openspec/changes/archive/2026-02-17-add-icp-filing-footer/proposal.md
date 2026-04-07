# Change: 网站悬挂 ICP 备案号

## Why

根据中国《互联网信息服务管理办法》及工信部要求，已备案网站在上线后须在网站底部展示 ICP 备案号，并链接至工信部备案查询页（https://beian.miit.gov.cn/）。西虹 ERP 已部署于云端且已完成备案（粤ICP备2026008583号），需在登录页与登录后首页（及全站）底部左侧悬挂该备案号，以满足合规要求。

## What Changes

### 1. 新增公共组件

- 新增 `frontend/src/components/common/IcpFooter.vue`，用于展示备案信息。
- **展示格式**：业界主流为「ICP备案号：粤ICP备2026008583号」，其中号码部分（或整段）为可点击链接，指向 `https://beian.miit.gov.cn/`。
- **可选**：支持展示备案主体名称（如公司全称）在备案号上一行，由 props 或配置控制，便于后续扩展。
- **样式**：小号字体（建议 12px）、灰色系（如 #666 / #888），底部左对齐，不干扰主内容；链接新开窗口打开（`target="_blank"`，`rel="noopener noreferrer"`）；链接 hover 可下划线或颜色加深。

### 2. 登录页悬挂

- 在 `frontend/src/views/Login.vue` 底部左侧展示备案号（可固定于视口底部左侧，或置于 `.login-container` 底部）。
- 使用上述公共组件，保证与登录后页面展示一致。

### 3. 登录后全站悬挂

- 在 `frontend/src/App.vue` 的「非公开路由」布局（`.app-layout` 或 `.main-container`）底部左侧增加备案号展示（同一公共组件）。
- 使业务概览等所有登录后页面（含首页）均在底部左侧显示备案号。

### 4. 位置与样式约定

- **位置**：页面底部、左侧对齐（满足「首页左下方」要求）。
- **样式**：字号约 12px，颜色 #666 或 #888，左对齐，行高适中；可参考主流厂商 footer 风格（如腾讯云示例）；链接 hover 可下划线或加深色。
- **链接**：新开窗口打开 `https://beian.miit.gov.cn/`。

## Impact

### 受影响的规格

- **legal-compliance**：ADDED - 网站展示 ICP 备案号（新建能力）

### 受影响的代码

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| 前端 | `frontend/src/components/common/IcpFooter.vue` | 新增：备案号展示与工信部链接 |
| 前端 | `frontend/src/views/Login.vue` | 底部引入 IcpFooter |
| 前端 | `frontend/src/App.vue` | 非公开布局底部引入 IcpFooter |

### 依赖关系

- **无前置依赖**；无后端、数据库变更。

## 非目标（Non-Goals）

- 不增加公安备案号（若有需求可后续单独变更）。
- 不修改现有路由或权限逻辑，仅增加展示与链接。
