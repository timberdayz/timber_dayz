"""Field mapping status router compat shim."""

import backend.routers.field_mapping_status as legacy_module

router = legacy_module.router


def __getattr__(name: str):
    return getattr(legacy_module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(legacy_module)))


__all__ = getattr(
    legacy_module,
    "__all__",
    [name for name in dir(legacy_module) if not name.startswith("_")],
)
