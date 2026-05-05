from backend.domains.collection.routers import collection_config as _impl
for _name, _value in _impl.__dict__.items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

del _name, _value, _impl
