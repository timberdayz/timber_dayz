# Field Mapping API统一响应格式计划

**创建时间**: 2025-11-21  
**最后更新**: 2025-11-21  
**状态**: ✅ 已完成（所有端点已统一）

---

## 📊 当前状态

### ✅ 已完成
- ✅ 已导入统一响应格式工具函数（`success_response`, `error_response`, `pagination_response`）
- ✅ 已导入错误码体系（`ErrorCode`, `get_error_type`）
- ✅ 部分端点已使用统一格式：
  - `/file-groups` - ✅ 已使用`success_response`和`error_response`
  - `/quarantine-summary` - ✅ 已使用`success_response`和`error_response`
  - `/progress/{task_id}` - ✅ 已使用`success_response`和`error_response`
  - `/progress` - ✅ 已使用`success_response`和`error_response`
  - `/validate` - ✅ 已使用`success_response`和`error_response`
  - `/save-template` - ✅ 已使用`error_response`（废弃API）
  - `/apply-template` - ✅ 已使用`HTTPException`（废弃API，返回410）
  - `/templates` - ✅ 已使用`success_response`和`error_response`

### ⏳ 待统一端点（约30个）

#### 1. 文件管理相关端点
- ✅ `/bulk-ingest` - 已统一为`success_response`和`error_response`
- ✅ `/scan-files-by-date` - 已统一为`success_response`和`error_response`
- ✅ `/files` - 已统一为`success_response`和`error_response`
- ✅ `/scan` - 已统一为`success_response`和`error_response`
- ✅ `/file-info` - 已统一为`success_response`和`error_response`
- ✅ `/files-by-period` - 已统一为`success_response`和`error_response`

#### 2. 字段映射相关端点
- ✅ `/preview` - 已统一为`success_response`和`error_response`
- ✅ `/generate-mapping` - 已统一为`success_response`和`error_response`
- ✅ `/ingest` - 已统一为`success_response`和`error_response`

#### 3. 模板缓存相关端点
- ✅ `/template-cache/stats` - 已统一为`success_response`和`error_response`
- ✅ `/template-cache/cleanup` - 已统一为`success_response`和`error_response`
- ✅ `/template-cache/similar` - 已统一为`success_response`和`error_response`

#### 4. 成本自动填充相关端点
- ✅ `/cost-auto-fill/product` - 已统一为`success_response`和`error_response`
- ✅ `/cost-auto-fill/batch-update` - 已统一为`success_response`和`error_response`
- ✅ `/cost-auto-fill/auto-fill` - 已统一为`success_response`和`error_response`

#### 5. 其他端点
- ✅ `/data-domains` - 已统一为`success_response`
- ✅ `/field-mappings/{domain}` - 已统一为`success_response`
- ✅ `/bulk-validate` - 已统一为`success_response`和`error_response`
- ✅ `/cleanup` - 已统一为`success_response`和`error_response`
- ✅ `/needs-shop` - 已统一为`success_response`和`error_response`
- ✅ `/assign-shop` - 已统一为`success_response`和`error_response`
- ✅ `/catalog-status` - 已统一为`success_response`和`error_response`

---

## 🎯 统一策略

### 1. 成功响应统一
**当前格式**:
```python
return {
    "success": True,
    "data": {...}
}
```

**统一后格式**:
```python
return success_response(data={...})
```

### 2. 错误响应统一
**当前格式**:
```python
raise HTTPException(status_code=500, detail=f"错误信息: {str(e)}")
```

**统一后格式**:
```python
return error_response(
    code=ErrorCode.DATABASE_QUERY_ERROR,
    message="操作失败",
    error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
    detail=str(e),
    status_code=500
)
```

### 3. 特殊处理
- **废弃API** (`/save-template`, `/apply-template`): 保持`HTTPException`或`error_response`返回410状态码
- **文件不存在**: 使用`error_response`返回404状态码
- **参数验证错误**: 使用`error_response`返回400状态码

---

## 📝 执行步骤

### 阶段1: 文件管理端点（6个）
1. `/bulk-ingest` - 批量入库
2. `/scan-files-by-date` - 按日期扫描文件
3. `/files` - 获取文件列表
4. `/scan` - 扫描文件
5. `/file-info` - 获取文件信息
6. `/files-by-period` - 按周期查询文件

### 阶段2: 字段映射端点（3个）
1. `/preview` - 预览数据
2. `/generate-mapping` - 生成映射
3. `/ingest` - 数据入库

### 阶段3: 模板和缓存端点（6个）
1. `/template-cache/stats` - 缓存统计
2. `/template-cache/cleanup` - 清理缓存
3. `/template-cache/similar` - 查找相似模板
4. `/data-domains` - 获取数据域
5. `/field-mappings/{domain}` - 获取字段映射
6. `/catalog-status` - 获取目录状态

### 阶段4: 成本和其他端点（6个）
1. `/cost-auto-fill/product` - 获取商品成本
2. `/cost-auto-fill/batch-update` - 批量更新成本
3. `/cost-auto-fill/auto-fill` - 自动填充成本
4. `/bulk-validate` - 批量验证
5. `/cleanup` - 清理文件
6. `/needs-shop` - 需要店铺的文件
7. `/assign-shop` - 分配店铺

---

## ⚠️ 注意事项

1. **向后兼容**: 确保响应格式统一后，前端仍能正常解析数据
2. **错误处理**: 所有异常都应使用`error_response`，提供详细的错误信息
3. **数据格式**: 确保日期时间、金额等字段自动格式化（通过`format_response_data`）
4. **测试验证**: 每个端点统一后，需要验证前端调用是否正常

---

## 🔗 相关文档

- [API契约标准](docs/API_CONTRACTS.md)
- [API设计规范](docs/DEVELOPMENT_RULES/API_DESIGN.md)
- [统一响应格式工具](backend/utils/api_response.py)

