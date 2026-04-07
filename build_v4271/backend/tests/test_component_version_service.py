from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.services.component_version_service import ComponentVersionService
from modules.core.db import Base, ComponentVersion


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    ComponentVersion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal(), engine


def test_register_version_never_creates_stable_directly():
    session, engine = _make_session()
    try:
        service = ComponentVersionService(session)
        version = service.register_version(
            component_name="shopee/login",
            version="1.0.0",
            file_path="modules/platforms/shopee/components/login_v1_0_0.py",
            description="manual register",
            is_stable=True,
            created_by="tester",
        )

        assert version.is_stable is False
        assert version.is_active is True
        assert version.is_testing is False
    finally:
        session.close()
        engine.dispose()


def test_promote_to_stable_clears_previous_stable_and_testing_flags():
    session, engine = _make_session()
    try:
        old_stable = ComponentVersion(
            component_name="shopee/orders_export",
            version="1.0.0",
            file_path="modules/platforms/shopee/components/orders_export_v1_0_0.py",
            is_stable=True,
            is_active=True,
            is_testing=False,
        )
        candidate = ComponentVersion(
            component_name="shopee/orders_export",
            version="1.1.0",
            file_path="modules/platforms/shopee/components/orders_export_v1_1_0.py",
            is_stable=False,
            is_active=True,
            is_testing=True,
        )
        session.add_all([old_stable, candidate])
        session.commit()

        service = ComponentVersionService(session)
        promoted = service.promote_to_stable("shopee/orders_export", "1.1.0")
        session.refresh(old_stable)
        session.refresh(candidate)

        assert promoted.id == candidate.id
        assert candidate.is_stable is True
        assert candidate.is_testing is False
        assert old_stable.is_stable is False
    finally:
        session.close()
        engine.dispose()


def test_get_all_stable_versions_only_returns_active_stable_rows():
    session, engine = _make_session()
    try:
        session.add_all(
            [
                ComponentVersion(
                    component_name="shopee/login",
                    version="1.0.0",
                    file_path="modules/platforms/shopee/components/login_v1_0_0.py",
                    is_stable=True,
                    is_active=True,
                ),
                ComponentVersion(
                    component_name="shopee/login",
                    version="1.1.0",
                    file_path="modules/platforms/shopee/components/login_v1_1_0.py",
                    is_stable=True,
                    is_active=False,
                ),
                ComponentVersion(
                    component_name="shopee/login",
                    version="1.2.0",
                    file_path="modules/platforms/shopee/components/login_v1_2_0.py",
                    is_stable=False,
                    is_active=True,
                ),
            ]
        )
        session.commit()

        service = ComponentVersionService(session)
        rows = service.get_all_stable_versions("shopee/login")

        assert len(rows) == 1
        assert rows[0].version == "1.0.0"
    finally:
        session.close()
        engine.dispose()
