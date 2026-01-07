# 开发规范文档索引

**版本**: v4.4.0  
**更新**: 2025-01-30  
**位置**: `docs/DEVELOPMENT_RULES/`  
**状态**: ⛔ 受保护目录（禁止自动清理）

---

## 📚 详细规范文档

### P0级别（必须遵循）

1. **[数据库设计规范](DATABASE_DESIGN.md)** ⭐
   - 表设计原则、索引设计、约束设计
   - 字段类型规范、命名规范
   - 性能优化建议

2. **[错误处理和日志规范](ERROR_HANDLING_AND_LOGGING.md)** ⭐
   - 统一错误码体系、错误分类
   - 日志级别规范、结构化日志
   - 日志保留策略

3. **[监控和可观测性规范](MONITORING_AND_OBSERVABILITY.md)** ⭐
   - 指标监控、日志聚合、链路追踪
   - 告警规则、健康检查
   - 性能监控

### P1级别（强烈建议）

4. **[API设计规范](API_DESIGN.md)**
   - RESTful设计、统一响应格式
   - API版本控制、Rate Limiting
   - 分页规范、排序和筛选

5. **[安全规范](SECURITY.md)**
   - 用户认证、权限控制
   - OWASP Top 10防护
   - 安全审计、安全测试

6. **[代码质量保证规范](CODE_QUALITY.md)**
   - 代码审查流程、静态分析工具
   - 测试覆盖率要求、性能基准测试
   - 代码复杂度、文档要求

### P2级别（建议）

7. **[测试策略规范](TESTING.md)**
   - 测试金字塔、测试类型
   - 测试数据管理、测试工具

8. **[部署和运维规范](DEPLOYMENT.md)**
   - CI/CD流程、部署策略
   - 运维标准、监控和告警

9. **[UI设计规范](UI_DESIGN.md)**
   - Vue.js 3组件开发规范
   - 布局和视觉设计标准
   - 数据可视化和交互设计

---

## 🛡️ 保护机制

**目录保护**: `docs/DEVELOPMENT_RULES/`目录下的所有文件禁止自动清理

**保护规则**:
- ❌ **绝对禁止**: Agent自动删除此目录下的任何文件
- ❌ **绝对禁止**: 移动此目录下的文件到archive/
- ❌ **绝对禁止**: 重命名或修改此目录
- ✅ **唯一例外**: 用户显式授权删除或修改

**Agent检查清单**:
- [ ] 我是否要删除`docs/DEVELOPMENT_RULES/`下的文件？（**绝对禁止！**）
- [ ] 我是否要移动`docs/DEVELOPMENT_RULES/`下的文件？（**绝对禁止！**）
- [ ] 我是否要创建新的详细规范文档？（应该放在`docs/DEVELOPMENT_RULES/`）

---

## 📖 快速参考

### 开发前必读
1. `.cursorrules` - 核心开发规范（精简版）
2. `docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md` - 数据库设计规范
3. `docs/DEVELOPMENT_RULES/API_DESIGN.md` - API设计规范

### 开发中参考
- `docs/DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md` - 错误处理规范
- `docs/DEVELOPMENT_RULES/CODE_QUALITY.md` - 代码质量规范
- `docs/DEVELOPMENT_RULES/SECURITY.md` - 安全规范

### 部署运维参考
- `docs/DEVELOPMENT_RULES/DEPLOYMENT.md` - 部署和运维规范
- `docs/DEVELOPMENT_RULES/MONITORING_AND_OBSERVABILITY.md` - 监控规范

---

**最后更新**: 2025-01-30  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准

