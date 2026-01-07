"""
账号对齐相关的Pydantic Schemas
用于账号别名管理、对齐统计、导入导出等API
"""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AlignmentStatsResponse(BaseModel):
    """对齐统计响应"""
    total_orders: int = Field(description="总订单数")
    aligned: int = Field(description="已对齐订单数")
    unaligned: int = Field(description="未对齐订单数")
    coverage_rate: float = Field(description="覆盖率")
    unique_raw_labels: int = Field(description="唯一原始标签数")


class MappingSuggestion(BaseModel):
    """映射建议"""
    raw_shop_label: str = Field(description="原始店铺标签")
    order_count: int = Field(description="订单数")
    suggested_account_id: Optional[str] = Field(None, description="建议的账号ID")


class MissingSuggestionsResponse(BaseModel):
    """缺失映射建议响应"""
    success: bool = Field(default=True)
    suggestions: List[MappingSuggestion] = Field(description="建议列表")
    count: int = Field(description="建议数量")


class AliasResponse(BaseModel):
    """别名响应"""
    id: int = Field(description="别名ID")
    account: str = Field(description="账号")
    site: str = Field(description="站点")
    store_label_raw: str = Field(description="原始店铺标签")
    target_id: Optional[str] = Field(None, description="目标ID")
    confidence: Optional[float] = Field(None, description="置信度")
    active: bool = Field(description="是否激活")
    notes: Optional[str] = Field(None, description="备注")
    created_by: Optional[str] = Field(None, description="创建人")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    
    model_config = ConfigDict(from_attributes=True)


class AliasListResponse(BaseModel):
    """别名列表响应"""
    success: bool = Field(default=True)
    aliases: List[AliasResponse] = Field(description="别名列表")
    count: int = Field(description="别名数量")


class AddAliasRequest(BaseModel):
    """添加别名请求"""
    platform: str = Field(..., description="平台代码")
    raw_shop_label: str = Field(..., description="原始店铺标签")
    account_id: str = Field(..., description="账号ID")


class AddAliasResponse(BaseModel):
    """添加别名响应"""
    success: bool = Field(default=True)
    message: str = Field(description="操作消息")
    alias_id: Optional[int] = Field(None, description="创建的别名ID")


class BatchAddAliasesRequest(BaseModel):
    """批量添加别名请求"""
    platform: str = Field(..., description="平台代码")
    mappings: List[dict] = Field(..., description="映射列表 [{raw_shop_label, account_id}, ...]")


class BatchAddAliasesResponse(BaseModel):
    """批量添加别名响应"""
    success: bool = Field(default=True)
    added: int = Field(description="成功添加数")
    skipped: int = Field(description="跳过数")
    errors: List[str] = Field(default_factory=list, description="错误列表")


class BackfillRequest(BaseModel):
    """回填请求"""
    platform: str = Field(default='miaoshou', description="平台代码")
    limit: Optional[int] = Field(None, description="限制处理数量")


class BackfillResponse(BaseModel):
    """回填响应"""
    success: bool = Field(default=True)
    updated: int = Field(description="更新的订单数")
    message: str = Field(description="操作消息")


class ImportResponse(BaseModel):
    """导入响应"""
    success: bool = Field(default=True)
    imported: int = Field(description="导入的别名数")
    skipped: int = Field(description="跳过的别名数")
    errors: List[str] = Field(default_factory=list, description="错误列表")


class UpdateAliasRequest(BaseModel):
    """更新别名请求"""
    target_id: Optional[str] = Field(None, description="目标ID")
    notes: Optional[str] = Field(None, description="备注")
    active: Optional[bool] = Field(None, description="是否激活")


class UpdateAliasResponse(BaseModel):
    """更新/删除别名响应"""
    success: bool = Field(default=True)
    message: str = Field(description="操作消息")


class DistinctRawStoresResponse(BaseModel):
    """不同原始店铺响应"""
    success: bool = Field(default=True)
    stores: List[str] = Field(description="店铺列表")
    count: int = Field(description="店铺数量")

