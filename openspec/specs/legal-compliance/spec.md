# legal-compliance Specification

## Purpose
TBD - created by archiving change add-icp-filing-footer. Update Purpose after archive.
## Requirements
### Requirement: 网站展示 ICP 备案号
已备案的网站 SHALL 在页面底部展示 ICP 备案号，格式含前缀「ICP备案号：」及号码（如粤ICP备2026008583号），并链接至工信部备案查询页（https://beian.miit.gov.cn/），以满足中国网络备案展示要求；可选展示备案主体名称于备案号上一行。

#### Scenario: 登录页展示
- **WHEN** 用户访问登录页（/login）
- **THEN** 页面底部左侧 SHALL 显示备案号，格式为「ICP备案号：粤ICP备2026008583号」
- **AND** 备案号（或整段）SHALL 为可点击链接，指向 https://beian.miit.gov.cn/

#### Scenario: 登录后页面展示
- **WHEN** 用户已登录并访问任意业务页（含首页/业务概览）
- **THEN** 页面底部左侧 SHALL 显示同一格式备案号
- **AND** 备案号（或整段）SHALL 为可点击链接，指向 https://beian.miit.gov.cn/

