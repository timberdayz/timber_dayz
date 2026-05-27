from __future__ import annotations

import ast
import importlib
from pathlib import Path


ALLOWED_LEGACY_ROUTER_IMPORTS: dict[str, list[str]] = {
    'backend/domains/platform/compat/notifications.py': [
        'from backend.routers.notifications import create_notification as create_notification_func',
        'from backend.routers.notifications import notify_account_locked as notify_account_locked_func',
        'from backend.routers.notifications import notify_account_unlocked as notify_account_unlocked_func',
        'from backend.routers.notifications import notify_password_reset as notify_password_reset_func',
        'from backend.routers.notifications import notify_user_approved as notify_user_approved_func',
        'from backend.routers.notifications import notify_user_registered as notify_user_registered_func',
        'from backend.routers.notifications import notify_user_rejected as notify_user_rejected_func',
        'from backend.routers.notifications import notify_user_suspended as notify_user_suspended_func',
        'from backend.routers.notifications import revoke_all_user_sessions as revoke_all_user_sessions_func',
    ],
}


def _is_legacy_router_module(module_name: str) -> bool:
    return module_name == 'backend.routers' or module_name.startswith('backend.routers.')


def _format_alias(alias: ast.alias) -> str:
    return f'{alias.name} as {alias.asname}' if alias.asname else alias.name


def _format_import_from(node: ast.ImportFrom) -> str:
    imported_names = ', '.join(sorted(_format_alias(alias) for alias in node.names))
    return f'from {node.module} import {imported_names}'


def _format_import(alias: ast.alias) -> str:
    return f'import {alias.name} as {alias.asname}' if alias.asname else f'import {alias.name}'


def _legacy_router_import_statements(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_legacy_router_module(node.module):
            hits.append(_format_import_from(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_legacy_router_module(alias.name):
                    hits.append(_format_import(alias))
    return sorted(set(hits))


def _scan_legacy_router_imports() -> dict[str, list[str]]:
    repo_root = Path(__file__).resolve().parents[2]
    targets = (repo_root / 'backend' / 'domains', repo_root / 'backend' / 'services')
    findings: dict[str, list[str]] = {}
    for base in targets:
        for path in base.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            hits = _legacy_router_import_statements(tree)
            if hits:
                findings[path.relative_to(repo_root).as_posix()] = hits
    return findings


def test_detects_all_backend_routers_runtime_import_shapes() -> None:
    tree = ast.parse(
        '\n'.join([
            'from backend.routers import users_admin as ua',
            'import backend.routers as legacy',
            'import backend.routers as old_legacy',
            'from backend.routers.users_me import router as me_router',
            'import backend.routers.notifications as notifications_legacy',
        ])
    )

    assert _legacy_router_import_statements(tree) == [
        'from backend.routers import users_admin as ua',
        'from backend.routers.users_me import router as me_router',
        'import backend.routers as legacy',
        'import backend.routers as old_legacy',
        'import backend.routers.notifications as notifications_legacy',
    ]


def test_domain_and_service_runtime_imports_do_not_expand_legacy_router_surface() -> None:
    actual = _scan_legacy_router_imports()
    assert actual == ALLOWED_LEGACY_ROUTER_IMPORTS, (
        'Found unexpected or changed backend.routers runtime imports. '
        'If the residual surface was intentionally changed, update the allowlist in this test '
        f'and refresh the Task 1 inventory summary. actual={actual}'
    )


def test_business_domain_runtime_imports_do_not_depend_on_backend_routers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    business_base = repo_root / 'backend' / 'domains' / 'business'
    findings: dict[str, list[str]] = {}
    for path in business_base.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        hits = _legacy_router_import_statements(tree)
        if hits:
            findings[path.relative_to(repo_root).as_posix()] = hits

    assert findings == {}, (
        'Business domain modules must not depend on backend.routers legacy modules. '
        f'found={findings}'
    )


def test_collection_domain_runtime_imports_do_not_depend_on_backend_routers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    collection_base = repo_root / 'backend' / 'domains' / 'collection'
    findings: dict[str, list[str]] = {}
    for path in collection_base.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        hits = _legacy_router_import_statements(tree)
        if hits:
            findings[path.relative_to(repo_root).as_posix()] = hits

    assert findings == {}, (
        'Collection domain modules must not depend on backend.routers legacy modules. '
        f'found={findings}'
    )


def test_data_platform_domain_runtime_imports_do_not_depend_on_backend_routers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    data_platform_base = repo_root / 'backend' / 'domains' / 'data_platform'
    findings: dict[str, list[str]] = {}
    for path in data_platform_base.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        hits = _legacy_router_import_statements(tree)
        if hits:
            findings[path.relative_to(repo_root).as_posix()] = hits

    assert findings == {}, (
        'Data platform domain modules must not depend on backend.routers legacy modules. '
        f'found={findings}'
    )


def test_platform_router_modules_do_not_depend_on_backend_routers() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    platform_router_base = repo_root / 'backend' / 'domains' / 'platform' / 'routers'
    findings: dict[str, list[str]] = {}
    for path in platform_router_base.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        hits = _legacy_router_import_statements(tree)
        if hits:
            findings[path.relative_to(repo_root).as_posix()] = hits

    assert findings == {}, (
        'Platform router modules must not depend on backend.routers legacy modules. '
        f'found={findings}'
    )


def _exported_names(module: object) -> set[str]:
    module_all = getattr(module, '__all__', None)
    if module_all is not None:
        return set(module_all)
    return {name for name in vars(module) if not name.startswith('_')}


def test_representative_domain_shims_preserve_legacy_public_exports() -> None:
    representative_pairs = [
    ]

    for shim_module_name, legacy_module_name in representative_pairs:
        shim_module = importlib.import_module(shim_module_name)
        legacy_module = importlib.import_module(legacy_module_name)

        missing_public_exports = _exported_names(legacy_module) - _exported_names(shim_module)
        assert not missing_public_exports, (
            f'{shim_module_name} narrowed the public export surface from {legacy_module_name}: '
            f'missing={sorted(missing_public_exports)}'
        )


def test_collection_tasks_shim_preserves_extra_helper_export() -> None:
    shim_module = importlib.import_module('backend.domains.collection.routers.collection_tasks')
    legacy_module = importlib.import_module('backend.routers.collection_tasks')

    assert (
        shim_module._execute_collection_task_background
        is legacy_module._execute_collection_task_background
    )


def test_users_domain_shim_preserves_legacy_public_exports() -> None:
    shim_module = importlib.import_module('backend.domains.platform.routers.users')
    admin_module = importlib.import_module('backend.routers.users_admin')
    me_module = importlib.import_module('backend.routers.users_me')

    expected_exports = (
        _exported_names(admin_module)
        | _exported_names(me_module)
        | {'require_admin', 'router'}
    )

    missing_public_exports = expected_exports - _exported_names(shim_module)
    assert not missing_public_exports, (
        'backend.domains.platform.routers.users narrowed the aggregated users export surface: '
        f'missing={sorted(missing_public_exports)}'
    )
