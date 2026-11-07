"""标准字段定义 / 语义别名的接口契约。

[*] 批次 D(API-1): 这些契约描述的是**唯一一份**标准字段定义
(``backend.services.semantic_field_registry``)的对外投影。

以前前端在 ``headerBindings.js`` 里**自己抄了一份**标准字段定义
(360 行), 抄漏了 ``required``、``domain``, ``hash_participates`` 恒为 ``false``,
而且推断算法与后端各写各的 ⇒ 前端显示的「已自动识别」后端不一定认。

现在前端从 :class:`SemanticFieldDefinitionsResponse` 取,
契约与实现一一对应。
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SemanticFieldKind = Literal["identity", "time", "dimension", "metric", "attribute"]
SemanticAliasStatus = Literal["active", "disabled", "conflict"]
SemanticAliasSource = Literal["builtin", "template_confirmed", "manual"]


class SemanticFieldDefinition(BaseModel):
    """一个标准字段(语义键)的完整定义。"""

    semantic_key: str = Field(..., description="Stable semantic key, e.g. order_id")
    label: str = Field(..., description="Chinese display label")
    description: str = Field("", description="What this field identifies")
    kind: SemanticFieldKind = Field("attribute", description="Field category")
    domain: str = Field("common", description="Data domain this field belongs to")
    required: bool = Field(False, description="Whether the field is required by the domain contract")
    hash_eligible: bool = Field(False, description="Whether the field may take part in data_hash")
    default_hash: bool = Field(False, description="Whether the field is part of data_hash by default")
    system_scope: bool = Field(False, description="Whether the field comes from system scope, not from the file")
    identity_strength: Optional[str] = Field(None, description="identity / strong / weak")
    hash_warning: Optional[str] = Field(None, description="Human-readable hash caution")
    aliases: List[str] = Field(default_factory=list, description="All alternative labels")
    option_group: str = Field("attribute", description="Frontend option group key")


class SemanticFieldOption(BaseModel):
    """前端下拉框里的一个选项。"""

    value: str = Field(..., description="semantic_key")
    label: str = Field(..., description="Display label")
    description: str = Field("")
    kind: str = Field("attribute")
    domain: str = Field("common")
    group: str = Field("attribute")
    hash_eligible: bool = Field(False)
    default_hash: bool = Field(False)
    system_scope: bool = Field(False)
    identity_strength: Optional[str] = None
    hash_warning: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)


class SemanticFieldOptionGroup(BaseModel):
    label: str
    options: List[SemanticFieldOption] = Field(default_factory=list)


class SemanticDomainAliasEntry(BaseModel):
    """域限定的「业务别名 → 语义键」映射。"""

    data_domain: str
    semantic_key: str
    aliases: List[str] = Field(default_factory=list)


class SemanticColumnOverrideEntry(BaseModel):
    """域限定的「列名 → 语义键」映射。"""

    data_domain: str
    raw_name: str
    semantic_key: str


class SemanticFieldDefinitionsData(BaseModel):
    """API-1 的数据体。"""

    fields: List[SemanticFieldDefinition] = Field(default_factory=list)
    option_groups: List[SemanticFieldOptionGroup] = Field(default_factory=list)
    domain_aliases: List[SemanticDomainAliasEntry] = Field(default_factory=list)
    column_overrides: List[SemanticColumnOverrideEntry] = Field(default_factory=list)
    system_hash_scope_fields: List[str] = Field(default_factory=list)
    hash_identity_keys: List[str] = Field(default_factory=list)
    runtime_alias_count: int = Field(0, description="Number of alias rows loaded from the database")
    runtime_alias_loaded: bool = Field(False)
    runtime_alias_index: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="User-confirmed aliases: domain -> normalized alias -> semantic key",
    )
    runtime_builtin_alias_index: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Built-in aliases from the database: domain -> normalized alias -> semantic key",
    )


class SemanticFieldDefinitionsResponse(BaseModel):
    success: bool = True
    data: SemanticFieldDefinitionsData
    message: str = ""


class SemanticAliasRow(BaseModel):
    """别名表里的一行。"""

    id: Optional[int] = None
    data_domain: str = Field(..., description="'*' means the alias applies to every domain")
    standard_field: str
    raw_alias: str
    platform_code: Optional[str] = None
    granularity: Optional[str] = None
    source: SemanticAliasSource = "builtin"
    confidence: float = 1.0
    status: SemanticAliasStatus = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SemanticAliasListData(BaseModel):
    aliases: List[SemanticAliasRow] = Field(default_factory=list)
    total: int = 0


class SemanticAliasListResponse(BaseModel):
    success: bool = True
    data: SemanticAliasListData
    message: str = ""


class SemanticAliasConflict(BaseModel):
    """同名列名撞不同含义 —— 需要人来裁决。"""

    data_domain: str
    raw_alias: str
    platform_code: Optional[str] = None
    granularity: Optional[str] = None
    active_semantic_key: str = Field(..., description="The alias currently in effect")
    conflicting_semantic_key: str = Field(..., description="The newly asserted semantic key")
    conflict_id: Optional[int] = None
    source: str = "manual"
    status: SemanticAliasStatus = "conflict"


class SemanticAliasConflictListData(BaseModel):
    conflicts: List[SemanticAliasConflict] = Field(default_factory=list)
    total: int = 0


class SemanticAliasConflictListResponse(BaseModel):
    success: bool = True
    data: SemanticAliasConflictListData
    message: str = ""


class SemanticAliasResolveRequest(BaseModel):
    """别名裁决请求(API-5)。"""

    data_domain: str = Field(..., description="Domain of the alias, '*' for global scope")
    raw_alias: str = Field(..., min_length=1, description="Physical column name")
    semantic_key: str = Field(..., min_length=1, description="The semantic key the user picked")
    platform_code: Optional[str] = None
    granularity: Optional[str] = None
    action: Literal["accept", "disable", "reject"] = Field(
        "accept",
        description=(
            "accept: the picked semantic key wins and the alias takes effect; "
            "disable: keep the current alias but stop it from taking effect; "
            "reject: the new assertion is wrong, the current alias stays as is"
        ),
    )


class SemanticAliasResolveData(BaseModel):
    action: str
    data_domain: str
    raw_alias: str
    semantic_key: str
    affected_rows: int = 0
    message: str = ""


class SemanticAliasResolveResponse(BaseModel):
    success: bool = True
    data: SemanticAliasResolveData
    message: str = ""


class SemanticColumnResolveRequest(BaseModel):
    """批量列名 → 语义键 解析请求。

    前端推断与后端推断**必须是同一套规则** —— 否则前端显示「已自动识别」,
    后端却不认(FE-2)。这里把整批列名交给后端解析, 前端不再自己猜。
    """

    data_domain: str = Field("", description="Data domain of the columns")
    columns: List[str] = Field(default_factory=list, description="Physical column names")


class SemanticColumnResolveItem(BaseModel):
    column: str
    semantic_key: Optional[str] = None
    source: str = Field("none", description="Which rule produced the hit")


class SemanticColumnResolveData(BaseModel):
    results: List[SemanticColumnResolveItem] = Field(default_factory=list)
    data_domain: str = ""


class SemanticColumnResolveResponse(BaseModel):
    success: bool = True
    data: SemanticColumnResolveData
    message: str = ""
