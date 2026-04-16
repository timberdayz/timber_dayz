from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


TemplateSaveMode = Literal["create", "new_version"]
TemplateUpdateMode = Literal["with-sample", "core-only"]
TemplateSaveOperation = Literal["created", "new_version"]
TemplateFieldParseRuleValueKind = Literal["single_date", "date_range"]
TemplateFieldParseRuleRangePick = Literal["start", "end"]


class TemplateFieldParseRule(BaseModel):
    target_field: str = Field(..., description="Target standard field")
    source_column: str = Field(..., description="Original source column")
    value_kind: TemplateFieldParseRuleValueKind = Field(..., description="single_date or date_range")
    date_format: str = Field(..., description="Declared date format")
    strict: bool = Field(True, description="Whether parsing should be strict")
    range_pick: Optional[TemplateFieldParseRuleRangePick] = Field(
        None,
        description="start or end when value_kind is date_range",
    )


class TemplateSaveRequest(BaseModel):
    platform: str = Field(..., description="Platform code")
    data_domain: str = Field(..., description="Data domain")
    header_columns: List[str] = Field(..., min_length=1, description="Original header columns")
    granularity: Optional[str] = Field(None, description="Granularity")
    account: Optional[str] = Field(None, description="Account")
    template_name: Optional[str] = Field(None, description="Template name")
    created_by: str = Field("web_ui", description="Creator")
    header_row: int = Field(0, description="Header row index")
    sub_domain: Optional[str] = Field(None, description="Sub domain")
    sheet_name: Optional[str] = Field(None, description="Sheet name")
    encoding: str = Field("utf-8", description="File encoding")
    deduplication_fields: Optional[List[str]] = Field(None, description="Core deduplication fields")
    field_parse_rules: Optional[List[TemplateFieldParseRule]] = Field(
        None,
        description="Field-level parsing rules",
    )
    mappings: Dict[str, Any] = Field(default_factory=dict, description="Legacy compatible mappings payload")
    save_mode: TemplateSaveMode = Field("create", description="Save mode")
    base_template_id: Optional[int] = Field(None, description="Base template id")


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
    template_id: int = Field(..., description="Template id")
    current_columns: List[str] = Field(..., min_length=1, description="Current file columns")


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
    field_parse_rules: List[TemplateFieldParseRule] = Field(default_factory=list)


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


class DefaultDeduplicationFieldsData(BaseModel):
    fields: List[str]
    description: str
    reason: str


class DefaultDeduplicationFieldsResponse(BaseModel):
    success: bool = True
    data: DefaultDeduplicationFieldsData
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


class TemplateListItem(BaseModel):
    id: int
    platform: str
    data_domain: str
    granularity: Optional[str] = None
    account: Optional[str] = None
    sub_domain: Optional[str] = None
    header_row: int = 0
    sheet_name: Optional[str] = None
    encoding: str = "utf-8"
    template_name: Optional[str] = None
    version: int
    status: Optional[str] = None
    field_count: int = 0
    deduplication_fields: List[str] = Field(default_factory=list)
    field_parse_rules: List[TemplateFieldParseRule] = Field(default_factory=list)
    usage_count: int = 0
    success_rate: float = 0.0
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class TemplateListData(BaseModel):
    templates: List[TemplateListItem]
    count: int


class TemplateListResponse(BaseModel):
    success: bool = True
    data: TemplateListData


class TemplateDeleteData(BaseModel):
    template_id: int


class TemplateDeleteResponse(BaseModel):
    success: bool = True
    data: TemplateDeleteData
    message: str


class TemplateApplyRequest(BaseModel):
    template_id: int = Field(..., description="Template id")
    columns: List[str] = Field(..., min_length=1, description="Current columns")


class TemplateApplyConfig(BaseModel):
    header_row: int = 0
    sub_domain: Optional[str] = None
    sheet_name: Optional[str] = None
    encoding: str = "utf-8"


class TemplateApplyResponse(BaseModel):
    success: bool = True
    mappings: Dict[str, Any] = Field(default_factory=dict)
    matched: int
    unmatched: int
    unmatched_columns: List[str] = Field(default_factory=list)
    match_rate: float
    config: TemplateApplyConfig
    template_name: Optional[str] = None
    template_version: Optional[int] = None
    header_columns: List[str] = Field(default_factory=list)
    header_changes: HeaderChangesPayload
