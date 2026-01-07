## 贡献指南（开发框架与规则要点）

### 编码风格
- 使用 4 空格缩进，行宽 ≤ 88
- snake_case（函数/变量），PascalCase（类），常量 UPPER_SNAKE
- 类型注解 + Google 风格 docstring
- 导入顺序：标准库 / 第三方 / 本地

### 架构契约
- 依赖方向：apps → services → core；禁止 apps 之间互相 import
- __init__ 与模块顶层零副作用；注册器只读类级元数据，不实例化
- 配置经 config/ 与依赖注入传入；业务层禁止硬编码 URL（走 *_config.py）

### 自动化采集（Playwright）
- 只用 Playwright；Selenium 禁止
- 持久化上下文：按账号/店铺隔离 profiles 与下载目录
- 等待策略：显式等待 + 短轮询重试；关键步骤提供兜底
- TikTok 日期控件：多上下文点击（主文档+iframe）+ 2.5s 轮询 + 顶层面板等待

### 临时文件与清理
- 绝不直接删除；移动至 temp/archive/
- 时效阈值：development→7 天；outputs→30 天；media→90 天；logs→180 天
- 命名：YYYYMMDD_HHMMSS_功能_版本.扩展名

### 日志与诊断
- 只输出控制台日志（不默认写文件）
- 需要对比/诊断时，临时保存 HAR/截图至 temp/，周期性归档

### 测试
- 新功能需最小契约测试；首选最小粒度（单文件/单函数）
- 修改 core/services 时，优先补契约测试再改动

### 提交流程自检
- 是否破坏接口？是否提供兼容层或迁移说明？
- 是否新增/更新契约测试并本地通过？
- 是否限制变更半径并提供开关/适配层？
- 是否更新 README/ROADMAP/PROJECT_STATUS？

