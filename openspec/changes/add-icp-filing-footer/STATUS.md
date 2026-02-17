# 网站悬挂 ICP 备案号 - 状态

**变更 ID**: add-icp-filing-footer  
**创建日期**: 2026-02-17  
**状态**: 实施完成

---

## 摘要

- **目标**：在登录页与登录后全站页面底部左侧悬挂 ICP 备案号「ICP备案号：粤ICP备2026008583号」，并链接至工信部备案查询页，满足中国网络备案展示要求。
- **范围**：仅前端展示，无后端与数据库变更。

---

## 实施说明（2026-02-17）

- 新增 `frontend/src/components/common/IcpFooter.vue`：展示格式「ICP备案号：粤ICP备2026008583号」，号码可点击跳转 https://beian.miit.gov.cn/；支持 props：icpNumber、icpUrl、companyName（可选）、fixed（默认 true 固定视口底部左侧）；样式 12px、#666、链接 hover 下划线。
- 登录页：在 `Login.vue` 中引入 IcpFooter，固定于视口底部左侧。
- 登录后：在 `App.vue` 的 `.app-layout` 底部引入 IcpFooter，所有需登录页面底部左侧可见。

---

## 进度

| 阶段     | 状态   |
|----------|--------|
| 提案编写 | 已完成 |
| 审批     | 已完成 |
| 实施     | 已完成 |
| 验收     | 待人工确认 |
