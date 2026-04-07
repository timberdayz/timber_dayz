## MODIFIED Requirements

### Requirement: 数据归属规则
系统 SHALL 明确定义数据归属规则，包括 shop_id、account_id 等归属字段使用规则，以及 A/B/C 类数据的 schema 归属与迁移治理规则。

#### Scenario: A/B/C 类 schema 归属清晰
- **WHEN** 系统设计或调整数据库表结构
- **THEN** A 类配置数据应位于 `a_class` schema
- **AND** B 类业务数据应位于 `b_class` schema
- **AND** C 类计算数据应位于 `c_class` schema
- **AND** 跨 schema 外键必须保留并可验证

#### Scenario: public 表迁移至 A/C 类
- **WHEN** 已识别 public 中存在 A 类或 C 类表
- **THEN** 系统通过 Alembic 迁移将其迁移至目标 schema
- **AND** 迁移后更新 ORM、后端服务、脚本与 SQL 引用
- **AND** 在完成结构与业务校验后删除 public 旧表

#### Scenario: 迁移采用 Expand/Contract
- **WHEN** 执行跨 schema 迁移
- **THEN** 系统先执行 Expand（建新表、回填、切换引用）
- **AND** 再执行 Contract（校验通过后删除旧表）
- **AND** 迁移 SQL 使用显式列清单，禁止 `select *` 直接回填

#### Scenario: 迁移失败可回滚
- **WHEN** 迁移后发生结构错误或关键业务回归失败
- **THEN** 系统可通过 downgrade 或反向迁移恢复至迁移前状态
- **AND** 回滚后核心链路（目标管理、绩效公示、核心 Questions）可恢复可用
