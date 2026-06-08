from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


TemplateSaveMode = Literal["create", "new_version"]
TemplateUpdateMode = Literal["with-sample", "core-only"]
TemplateSaveOperation = Literal["created", "new_version"]
TemplateFieldParseRuleValueKind = Literal["single_date", "date_range"]
TemplateFieldParseRuleRangePick = Literal["start", "end"]
TemplateSemanticReviewStatus = Literal["pending", "confirmed_semantic", "confirmed_non_semantic"]


class TemplateHeaderBinding(BaseModel):
    raw_name: str = Field(..., description="Physical source column name")
    display_name: Optional[str] = Field(None, description="Human-readable semantic label")
    semantic_key: Optional[str] = Field(None, description="Stable semantic identity key such as order_id")
    semantic_role: Optional[str] = Field(None, description="Semantic role such as metric_date")
    aliases: List[str] = Field(default_factory=list, description="Alternative labels for matching")
    required: Optional[bool] = Field(None, description="Whether this semantic binding is required for sync")
    hash_participates: Optional[bool] = Field(None, description="Whether this binding participates in data_hash")
    semantic_review_status: Optional[TemplateSemanticReviewStatus] = Field(
        None,
        description="Manual review status for semantic identity governance",
    )
    position: Optional[int] = Field(None, description="0-based column position")
    sample_type: Optional[str] = Field(None, description="Sample-inferred type")
    confidence: Optional[float] = Field(None, description="Inference confidence")


class TemplateFieldParseRule(BaseModel):
    target_field: str = Field(..., description="Target standard field")
    source_column: str = Field(..., description="Original source column")
    source_label: Optional[str] = Field(None, description="Semantic display label for source column")
    source_aliases: List[str] = Field(default_factory=list, description="Alternative source labels")
    source_semantic_role: Optional[str] = Field(None, description="Semantic role for source column")
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
    header_bindings: Optional[List[TemplateHeaderBinding]] = Field(
        None,
        description="Template column semantic bindings",
    )
    sample_data: Dict[str, Any] = Field(default_factory=dict, description="Preview sample row keyed by source column")
    field_parse_rules: Optional[List[TemplateFieldParseRule]] = Field(
        None,
        description="Field-level parsing rules",
    )
    mappings: Dict[str, Any] = Field(default_factory=dict, description="Legacy compatible mappings payload")
    save_mode: TemplateSaveMode = Field("create", description="Save mode")
    base_template_id: Optional[int] = Field(None, description="Base template id")


class HashPolicyPreviewRequest(BaseModel):
    data_domain: str = Field(..., description="Data domain")
    granularity: Optional[str] = Field(None, description="Granularity")
    sub_domain: Optional[str] = Field(None, description="Sub domain")
    deduplication_fields: List[str] = Field(default_factory=list, description="Canonical hash identity keys")
    header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    field_parse_rules: List[TemplateFieldParseRule] = Field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)


class HashPolicyPreviewData(BaseModel):
    passed: bool
    blocking_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    resolved_keys: List[str] = Field(default_factory=list)
    requirement_groups: List[Dict[str, Any]] = Field(default_factory=list)
    effective_components: Dict[str, Any] = Field(default_factory=dict)
    invalid_keys: List[str] = Field(default_factory=list)
    missing_required_groups: List[Dict[str, Any]] = Field(default_factory=list)
    sample_diagnostics: Dict[str, Any] = Field(default_factory=dict)


class HashPolicyPreviewResponse(BaseModel):
    success: bool = True
    data: HashPolicyPreviewData


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
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)
    header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
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
    governance_checks: Dict[str, Any] = Field(default_factory=dict)


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
    resolved_object_type: str = "template_update"
    template: TemplateContextSummary
    template_header_columns: List[str]
    current_file: Optional[TemplateCurrentFileSummary] = None
    current_header_columns: List[str]
    current_header_row: int = 0
    sample_data: Dict[str, Any] = Field(default_factory=dict)
    preview_data: List[Dict[str, Any]] = Field(default_factory=list)
    current_header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    update_mode: TemplateUpdateMode
    header_source: str
    header_changes: HeaderChangesPayload
    match_rate: float
    added_fields: List[str]
    removed_fields: List[str]
    existing_deduplication_fields_available: List[str] = Field(default_factory=list)
    existing_deduplication_fields_missing: List[str] = Field(default_factory=list)
    recommended_deduplication_fields: List[str] = Field(default_factory=list)
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)
    update_semantics: TemplateSaveOperation = "new_version"
    recommended_save_mode: TemplateSaveMode = "new_version"


class TemplateUpdateContextResponse(BaseModel):
    success: bool = True
    data: TemplateUpdateContextData
    message: str


class TemplateUpdatePreviewData(BaseModel):
    current_file: TemplateCurrentFileSummary
    current_header_columns: List[str] = Field(default_factory=list)
    current_header_row: int = 0
    sample_data: Dict[str, Any] = Field(default_factory=dict)
    preview_data: List[Dict[str, Any]] = Field(default_factory=list)


class TemplateUpdatePreviewResponse(BaseModel):
    success: bool = True
    data: TemplateUpdatePreviewData
    message: str


class TemplateUpdateBindingsData(BaseModel):
    current_file: TemplateCurrentFileSummary
    current_header_columns: List[str] = Field(default_factory=list)
    current_header_row: int = 0
    current_header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)


class TemplateUpdateBindingsResponse(BaseModel):
    success: bool = True
    data: TemplateUpdateBindingsData
    message: str


class TemplateVariantCreateContextData(BaseModel):
    resolved_object_type: str = "variant_create"
    family: TemplateFamilyListItem
    active_version: Optional[TemplateVersionListItem] = None
    existing_variants: List[TemplateVariantListItem] = Field(default_factory=list)
    current_file: TemplateCurrentFileSummary
    current_header_columns: List[str] = Field(default_factory=list)
    current_header_row: int = 0
    sample_data: Dict[str, Any] = Field(default_factory=dict)
    preview_data: List[Dict[str, Any]] = Field(default_factory=list)
    current_header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)
    recommended_variant_key: str = ""
    recommended_parse_profile: Dict[str, Any] = Field(default_factory=dict)


class TemplateVariantCreateContextResponse(BaseModel):
    success: bool = True
    data: TemplateVariantCreateContextData
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
    header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
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


class TemplateFamilyActiveVersionSummary(BaseModel):
    id: int
    version_no: int
    status: str
    template_name: Optional[str] = None


class TemplateFamilyListItem(BaseModel):
    id: int
    platform: str
    data_domain: str
    granularity: Optional[str] = None
    account: Optional[str] = None
    sub_domain: Optional[str] = None
    display_name: Optional[str] = None
    governance_status: str = "ready"
    display_governance_status: str = "ready"
    variant_count: int = 0
    file_count: int = 0
    current_file_count: int = 0
    pending_file_count: int = 0
    historical_file_count: int = 0
    active_template_id: Optional[int] = None
    sample_file_id: Optional[int] = None
    sample_file_name: Optional[str] = None
    active_version: Optional[TemplateFamilyActiveVersionSummary] = None


class TemplateFamilyListData(BaseModel):
    families: List[TemplateFamilyListItem]
    count: int


class TemplateFamilyListResponse(BaseModel):
    success: bool = True
    data: TemplateFamilyListData


class TemplateVersionListItem(BaseModel):
    id: int
    family_id: int
    version_no: int
    status: str
    template_name: Optional[str] = None
    deduplication_fields: List[str] = Field(default_factory=list)
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)
    header_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    notes: Optional[str] = None
    variant_count: int = 0
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    legacy_template_ids: List[int] = Field(default_factory=list)


class TemplateFamilyVersionsData(BaseModel):
    family: TemplateFamilyListItem
    versions: List[TemplateVersionListItem]


class TemplateFamilyVersionsResponse(BaseModel):
    success: bool = True
    data: TemplateFamilyVersionsData


class TemplateVariantListItem(BaseModel):
    id: int
    template_version_id: int
    variant_key: str
    match_priority: int = 100
    header_row: int = 0
    sheet_name_pattern: Optional[str] = None
    required_headers: List[str] = Field(default_factory=list)
    parse_profile: Dict[str, Any] = Field(default_factory=dict)
    field_parse_rules: List[TemplateFieldParseRule] = Field(default_factory=list)
    source_legacy_template_id: Optional[int] = None
    template_name: Optional[str] = None
    created_at: Optional[str] = None


class TemplateVersionVariantsData(BaseModel):
    version: TemplateVersionListItem
    variants: List[TemplateVariantListItem]


class TemplateVersionVariantsResponse(BaseModel):
    success: bool = True
    data: TemplateVersionVariantsData


class TemplateResolveRequest(BaseModel):
    platform: str
    data_domain: str
    granularity: Optional[str] = None
    sub_domain: Optional[str] = None
    account: Optional[str] = None
    header_row: Optional[int] = None
    sheet_name: Optional[str] = None
    header_columns: List[str] = Field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)


class TemplateResolveShadowCompare(BaseModel):
    legacy_template_id: Optional[int] = None
    legacy_template_name: Optional[str] = None
    projected_variant_legacy_template_id: Optional[int] = None
    is_consistent: bool = False


class TemplateResolveData(BaseModel):
    matched: bool
    governance_status: str
    family: Optional[TemplateFamilyListItem] = None
    active_version: Optional[TemplateVersionListItem] = None
    variant: Optional[TemplateVariantListItem] = None
    semantic_bindings: List[TemplateHeaderBinding] = Field(default_factory=list)
    deduplication_fields: List[str] = Field(default_factory=list)
    field_parse_rules: List[TemplateFieldParseRule] = Field(default_factory=list)
    required_semantic_keys: List[str] = Field(default_factory=list)
    hash_participating_semantic_keys: List[str] = Field(default_factory=list)
    shadow_compare: TemplateResolveShadowCompare


class TemplateResolveResponse(BaseModel):
    success: bool = True
    data: TemplateResolveData


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


# Explicitly rebuild models with forward references so older Pydantic/FastAPI
# combinations used in CI can resolve response models during router import.
for _model in (
    TemplateVariantCreateContextData,
    TemplateVariantCreateContextResponse,
    TemplateFamilyVersionsData,
    TemplateFamilyVersionsResponse,
    TemplateVersionVariantsData,
    TemplateVersionVariantsResponse,
    TemplateResolveData,
    TemplateResolveResponse,
):
    _model.model_rebuild()
