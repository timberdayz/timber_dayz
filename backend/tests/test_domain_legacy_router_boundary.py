from __future__ import annotations

import ast
from pathlib import Path


ALLOWED_LEGACY_ROUTER_IMPORTS: dict[str, list[str]] = {
    'backend/domains/business/routers/dashboard_api_postgresql.py': [
        'from backend.routers.dashboard_api_postgresql import *',
    ],
    'backend/domains/business/routers/follow_investment.py': [
        'from backend.routers.follow_investment import *',
    ],
    'backend/domains/business/routers/hr_attendance.py': [
        'from backend.routers.hr_attendance import *',
    ],
    'backend/domains/business/routers/hr_commission.py': [
        'from backend.routers.hr_commission import *',
    ],
    'backend/domains/business/routers/hr_department.py': [
        'from backend.routers.hr_department import *',
    ],
    'backend/domains/business/routers/hr_employee.py': [
        'from backend.routers.hr_employee import *',
    ],
    'backend/domains/business/routers/hr_salary.py': [
        'from backend.routers.hr_salary import *',
    ],
    'backend/domains/business/routers/monthly_profit_settlement.py': [
        'from backend.routers.monthly_profit_settlement import *',
    ],
    'backend/domains/business/routers/mv.py': [
        'from backend.routers.mv import *',
    ],
    'backend/domains/business/routers/performance_management.py': [
        'from backend.routers.performance_management import *',
    ],
    'backend/domains/business/routers/profit_basis.py': [
        'from backend.routers.profit_basis import *',
    ],
    'backend/domains/collection/routers/collection_tasks.py': [
        'from backend.routers.collection_tasks import *',
        'from backend.routers.collection_tasks import _execute_collection_task_background',
    ],
    'backend/domains/collection/routers/component_recorder.py': [
        'from backend.routers.component_recorder import *',
    ],
    'backend/domains/collection/routers/component_versions.py': [
        'from backend.routers.component_versions import *',
    ],
    'backend/domains/collection/routers/main_accounts.py': [
        'from backend.routers.main_accounts import *',
    ],
    'backend/domains/collection/routers/shop_account_aliases.py': [
        'from backend.routers.shop_account_aliases import *',
    ],
    'backend/domains/data_platform/routers/field_mapping_files.py': [
        'from backend.routers.field_mapping_files import *',
    ],
    'backend/domains/data_platform/routers/field_mapping_ingest.py': [
        'from backend.routers.field_mapping_ingest import *',
    ],
    'backend/domains/data_platform/routers/field_mapping_status.py': [
        'from backend.routers.field_mapping_status import *',
    ],
    'backend/domains/platform/compat/notifications.py': [
        'from backend.routers.notifications import create_notification as create_notification_func',
        'from backend.routers.notifications import notify_account_locked as notify_account_locked_func',
        'from backend.routers.notifications import notify_account_unlocked as notify_account_unlocked_func',
        'from backend.routers.notifications import notify_user_registered as notify_user_registered_func',
        'from backend.routers.notifications import revoke_all_user_sessions as revoke_all_user_sessions_func',
    ],
    'backend/domains/platform/routers/users.py': [
        'from backend.routers.users_admin import router as _admin_router',
        'from backend.routers.users_me import router as _me_router',
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
