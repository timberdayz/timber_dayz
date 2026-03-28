from backend.middleware.rate_limiter import _resolve_limiter_storage


class _StorageMarker:
    pass


class _LimiterWithStorage:
    def __init__(self, storage):
        self.storage = storage


class _InnerLimiter:
    def __init__(self, storage):
        self.storage = storage


class _LimiterWithInnerStorage:
    def __init__(self, storage):
        self._limiter = _InnerLimiter(storage)


class _LimiterWithPrivateStorage:
    def __init__(self, storage):
        self._storage = storage


def test_resolve_limiter_storage_prefers_private_storage():
    storage = _StorageMarker()
    limiter = _LimiterWithPrivateStorage(storage)

    resolved = _resolve_limiter_storage(limiter)

    assert resolved is storage


def test_resolve_limiter_storage_supports_public_storage_attr():
    storage = _StorageMarker()
    limiter = _LimiterWithStorage(storage)

    resolved = _resolve_limiter_storage(limiter)

    assert resolved is storage


def test_resolve_limiter_storage_supports_inner_limiter_storage():
    storage = _StorageMarker()
    limiter = _LimiterWithInnerStorage(storage)

    resolved = _resolve_limiter_storage(limiter)

    assert resolved is storage
