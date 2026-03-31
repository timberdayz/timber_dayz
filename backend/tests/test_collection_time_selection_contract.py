from datetime import date
from types import SimpleNamespace

import pytest

from backend.schemas.collection import CollectionConfigResponse, TimeSelectionPayload
from backend.services.collection_contracts import (
    build_date_range_from_time_selection,
    derive_granularity_from_time_selection,
    get_supported_config_data_domains,
    normalize_domain_subtypes,
    normalize_time_selection,
)


def test_derive_granularity_from_preset_follows_global_hard_rules():
    assert derive_granularity_from_time_selection({"mode": "preset", "preset": "today"}) == "daily"
    assert derive_granularity_from_time_selection({"mode": "preset", "preset": "yesterday"}) == "daily"
    assert derive_granularity_from_time_selection({"mode": "preset", "preset": "last_7_days"}) == "weekly"
    assert derive_granularity_from_time_selection({"mode": "preset", "preset": "last_30_days"}) == "monthly"


def test_derive_granularity_from_custom_requires_manual_input():
    assert derive_granularity_from_time_selection(
        {"mode": "custom", "start_date": "2026-03-01", "end_date": "2026-03-07"},
        "daily",
    ) == "daily"

    with pytest.raises(ValueError, match="granularity is required for custom"):
        derive_granularity_from_time_selection(
            {"mode": "custom", "start_date": "2026-03-01", "end_date": "2026-03-07"},
            None,
        )


def test_normalize_time_selection_accepts_legacy_collection_fields():
    normalized = normalize_time_selection(
        date_range_type="custom",
        custom_date_start=date(2026, 3, 1),
        custom_date_end=date(2026, 3, 7),
    )

    assert normalized == {
        "mode": "custom",
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }


def test_build_date_range_from_time_selection_for_last_7_days_is_inclusive():
    result = build_date_range_from_time_selection(
        {"mode": "preset", "preset": "last_7_days"},
        today=date(2026, 3, 27),
    )

    assert result == {
        "start_date": "2026-03-21",
        "end_date": "2026-03-27",
        "date_from": "2026-03-21",
        "date_to": "2026-03-27",
    }


def test_build_date_range_from_time_selection_for_last_30_days_is_inclusive():
    result = build_date_range_from_time_selection(
        {"mode": "preset", "preset": "last_30_days"},
        today=date(2026, 3, 27),
    )

    assert result == {
        "start_date": "2026-02-26",
        "end_date": "2026-03-27",
        "date_from": "2026-02-26",
        "date_to": "2026-03-27",
    }


def test_normalize_time_selection_rejects_preset_plus_custom_fields():
    with pytest.raises(ValueError, match="preset time selection cannot include custom"):
        normalize_time_selection(
            time_mode="preset",
            date_preset="today",
            start_date="2026-03-01",
            end_date="2026-03-07",
        )


def test_normalize_time_selection_rejects_custom_plus_preset_fields():
    with pytest.raises(ValueError, match="custom time selection cannot include preset"):
        normalize_time_selection(
            time_mode="custom",
            date_preset="today",
            start_date="2026-03-01",
            end_date="2026-03-07",
        )


def test_time_selection_payload_rejects_preset_without_preset_value():
    with pytest.raises(ValueError, match="preset time selection requires preset"):
        TimeSelectionPayload(mode="preset")


def test_time_selection_payload_rejects_custom_without_date_range():
    with pytest.raises(ValueError, match="custom time selection requires start_date and end_date"):
        TimeSelectionPayload(mode="custom")


def test_time_selection_payload_rejects_custom_with_preset_fields():
    with pytest.raises(ValueError, match="custom time selection cannot include preset"):
        TimeSelectionPayload(
            mode="custom",
            preset="last_7_days",
            start_date="2026-03-01",
            end_date="2026-03-07",
        )


def test_normalize_domain_subtypes_keeps_domain_scoped_mapping_only():
    normalized = normalize_domain_subtypes(
        data_domains=["orders", "services"],
        sub_domains={
            "orders": ["shopee", "invalid"],
            "services": ["agent", "ai_assistant"],
            "analytics": ["overview"],
        },
    )

    assert normalized == {
        "orders": ["shopee"],
        "services": ["agent", "ai_assistant"],
    }


def test_collection_config_response_derives_time_selection_from_legacy_fields():
    payload = CollectionConfigResponse.model_validate(
        SimpleNamespace(
            id=1,
            name="miaoshou-orders-v1",
            platform="miaoshou",
            account_ids=[],
            data_domains=["orders"],
            sub_domains={"orders": ["shopee"]},
            granularity="weekly",
            date_range_type="last_7_days",
            custom_date_start=None,
            custom_date_end=None,
            time_selection=None,
            schedule_enabled=False,
            schedule_cron=None,
            retry_count=3,
            is_active=True,
            created_at=date(2026, 3, 31),
            updated_at=date(2026, 3, 31),
            created_by=None,
        )
    )

    assert payload.time_selection is not None
    assert payload.time_selection.model_dump(exclude_none=True) == {
        "mode": "preset",
        "preset": "last_7_days",
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }


def test_get_supported_config_data_domains_keeps_default_domains_for_miaoshou():
    assert get_supported_config_data_domains("miaoshou") == [
        "orders",
        "products",
        "analytics",
        "finance",
        "services",
        "inventory",
    ]


def test_get_supported_config_data_domains_keeps_default_domains_for_other_platforms():
    assert get_supported_config_data_domains("shopee") == [
        "orders",
        "products",
        "analytics",
        "finance",
        "services",
        "inventory",
    ]
