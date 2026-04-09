from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


TemplateSaveMode = Literal["create", "new_version"]
TemplateUpdateMode = Literal["with-sample", "core-only"]
TemplateSaveOperation = Literal["created", "new_version"]


class TemplateSaveRequest(BaseModel):
    platform: str = Field(..., description="平台代码")
    data_domain: str = Field(..., description="数据域")
    header_columns: List[str] = Field(..., min_length=1, description="模板表头字段列表")
    granularity: Optional[str] = Field(None, description="粒度")
    account: Optional[str] = Field(None, description="账号")
    template_name: Optional[str] = Field(None, description="模板名称")
    created_by: str = Field("web_ui", description="创建人")
    header_row: int = Field(0, description="表头行索引")
    sub_domain: Optional[str] = Field(None, description="子类型")
    sheet_name: Optional[str] = Field(None, description="工作表名称")
    encoding: str = Field("utf-8", description="文件编码")
    deduplication_fields: Optional[List[str]] = Field(None, description="核心去重字段")
    mappings: Dict[str, Any] = Field(default_factory=dict, description="兼容旧前端的映射字段")
    save_mode: TemplateSaveMode = Field("create", description="保存语义")
    base_template_id: Optional[int] = Field(None, description="作为更新基础的模板ID")


class HeaderChangesPayload(BaseModel):
    detected: bool
    added_fields: List[str]
    removed_fields: List[str]
    match_rate: float
    is_exact_match: bool
    template_columns: List[str]
    current_columns: List[str]
    normalized_template_columns: List[str] = Field(default_factory=list)
    normalized_current_columns: List[str] = Field(default_factory=list)


class DetectHeaderChangesRequest(BaseModel):
    template_id: int = Field(..., description="模板ID")
    current_columns: List[str] = Field(..., min_length=1, description="当前表头字段列表")


class DetectHeaderChangesResponse(BaseModel):
    success: bool = True
    header_changes: HeaderChangesPayload


class TemplateContextSummary(BaseModel):
    id: int
    platform: str
    data_domain: str
    granularity: Optional[str] = None
    sub_domain: Optional[str] = None
    header_row: int = 0
    template_name: Optional[str] = None
    version: int
    status: Optional[str] = None
    field_count: int
    deduplication_fields: List[str] = Field(default_factory=list)


class TemplateCurrentFileSummary(BaseModel):
    id: int
    file_name: str
    platform: Optional[str] = None
    domain: Optional[str] = None
    granularity: Optional[str] = None
    sub_domain: Optional[str] = None


class TemplateSaveData(BaseModel):
    template_id: int
    template_name: str
    version: int
    operation: TemplateSaveOperation
    archived_template_id: Optional[int] = None
    save_mode: TemplateSaveMode
    base_template_id: Optional[int] = None


class TemplateSaveResponse(BaseModel):
    success: bool = True
    data: TemplateSaveData
    message: str


class TemplateUpdateContextData(BaseModel):
    template: TemplateContextSummary
    template_header_columns: List[str]
    current_file: Optional[TemplateCurrentFileSummary] = None
    current_header_columns: List[str]
    sample_data: Dict[str, Any] = Field(default_factory=dict)
    preview_data: List[Dict[str, Any]] = Field(default_factory=list)
    update_mode: TemplateUpdateMode
    header_source: str
    header_changes: HeaderChangesPayload
    match_rate: float
    added_fields: List[str]
    removed_fields: List[str]
    existing_deduplication_fields_available: List[str] = Field(default_factory=list)
    existing_deduplication_fields_missing: List[str] = Field(default_factory=list)
    recommended_deduplication_fields: List[str] = Field(default_factory=list)
    update_semantics: TemplateSaveOperation = "new_version"
    recommended_save_mode: TemplateSaveMode = "new_version"


class TemplateUpdateContextResponse(BaseModel):
    success: bool = True
    data: TemplateUpdateContextData
    message: str
