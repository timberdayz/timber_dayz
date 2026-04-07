from modules.core.db import (
    BackupRecord,
    DimRole,
    DimUser,
    user_roles,
)
from modules.core.db.schema import (
    AlertRule,
    FactAuditLog,
    FactRateLimitConfigAudit,
    Notification,
    NotificationTemplate,
    SecurityConfig,
    SMTPConfig,
    SystemConfig,
    SystemLog,
    UserApprovalLog,
    UserNotificationPreference,
    UserSession,
)


def test_wave_b3_tables_bind_explicitly_to_core_schema():
    assert DimUser.__table__.schema == "core"
    assert DimUser.__table__.fullname == "core.dim_users"
    assert DimRole.__table__.schema == "core"
    assert DimRole.__table__.fullname == "core.dim_roles"
    assert BackupRecord.__table__.schema == "core"
    assert BackupRecord.__table__.fullname == "core.backup_records"


def test_user_roles_stays_public_but_targets_core_user_tables():
    assert user_roles.schema is None
    fk_targets = {fk.target_fullname for fk in user_roles.foreign_keys}

    assert "core.dim_users.user_id" in fk_targets
    assert "core.dim_roles.role_id" in fk_targets


def test_user_related_foreign_keys_target_core_dim_users():
    models = [
        UserSession,
        UserApprovalLog,
        FactAuditLog,
        FactRateLimitConfigAudit,
        Notification,
        UserNotificationPreference,
        SystemLog,
        SecurityConfig,
        BackupRecord,
        SMTPConfig,
        NotificationTemplate,
        AlertRule,
        SystemConfig,
    ]
    fk_targets = set()
    for model in models:
        fk_targets.update(fk.target_fullname for fk in model.__table__.foreign_keys)

    assert "core.dim_users.user_id" in fk_targets


def test_dim_user_self_reference_targets_core_dim_users():
    fk_targets = {fk.target_fullname for fk in DimUser.__table__.foreign_keys}

    assert "core.dim_users.user_id" in fk_targets


def test_notification_foreign_keys_target_core_dim_users():
    fk_targets = {fk.target_fullname for fk in Notification.__table__.foreign_keys}

    assert "core.dim_users.user_id" in fk_targets


def test_user_notification_preference_foreign_keys_target_core_dim_users():
    fk_targets = {fk.target_fullname for fk in UserNotificationPreference.__table__.foreign_keys}

    assert "core.dim_users.user_id" in fk_targets
