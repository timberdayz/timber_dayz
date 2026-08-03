from datetime import date

from backend.schemas.performance import PerformanceConfigCreateRequest, PerformanceConfigResponse
from modules.core.db import PerformanceConfig


def test_performance_config_defaults_are_100_point_formal_scope():
    request = PerformanceConfigCreateRequest(effective_from=date(2026, 8, 1))

    assert request.sales_weight == 40
    assert request.profit_weight == 40
    assert request.key_product_weight == 0
    assert request.operation_weight == 20
    assert request.sales_max_score == 40
    assert request.profit_max_score == 40
    assert request.key_product_max_score == 0
    assert request.operation_max_score == 20


def test_performance_config_model_defaults_are_100_point_formal_scope():
    columns = PerformanceConfig.__table__.c

    assert columns.sales_weight.default.arg == 40
    assert columns.profit_weight.default.arg == 40
    assert columns.key_product_weight.default.arg == 0
    assert columns.operation_weight.default.arg == 20
    assert columns.sales_max_score.default.arg == 40
    assert columns.profit_max_score.default.arg == 40
    assert columns.key_product_max_score.default.arg == 0
    assert columns.operation_max_score.default.arg == 20


def test_performance_config_response_defaults_match_formal_scope():
    fields = PerformanceConfigResponse.model_fields

    assert fields["sales_max_score"].default == 40
    assert fields["profit_max_score"].default == 40
    assert fields["key_product_max_score"].default == 0
    assert fields["operation_max_score"].default == 20
