# TODO任务分类清单

**创建日期**: 2025-11-05  
**总TODO数**: 17个  
**分类标准**: 优先级（P0紧急/P1重要/P2优化）

---

## 分类原则

- **P0 - 紧急**: 功能缺失，影响用户体验，需要立即修复
- **P1 - 重要**: 功能不完整，影响业务准确性，建议1个月内完成
- **P2 - 优化**: 改进建议，不影响核心功能，可持续优化

---

## P0 - 紧急任务（1个）

### 1. 数据隔离区重新处理逻辑

**位置**: `backend/routers/data_quarantine.py:302`

**代码**:
```python
# TODO: 实现实际的重新处理逻辑
```

**问题描述**:
- 数据隔离区的重新处理功能未实现
- 用户点击"重新处理"按钮后，数据未真正处理
- 只是记录日志，没有实际的数据修正和重新验证

**影响范围**:
- 用户体验严重受影响
- 隔离数据无法修复，导致数据丢失
- 数据隔离区功能不完整

**建议解决方案**:
```python
# 实现步骤
1. 从data_quarantine表读取隔离数据
2. 应用用户提供的corrections（修正）
3. 重新调用data_validator进行验证
4. 如果验证通过，插入到目标事实表
5. 更新data_quarantine表状态（is_resolved=True）
6. 记录解决日志（resolution_note）

# 参考代码
async def reprocess_quarantine_data(
    quarantine_ids: List[int],
    corrections: Dict[str, Any],
    db: Session
):
    results = []
    for qid in quarantine_ids:
        # 1. 读取隔离数据
        qdata = db.query(DataQuarantine).filter_by(id=qid).first()
        
        # 2. 应用修正
        corrected_data = {**qdata.raw_data, **corrections}
        
        # 3. 重新验证
        validation_result = validate_data(corrected_data, qdata.data_domain)
        
        if validation_result["valid"]:
            # 4. 插入目标表
            insert_to_fact_table(corrected_data, qdata.data_domain, db)
            
            # 5. 更新隔离区状态
            qdata.is_resolved = True
            qdata.resolved_at = datetime.utcnow()
            qdata.resolution_note = "手动修正并重新处理"
            db.commit()
            
            results.append({"quarantine_id": qid, "status": "success"})
        else:
            results.append({"quarantine_id": qid, "status": "failed", "errors": validation_result["errors"]})
    
    return results
```

**预计工作量**: 4小时

**验收标准**:
- 重新处理功能正常工作
- 验证通过的数据成功入库
- 隔离区状态正确更新
- 有完整的错误处理和日志

---

## P1 - 重要任务（9个）

### 1. 费用分摊FX转换

**位置**: `backend/routers/finance.py:632`

**代码**:
```python
base_amt=amount,  # TODO: FX转换
```

**问题描述**:
- 费用金额未转换为CNY本位币
- 财务报表金额可能不准确

**建议解决方案**:
```python
from backend.services.currency_converter import CurrencyConverter

converter = CurrencyConverter()
base_amt = converter.convert(amount, from_currency, 'CNY', rate_date)
```

**预计工作量**: 1小时

---

### 2-4. 采购管理FX转换（3处）

**位置**: 
- `backend/routers/procurement.py:78`
- `backend/routers/procurement.py:110`
- `backend/routers/procurement.py:424`

**问题描述**:
- 采购订单、采购行、入库单金额未转换为CNY
- 影响成本计算和P&L报表

**建议解决方案**:
```python
# 统一使用FxConversionService
from backend.services.fx_conversion import FxConversionService

fx_service = FxConversionService()
base_amt = fx_service.convert_to_base(
    amount=total_amt,
    from_currency=currency,
    rate_date=po_date
)
```

**预计工作量**: 2小时（3处统一处理）

---

### 5. 发票OCR识别

**位置**: `backend/routers/procurement.py:590`

**代码**:
```python
# TODO: OCR识别（集成OCR服务）
```

**问题描述**:
- 发票需要手动录入，效率低
- 容易出错

**建议解决方案**:
```python
# 集成第三方OCR服务
from backend.services.ocr_service import InvoiceOCRService

ocr = InvoiceOCRService(provider='tencent')  # 或 'aliyun', 'baidu'
invoice_data = ocr.recognize_invoice(file_path)

# 返回结构化数据
# {
#   "invoice_number": "...",
#   "invoice_date": "...",
#   "vendor_name": "...",
#   "total_amount": 1000.00,
#   "line_items": [...]
# }
```

**预计工作量**: 8小时（包括服务集成和测试）

**技术选型**:
- 腾讯云OCR: https://cloud.tencent.com/product/ocr
- 阿里云OCR: https://www.aliyun.com/product/ocr
- 百度OCR: https://cloud.baidu.com/product/ocr

---

### 6-7. 三单匹配逻辑完善（2处）

**位置**:
- `backend/routers/procurement.py:689`
- `backend/routers/procurement.py:693`

**代码**:
```python
# TODO: 实际匹配逻辑
invoice_line_id=None,  # TODO: 关联invoice_line
```

**问题描述**:
- 三单匹配（PO-GRN-Invoice）逻辑不完整
- 无法自动对账

**建议解决方案**:
```python
def match_three_way(po_id: str, grn_id: str, invoice_id: str, db: Session):
    """
    三单匹配逻辑
    
    匹配规则:
    1. 数量匹配: GRN数量 = Invoice数量（容差±5%）
    2. 金额匹配: GRN金额 = Invoice金额（容差±2%）
    3. 品名匹配: 品名相似度 > 80%
    """
    
    # 1. 查询PO行项目
    po_lines = db.query(POLine).filter_by(po_id=po_id).all()
    
    # 2. 查询GRN行项目
    grn_lines = db.query(GRNLine).filter_by(grn_id=grn_id).all()
    
    # 3. 查询Invoice行项目
    invoice_lines = db.query(InvoiceLine).filter_by(invoice_id=invoice_id).all()
    
    # 4. 逐行匹配
    match_results = []
    for po_line in po_lines:
        # 查找对应的GRN行
        grn_line = find_matching_grn_line(po_line, grn_lines)
        
        # 查找对应的Invoice行
        invoice_line = find_matching_invoice_line(po_line, invoice_lines)
        
        if grn_line and invoice_line:
            # 检查数量和金额差异
            qty_diff = abs(grn_line.qty_received - invoice_line.qty) / grn_line.qty_received
            amt_diff = abs(grn_line.total_amt - invoice_line.line_amt) / grn_line.total_amt
            
            match_status = 'matched' if (qty_diff < 0.05 and amt_diff < 0.02) else 'variance'
            
            match_results.append({
                "po_line_id": po_line.id,
                "grn_line_id": grn_line.id,
                "invoice_line_id": invoice_line.id,
                "match_status": match_status,
                "qty_variance": qty_diff,
                "amt_variance": amt_diff
            })
    
    # 5. 记录匹配日志
    log = ThreeWayMatchLog(
        po_id=po_id,
        grn_id=grn_id,
        invoice_id=invoice_id,
        match_results=match_results,
        created_at=datetime.utcnow()
    )
    db.add(log)
    db.commit()
    
    return match_results
```

**预计工作量**: 6小时

---

### 8-10. 平台和店铺识别优化（3处）

**位置**:
- `backend/routers/procurement.py:493`
- `backend/routers/procurement.py:494`
- `backend/routers/procurement.py:514`

**代码**:
```python
platform_code=grn.po_id[:grn.po_id.find('_')] if '_' in grn.po_id else 'unknown',  # TODO: 改进
shop_id='warehouse',  # TODO: 关联到实际店铺
```

**问题描述**:
- 平台代码从PO ID中硬编码提取
- 店铺ID固定为'warehouse'
- 数据归属不准确

**建议解决方案**:
```python
# 方案1: 从采购订单中提取
po = db.query(POHeader).filter_by(po_id=grn.po_id).first()
platform_code = po.platform_code if po else 'unknown'
shop_id = po.shop_id if po else 'warehouse'

# 方案2: 从供应商维度表关联
vendor = db.query(DimVendor).filter_by(vendor_id=po.vendor_id).first()
platform_code = vendor.default_platform if vendor else 'unknown'
```

**预计工作量**: 2小时

---

## P2 - 优化任务（5个）

### 1-2. 审计日志增强（2处）

**位置**:
- `backend/routers/auth.py:70`
- `backend/routers/auth.py:71`

**代码**:
```python
ip_address="127.0.0.1",  # TODO: 从请求中获取真实IP
user_agent="Unknown",    # TODO: 从请求中获取真实User-Agent
```

**问题描述**:
- 审计日志中IP和User-Agent信息缺失
- 不利于安全审计和问题排查

**建议解决方案**:
```python
from fastapi import Request

async def login(credentials: LoginRequest, request: Request):
    # 获取真实IP（考虑代理）
    ip_address = request.client.host
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    
    # 获取User-Agent
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # 记录审计日志
    audit_log = AuditLog(
        ip_address=ip_address,
        user_agent=user_agent,
        ...
    )
```

**预计工作量**: 1小时

---

### 3-5. 数据采集接口调整（3处）

**位置**:
- `backend/routers/collection.py:158`
- `backend/routers/collection.py:323`
- `backend/routers/collection.py:351`

**代码**:
```python
# TODO: 这里需要根据DataCollectionHandler的实际接口调整
# TODO: 调用实际的登录方法
# TODO: 调用实际的获取店铺方法
```

**问题描述**:
- API路由可能与Handler接口不匹配
- 需要验证接口一致性

**建议解决方案**:
```python
# 验证步骤
1. 检查DataCollectionHandler的实际接口
2. 对比API路由的调用方式
3. 如有不匹配，更新API路由或Handler
4. 添加集成测试确保一致性
```

**预计工作量**: 2小时（验证和测试）

---

## 任务执行计划

### 第1周（紧急任务）
- [ ] P0-1: 数据隔离区重新处理逻辑（4小时）

### 第2-3周（FX转换系列）
- [ ] P1-1: 费用分摊FX转换（1小时）
- [ ] P1-2~4: 采购管理FX转换（2小时）

### 第4周（采购管理优化）
- [ ] P1-8~10: 平台和店铺识别优化（2小时）

### 第5-6周（高级功能）
- [ ] P1-5: 发票OCR识别（8小时）
- [ ] P1-6~7: 三单匹配逻辑完善（6小时）

### 持续优化
- [ ] P2-1~2: 审计日志增强（1小时）
- [ ] P2-3~5: 数据采集接口调整（2小时）

**总计工作量**: 约26小时

---

## 执行建议

1. **分批执行**: 每次只执行1-2个任务，避免影响系统稳定性
2. **充分测试**: 每个任务完成后进行完整测试
3. **版本控制**: 每个任务提交一次Git，便于回滚
4. **文档更新**: 完成任务后更新相关文档
5. **架构验证**: 每次修改后运行`verify_architecture_ssot.py`

---

**文档维护**: 请在完成任务后更新此文档，标记完成状态  
**最后更新**: 2025-11-05

