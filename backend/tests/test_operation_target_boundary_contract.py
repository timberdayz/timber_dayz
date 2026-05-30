from backend.schemas.target import TargetCreateRequest, TargetResponse, TargetUpdateRequest
from modules.core.db import SalesTarget


def test_operation_target_contract_exposes_explicit_scope_type():
    assert "scope_type" in TargetCreateRequest.model_fields
    assert "scope_type" in TargetUpdateRequest.model_fields
    assert "scope_type" in TargetResponse.model_fields


def test_sales_target_model_exposes_scope_type_for_operation_boundary():
    columns = SalesTarget.__table__.c
    assert "scope_type" in columns
