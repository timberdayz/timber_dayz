import importlib
import sys
import warnings
from pathlib import Path


def _fresh_import_rate_limiter():
    sys.modules.pop("backend.middleware.rate_limiter", None)
    return importlib.import_module("backend.middleware.rate_limiter")


def test_rate_limiter_imports_when_env_limiter_file_is_missing(monkeypatch, tmp_path):
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path.name == ".env.limiter":
            return False
        return original_exists(path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = _fresh_import_rate_limiter()

    assert module.limiter is not None
    assert not any("Config file '.env.limiter' not found" in str(item.message) for item in caught)


def test_rate_limiter_uses_env_limiter_when_file_exists(monkeypatch):
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path.name == ".env.limiter":
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")

    module = _fresh_import_rate_limiter()

    assert module.limiter is not None
