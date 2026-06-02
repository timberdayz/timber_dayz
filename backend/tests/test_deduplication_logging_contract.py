from backend.services.deduplication_service import DeduplicationService


def test_optional_missing_semantic_fields_are_debug_only(monkeypatch):
    from backend.services import deduplication_service as module

    service = DeduplicationService(db=None)
    row = {"dummy": "value"}
    header_bindings = []
    debug_messages = []
    info_messages = []

    class _Logger:
        @staticmethod
        def debug(message, *args, **kwargs):
            debug_messages.append(message % args if args else message)

        @staticmethod
        def info(message, *args, **kwargs):
            info_messages.append(message % args if args else message)

        @staticmethod
        def warning(*args, **kwargs):
            return None

    monkeypatch.setattr(module, "logger", _Logger())
    monkeypatch.setattr(module, "is_canonical_semantic_key", lambda value: True)
    monkeypatch.setattr(module, "normalize_semantic_key", lambda value: value)
    monkeypatch.setattr(
        module,
        "resolve_semantic_value",
        lambda row, semantic_key, header_bindings=None: (
            {"product_id": "P-001", "sku_id": "S-001", "order_id": "A-001"}.get(semantic_key),
            semantic_key if semantic_key != "platform_sku" else None,
        ),
    )
    monkeypatch.setattr(
        module,
        "get_semantic_requirements",
        lambda semantic_key: {"required": semantic_key == "order_id"},
    )

    service.calculate_data_hash(
        row,
        deduplication_fields=["product_id", "platform_sku", "sku_id", "order_id"],
        header_bindings=header_bindings,
    )

    assert any("可选核心字段未找到" in message for message in debug_messages)
    assert not any("部分核心字段未找到" in message for message in info_messages)


def test_missing_required_semantic_fields_still_log_info(monkeypatch):
    from backend.services import deduplication_service as module

    service = DeduplicationService(db=None)
    row = {"dummy": "value"}
    header_bindings = []
    info_messages = []

    class _Logger:
        @staticmethod
        def debug(*args, **kwargs):
            return None

        @staticmethod
        def info(message, *args, **kwargs):
            info_messages.append(message % args if args else message)

        @staticmethod
        def warning(*args, **kwargs):
            return None

    monkeypatch.setattr(module, "logger", _Logger())
    monkeypatch.setattr(module, "is_canonical_semantic_key", lambda value: True)
    monkeypatch.setattr(module, "normalize_semantic_key", lambda value: value)
    monkeypatch.setattr(
        module,
        "resolve_semantic_value",
        lambda row, semantic_key, header_bindings=None: (
            {"product_id": "P-001"}.get(semantic_key),
            semantic_key if semantic_key == "product_id" else None,
        ),
    )
    monkeypatch.setattr(
        module,
        "get_semantic_requirements",
        lambda semantic_key: {"required": semantic_key == "order_id"},
    )

    service.calculate_data_hash(
        row,
        deduplication_fields=["order_id", "product_id"],
        header_bindings=header_bindings,
    )

    assert any("部分核心字段未找到" in message for message in info_messages)
