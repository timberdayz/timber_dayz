# 🎯 完整的映射审核和处理系统设计

## 📋 系统概述

本系统旨在解决跨境电商ERP中多平台Excel数据格式不统一的问题，通过智能字段映射和人工审核，实现数据的标准化入库。

### 🎯 核心目标
- **智能识别**: 自动识别Excel文件结构（标题行位置、数据类型）
- **智能映射**: AI驱动的字段映射，支持模糊匹配和语义识别
- **人工审核**: 提供直观的UI进行映射审核和调整
- **外键管理**: 特别关注外键关系的正确识别和映射
- **数据验证**: 入库前进行数据质量检查和验证
- **批量处理**: 支持批量文件的映射配置和应用

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Vue.js前端    │◄──►│   FastAPI后端   │◄──►│   Python服务    │
│                 │    │                 │    │                 │
│ • 文件管理      │    │ • REST API      │    │ • 文件扫描      │
│ • 映射审核      │    │ • 数据验证      │    │ • 智能映射      │
│ • 数据预览      │    │ • 错误处理      │    │ • 数据入库      │
│ • 外键管理      │    │ • 缓存管理      │    │ • 质量控制      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       ▼
         │                       │              ┌─────────────────┐
         │                       │              │   数据库层      │
         │                       │              │                 │
         │                       └──────────────►│ • catalog_files │
         │                                      │ • mapping_configs│
         │                                      │ • data_quarantine│
         │                                      │ • dim_* 表      │
         │                                      │ • fact_* 表     │
         └──────────────────────────────────────►└─────────────────┘
```

## 🔧 核心模块设计

### 1. 文件扫描与识别模块

#### 功能特性
- **多格式支持**: Excel (.xlsx, .xls), CSV, JSON
- **智能标题行识别**: 自动检测标题行位置（第1行、第3行等）
- **元数据提取**: 文件大小、修改时间、平台、店铺信息
- **增量扫描**: 只处理新增或修改的文件

#### API接口
```python
POST /api/scan
GET /api/file-groups
GET /api/catalog/status
POST /api/catalog/cleanup
```

### 2. 智能字段映射引擎

#### 映射策略
1. **精确匹配**: 字段名完全一致
2. **模糊匹配**: 使用字符串相似度算法
3. **语义匹配**: 基于同义词库和语义理解
4. **历史学习**: 从已批准的映射中学习
5. **数据内容分析**: 通过样本数据分析推断字段类型

#### 外键识别算法
```python
def identify_foreign_keys(source_columns, target_tables):
    """
    识别外键关系
    
    策略:
    1. 列名匹配: shop_id, product_id, order_id
    2. 数据内容匹配: 检查值与目标表主键的重合度
    3. 语义匹配: "店铺" -> shop_id, "商品" -> product_id
    4. 用户历史选择: 记录用户的外键映射偏好
    """
    foreign_keys = {}
    
    for column in source_columns:
        # 1. 基于列名识别
        if 'shop' in column.lower() or '店铺' in column:
            foreign_keys[column] = {
                'target_table': 'dim_shops',
                'target_field': 'shop_id',
                'confidence': 0.9
            }
        
        # 2. 基于数据内容匹配
        elif analyze_data_overlap(column, target_tables):
            match = find_best_match(column, target_tables)
            foreign_keys[column] = match
            
        # 3. 基于用户历史
        elif column in user_mapping_history:
            foreign_keys[column] = user_mapping_history[column]
    
    return foreign_keys
```

### 3. 交互式映射审核界面

#### UI设计原则
- **左右对比**: 源文件列 vs 目标数据库字段
- **拖放操作**: 支持拖拽进行字段映射
- **实时预览**: 映射后立即显示转换结果
- **错误高亮**: 数据类型不匹配、外键不存在等问题
- **批量操作**: 支持批量应用映射规则

#### 核心组件
```vue
<template>
  <div class="mapping-container">
    <!-- 文件选择区域 -->
    <FileSelector @file-selected="onFileSelected" />
    
    <!-- 映射编辑区域 -->
    <div class="mapping-editor">
      <div class="source-columns">
        <ColumnList :columns="sourceColumns" @drag-start="onDragStart" />
      </div>
      
      <div class="target-fields">
        <FieldList :fields="targetFields" @drop="onDrop" />
      </div>
    </div>
    
    <!-- 外键审核区域 -->
    <ForeignKeyReviewer 
      :foreign-keys="identifiedForeignKeys" 
      @confirm="onForeignKeyConfirm" 
    />
    
    <!-- 数据预览区域 -->
    <DataPreview :mappings="currentMappings" :data="previewData" />
    
    <!-- 操作按钮 -->
    <ActionButtons 
      @auto-map="onAutoMap"
      @validate="onValidate" 
      @save-mapping="onSaveMapping"
      @ingest="onIngest"
    />
  </div>
</template>
```

### 4. 数据验证与质量控制

#### 验证规则
1. **数据类型验证**: 数字、日期、字符串格式检查
2. **必填字段验证**: 检查必需字段是否为空
3. **外键存在性验证**: 确保外键值在目标表中存在
4. **业务规则验证**: 自定义业务逻辑验证
5. **数据一致性验证**: 跨字段的逻辑关系检查

#### 验证引擎
```python
class DataValidator:
    def validate_mapping(self, mappings, data):
        """验证映射和数据"""
        errors = []
        warnings = []
        
        for mapping in mappings:
            source_col = mapping['source']
            target_field = mapping['target']
            
            # 1. 数据类型验证
            if not self.validate_data_type(source_col, target_field, data):
                errors.append({
                    'type': 'data_type_mismatch',
                    'source': source_col,
                    'target': target_field,
                    'message': f'数据类型不匹配: {source_col} -> {target_field}'
                })
            
            # 2. 外键验证
            if target_field in self.foreign_key_fields:
                if not self.validate_foreign_key(source_col, target_field, data):
                    errors.append({
                        'type': 'foreign_key_invalid',
                        'source': source_col,
                        'target': target_field,
                        'message': f'外键值不存在: {source_col} -> {target_field}'
                    })
            
            # 3. 业务规则验证
            business_errors = self.validate_business_rules(mapping, data)
            errors.extend(business_errors)
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
```

### 5. 数据入库与错误处理

#### 入库策略
- **事务性操作**: 确保数据一致性
- **批量插入**: 提高性能
- **错误隔离**: 失败记录进入隔离表
- **重试机制**: 自动重试失败的记录
- **进度跟踪**: 实时显示入库进度

#### 错误处理
```python
class DataIngestionEngine:
    def ingest_file(self, file_path, mappings):
        """数据入库"""
        success_count = 0
        error_count = 0
        quarantine_records = []
        
        try:
            # 1. 读取和转换数据
            df = self.read_and_transform(file_path, mappings)
            
            # 2. 批量验证
            validation_result = self.validator.validate_dataframe(df, mappings)
            
            if not validation_result['valid']:
                # 分离有效和无效记录
                valid_df, invalid_df = self.separate_valid_invalid(df, validation_result['errors'])
                
                # 3. 有效数据入库
                if not valid_df.empty:
                    success_count = self.insert_valid_records(valid_df)
                
                # 4. 无效数据隔离
                if not invalid_df.empty:
                    quarantine_records = self.quarantine_invalid_records(invalid_df, validation_result['errors'])
                    error_count = len(quarantine_records)
            else:
                # 5. 全部数据入库
                success_count = self.insert_records(df)
                
        except Exception as e:
            # 6. 异常处理
            error_count = 1
            quarantine_records = [{
                'file_path': file_path,
                'error': str(e),
                'error_type': 'system_error'
            }]
        
        return {
            'success_count': success_count,
            'error_count': error_count,
            'quarantine_records': quarantine_records
        }
```

## 🗄️ 数据库设计

### 新增表结构

#### 1. mapping_configs (映射配置表)
```sql
CREATE TABLE mapping_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name VARCHAR(255) NOT NULL,
    platform_code VARCHAR(32),
    data_domain VARCHAR(64),
    file_pattern VARCHAR(255),
    mappings JSON NOT NULL,  -- 存储字段映射关系
    foreign_key_mappings JSON,  -- 存储外键映射关系
    validation_rules JSON,  -- 存储验证规则
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) DEFAULT 'active'
);
```

#### 2. data_quarantine (数据隔离表)
```sql
CREATE TABLE data_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path VARCHAR(1024) NOT NULL,
    record_data JSON NOT NULL,  -- 原始记录数据
    error_message TEXT NOT NULL,
    error_type VARCHAR(64),
    mapping_config_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(64),
    resolution_notes TEXT,
    FOREIGN KEY (mapping_config_id) REFERENCES mapping_configs(id)
);
```

#### 3. mapping_history (映射历史表)
```sql
CREATE TABLE mapping_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name VARCHAR(255) NOT NULL,
    platform_code VARCHAR(32),
    data_domain VARCHAR(64),
    source_column VARCHAR(255) NOT NULL,
    target_field VARCHAR(255) NOT NULL,
    mapping_type VARCHAR(32),  -- 'auto', 'manual', 'learned'
    confidence_score FLOAT,
    user_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🔄 工作流程

### 1. 文件上传与扫描
```
用户上传Excel文件 → 文件扫描 → 元数据提取 → 存储到catalog_files
```

### 2. 智能映射生成
```
选择文件 → 智能分析 → 生成映射建议 → 显示置信度
```

### 3. 人工审核与调整
```
查看映射建议 → 手动调整 → 外键审核 → 数据预览 → 验证通过
```

### 4. 映射配置保存
```
审核完成 → 保存映射配置 → 应用到同类文件 → 更新历史记录
```

### 5. 数据入库
```
确认映射 → 数据验证 → 批量入库 → 错误隔离 → 结果报告
```

## 🚀 实现计划

### Phase 1: 核心映射引擎 (Week 2)
- [ ] 实现智能字段映射算法
- [ ] 外键识别和匹配
- [ ] 基础数据验证
- [ ] API接口完善

### Phase 2: 前端UI增强 (Week 2)
- [ ] 交互式映射界面
- [ ] 拖放操作支持
- [ ] 实时数据预览
- [ ] 错误提示和修复建议

### Phase 3: 高级功能 (Week 3)
- [ ] 映射配置管理
- [ ] 批量处理支持
- [ ] 数据质量报告
- [ ] 历史学习功能

### Phase 4: 优化与测试 (Week 3)
- [ ] 性能优化
- [ ] 浏览器自动化测试
- [ ] 用户文档
- [ ] 部署准备

## 🎯 成功指标

### 功能指标
- **映射准确率**: ≥85% 自动映射正确率
- **处理速度**: ≤30秒/文件（1000行数据）
- **错误率**: ≤5% 数据入库错误率
- **用户满意度**: 界面操作流畅，学习成本低

### 技术指标
- **API响应时间**: ≤500ms
- **数据库查询性能**: ≤100ms
- **前端渲染时间**: ≤2秒
- **系统可用性**: ≥99%

## 📚 技术栈

### 后端
- **FastAPI**: 高性能异步API框架
- **SQLAlchemy**: ORM和数据访问层
- **Pandas**: 数据处理和分析
- **NumPy**: 数值计算
- **Scikit-learn**: 机器学习（相似度计算）

### 前端
- **Vue.js 3**: 现代化前端框架
- **Element Plus**: UI组件库
- **Pinia**: 状态管理
- **Vue Draggable**: 拖放功能
- **ECharts**: 数据可视化

### 数据库
- **SQLite**: 开发环境
- **PostgreSQL**: 生产环境
- **Redis**: 缓存层（可选）

---

这个设计为跨境电商ERP系统提供了一个完整的、可扩展的字段映射解决方案，能够有效处理多平台数据格式不统一的问题，同时保证数据质量和用户体验。
