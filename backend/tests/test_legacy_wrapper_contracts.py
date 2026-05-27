from pathlib import Path


ROUTERS_DIR = Path("backend/routers")


def test_legacy_wrapper_modules_are_thin_and_logic_free():
    wrapper_files = []
    for path in ROUTERS_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        normalized = text.lstrip("\ufeff")
        if not normalized.startswith('"""Legacy compatibility wrapper'):
            continue
        wrapper_files.append((path, normalized))

    assert wrapper_files, "Expected legacy compatibility wrappers under backend/routers"

    offenders = {}
    for path, text in wrapper_files:
        file_offenders = []
        if "Do not add runtime logic here." not in text:
            file_offenders.append("missing no-runtime-logic marker")
        if "@router" in text:
            file_offenders.append("contains route decorator")
        if "APIRouter(" in text:
            file_offenders.append("contains APIRouter construction")

        is_alias_wrapper = "sys.modules[__name__] = domain_module" in text
        is_export_wrapper = (
            "router = domain_module.router" in text
            and "def __getattr__" in text
            and "__all__ =" in text
        )
        if not (is_alias_wrapper or is_export_wrapper):
            file_offenders.append("wrapper does not match alias/export pattern")

        if file_offenders:
            offenders[path.as_posix()] = file_offenders

    assert offenders == {}, (
        "Legacy wrappers must stay thin compatibility layers only. "
        f"offenders={offenders}"
    )
