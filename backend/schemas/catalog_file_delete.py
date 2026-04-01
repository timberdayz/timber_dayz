from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
