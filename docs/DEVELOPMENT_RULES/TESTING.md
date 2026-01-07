# 测试策略规范 - 企业级ERP标准

**版本**: v4.4.0  
**更新**: 2025-01-30  
**标准**: 企业级测试标准

---

## 🏗️ 测试金字塔

### 1. 单元测试（70%）
- ✅ **快速**: 执行速度快（毫秒级）
- ✅ **隔离**: 测试单元独立，不依赖外部服务
- ✅ **覆盖**: 覆盖所有函数和类方法
- ✅ **工具**: pytest

### 2. 集成测试（20%）
- ✅ **模块交互**: 测试模块间的交互
- ✅ **数据库**: 测试数据库操作（使用测试数据库）
- ✅ **API**: 测试API端点（使用FastAPI TestClient）

### 3. E2E测试（10%）
- ✅ **关键流程**: 只测试关键业务流程
- ✅ **端到端**: 从前端到数据库完整流程
- ✅ **工具**: Playwright（前端E2E测试）

---

## 🧪 测试类型

### 1. 功能测试
- ✅ **业务逻辑**: 验证业务逻辑正确性
- ✅ **数据处理**: 验证数据处理正确性
- ✅ **业务规则**: 验证业务规则执行

### 2. 性能测试
- ✅ **负载测试**: 正常负载下的性能
- ✅ **压力测试**: 极限负载下的性能
- ✅ **基准测试**: 性能基准测试

### 3. 安全测试
- ✅ **漏洞扫描**: 安全漏洞扫描
- ✅ **渗透测试**: 安全渗透测试
- ✅ **权限测试**: 权限控制测试

### 4. 兼容性测试
- ✅ **浏览器兼容**: 主流浏览器兼容性
- ✅ **平台兼容**: Windows、macOS、Linux
- ✅ **版本兼容**: Python版本兼容性

---

## 📦 测试数据管理

### 1. 测试数据隔离
- ✅ **独立数据**: 每个测试使用独立数据
- ✅ **数据清理**: 测试后自动清理数据
- ✅ **数据工厂**: 使用工厂模式生成测试数据

### 2. 数据工厂
- ✅ **Faker**: 使用Faker生成假数据
- ✅ **Factory**: 使用工厂模式创建测试对象
- ✅ **Fixture**: 使用pytest fixture管理测试数据

**示例**:
```python
import factory
from modules.core.db import FactOrder

class FactOrderFactory(factory.Factory):
    class Meta:
        model = FactOrder
    
    order_id = factory.Sequence(lambda n: f"ORD{n:06d}")
    platform_code = "shopee"
    shop_id = "shop123"
    total_amount = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)
```

### 3. 数据清理
- ✅ **事务回滚**: 使用事务回滚自动清理
- ✅ **Fixture清理**: 使用pytest fixture清理
- ✅ **测试数据库**: 使用独立的测试数据库

---

## 🔧 测试工具

### 1. pytest（单元测试）
- ✅ **断言**: 丰富的断言函数
- ✅ **Fixture**: 强大的fixture系统
- ✅ **参数化**: 支持参数化测试
- ✅ **覆盖率**: pytest-cov集成

### 2. pytest-asyncio（异步测试）
- ✅ **异步支持**: 支持异步函数测试
- ✅ **异步Fixture**: 支持异步fixture

### 3. FastAPI TestClient（API测试）
- ✅ **API测试**: 测试FastAPI端点
- ✅ **请求模拟**: 模拟HTTP请求
- ✅ **响应验证**: 验证HTTP响应

### 4. Playwright（E2E测试）
- ✅ **浏览器自动化**: 自动化浏览器操作
- ✅ **多浏览器**: 支持Chrome、Firefox、Safari
- ✅ **截图**: 自动截图便于调试

---

## 📋 测试最佳实践

### 1. 测试命名
- ✅ **描述性**: 测试名称必须清晰描述测试内容
- ✅ **格式**: `test_<功能>_<场景>_<预期结果>`

**示例**:
```python
def test_create_order_with_valid_data_should_succeed():
    pass

def test_create_order_with_invalid_order_id_should_fail():
    pass
```

### 2. 测试结构
- ✅ **AAA模式**: Arrange（准备）、Act（执行）、Assert（断言）
- ✅ **独立性**: 每个测试独立，不依赖其他测试
- ✅ **可重复**: 测试可以重复执行

### 3. 测试覆盖
- ✅ **边界值**: 测试边界值（最大值、最小值）
- ✅ **异常情况**: 测试异常情况（错误输入、空值）
- ✅ **正常情况**: 测试正常情况

---

**最后更新**: 2025-01-30  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准

