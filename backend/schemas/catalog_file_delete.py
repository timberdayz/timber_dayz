from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CatalogFileBatchDeleteRequest(BaseModel):
    file_ids: list[int] = Field(..., min_length=1, max_length=1000, description="文件ID列表")


class CatalogFileDeleteImpactResponse(BaseModel):
    file_id: int
    file_name: str
    platform_code: Optional[str] = None
    source_platform: Optional[str] = None
    data_domain: Optional[str] = None
    granularity: Optional[str] = None
    status: Optional[str] = None
    local_file_exists: bool = False
    meta_file_exists: bool = False
    quarantine_rows: int = 0
    staging_rows: int = 0
    fact_table_name: Optional[str] = None
    fact_rows: int = 0
    can_delete: bool = True
    warnings: list[str] = Field(default_factory=list)


class CatalogFileBatchDeleteImpactItemResponse(BaseModel):
    file_id: int
    file_name: Optional[str] = None
    status: Optional[str] = None
    can_delete: bool = False
    message: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class CatalogFileBatchDeleteImpactResponse(BaseModel):
    requested_count: int
    found_count: int
    missing_count: int = 0
    processing_count: int = 0
    deletable_count: int = 0
    ingested_like_count: int = 0
    local_file_exists_count: int = 0
    meta_file_exists_count: int = 0
    quarantine_rows: int = 0
    staging_rows: int = 0
    fact_rows: int = 0
    items: list[CatalogFileBatchDeleteImpactItemResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CatalogFileDeleteResultResponse(BaseModel):
    file_id: int
    fact_table_name: Optional[str] = None
    deleted_file: bool = False
    deleted_meta: bool = False
    deleted_catalog: bool = False
    deleted_quarantine_rows: int = 0
    deleted_staging_rows: int = 0
    deleted_fact_rows: int = 0
    warnings: list[str] = Field(default_factory=list)


class CatalogFileBatchDeleteResultItemResponse(BaseModel):
    file_id: int
    file_name: Optional[str] = None
    status: Optional[str] = None
    outcome: str
    message: str
    warnings: list[str] = Field(default_factory=list)


class CatalogFileBatchDeleteResultResponse(BaseModel):
    requested_count: int
    deleted_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: list[CatalogFileBatchDeleteResultItemResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
