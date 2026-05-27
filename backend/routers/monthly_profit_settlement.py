"""Legacy compatibility wrapper for monthly profit settlement router."""
# Do not add runtime logic here.

import backend.domains.business.routers.monthly_profit_settlement as domain_module

router = domain_module.router


def __getattr__(name: str):
    return getattr(domain_module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(domain_module)))


__all__ = getattr(
    domain_module,
    "__all__",
    [name for name in dir(domain_module) if not name.startswith("_")],
)
