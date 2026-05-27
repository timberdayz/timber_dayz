from pathlib import Path


TARGETS = [
    Path("backend/domains/business/routers"),
    Path("backend/domains/collection/routers"),
    Path("backend/domains/data_platform/routers"),
    Path("backend/domains/platform/routers"),
]


def test_domain_router_modules_do_not_use_relative_parent_project_root_hops():
    banned_fragments = [
        "Path(__file__).parent.parent.parent",
        "PathLib(__file__).parent.parent.parent",
        "Path(__file__).resolve().parents[2]",
        "Path(__file__).resolve().parents[3]",
    ]

    offenders: dict[str, list[str]] = {}
    for base in TARGETS:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            hits = [fragment for fragment in banned_fragments if fragment in text]
            if hits:
                offenders[path.as_posix()] = hits

    assert offenders == {}, (
        "Domain router modules must not infer project root via fragile relative parent hops. "
        f"offenders={offenders}"
    )
