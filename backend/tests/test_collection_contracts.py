from backend.services.collection_contracts import (
    count_collection_targets,
    iter_domain_targets,
    normalize_collection_date_range,
    normalize_domain_subtypes,
)


def test_normalize_domain_subtypes_scopes_values_per_domain(monkeypatch):
    monkeypatch.setattr(
        "backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES",
        {
            "services": ["agent", "ai_assistant"],
            "products": ["basic", "full"],
        },
    )

    normalized = normalize_domain_subtypes(
        data_domains=["orders", "services", "products"],
        domain_subtypes={
            "orders": ["agent"],
            "services": ["agent", "invalid"],
            "products": ["basic"],
            "unknown": ["x"],
        },
    )

    assert normalized == {
        "services": ["agent"],
        "products": ["basic"],
    }


def test_normalize_domain_subtypes_supports_legacy_flat_sub_domains(monkeypatch):
    monkeypatch.setattr(
        "backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES",
        {
            "services": ["agent", "ai_assistant"],
            "products": ["basic"],
        },
    )

    normalized = normalize_domain_subtypes(
        data_domains=["orders", "services", "products"],
        sub_domains=["agent", "basic"],
    )

    assert normalized == {
        "services": ["agent"],
        "products": ["basic"],
    }


def test_iter_domain_targets_and_count_follow_domain_boundaries(monkeypatch):
    monkeypatch.setattr(
        "backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES",
        {
            "services": ["agent", "ai_assistant"],
            "products": ["basic"],
        },
    )

    domain_subtypes = {
        "services": ["agent", "ai_assistant"],
        "products": ["basic"],
    }

    targets = list(iter_domain_targets(["orders", "services", "products"], domain_subtypes))

    assert targets == [
        ("orders", None, "orders"),
        ("services", "agent", "services:agent"),
        ("services", "ai_assistant", "services:ai_assistant"),
        ("products", "basic", "products:basic"),
    ]
    assert count_collection_targets(["orders", "services", "products"], domain_subtypes) == 4


def test_normalize_collection_date_range_prefers_start_date_end_date():
    normalized = normalize_collection_date_range(
        {
            "start_date": "2026-03-01",
            "end_date": "2026-03-07",
            "start": "2026-01-01",
            "end": "2026-01-07",
        }
    )

    assert normalized == {
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "date_from": "2026-03-01",
        "date_to": "2026-03-07",
    }
