from __future__ import annotations

import hashlib
import os

from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.engine import make_url

from backend.models.database import DATABASE_URL, SessionLocal
from backend.services.cloud_b_class_auto_sync_worker import CloudBClassAutoSyncWorker
from backend.services.cloud_b_class_mirror_manager import CloudBClassMirrorManager
from backend.services.cloud_b_class_sync_checkpoint_service import (
    CloudBClassSyncCheckpointService,
)
from backend.services.cloud_b_class_sync_service import (
    CloudBClassSyncService,
    SQLAlchemyBClassSourceReader,
    SQLAlchemyCloudWriter,
)


class NoOpCloudBClassMirrorManager:
    """Dry-run mirror manager that never touches the cloud database."""

    def ensure_cloud_schema_exists(self) -> None:
        return None

    def ensure_cloud_mirror_table(self, table_name: str, data_domain: str) -> None:
        return None


def _build_checkpoint_scope_key(cloud_database_url: str | None, dry_run: bool) -> str:
    if dry_run:
        return "cloud_sync:dry_run"

    if not cloud_database_url:
        return "cloud_sync:local"

    parsed = make_url(cloud_database_url)
    identity = (
        f"{parsed.drivername.split('+', 1)[0]}://"
        f"{parsed.host or ''}:{parsed.port or ''}/"
        f"{parsed.database or ''}"
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"cloud_sync:{digest}"


def _build_cloud_sync_service(
    *,
    local_engine,
    cloud_engine,
    session_factory,
    dry_run: bool,
    checkpoint_scope: str,
) -> CloudBClassSyncService:
    checkpoint_service = CloudBClassSyncCheckpointService(session_factory())
    mirror_manager = NoOpCloudBClassMirrorManager() if dry_run else CloudBClassMirrorManager(cloud_engine)
    source_reader = SQLAlchemyBClassSourceReader(local_engine)
    cloud_writer = SQLAlchemyCloudWriter(cloud_engine, dry_run=dry_run)

    def inspect_tables():
        inspector = sa_inspect(local_engine)
        return inspector.get_table_names(schema="b_class")

    return CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=mirror_manager,
        source_batch_reader=source_reader,
        remote_writer=cloud_writer,
        table_inspector=inspect_tables,
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        owns_engines=False,
        checkpoint_scope=checkpoint_scope,
    )


def build_cloud_sync_service_from_env(dry_run: bool = False) -> CloudBClassSyncService:
    cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
    if not dry_run and not cloud_database_url:
        raise RuntimeError("CLOUD_DATABASE_URL is required unless dry_run is enabled")

    local_engine = create_engine(DATABASE_URL)
    cloud_engine = create_engine(cloud_database_url) if cloud_database_url else local_engine
    checkpoint_scope = _build_checkpoint_scope_key(cloud_database_url, dry_run)

    service = _build_cloud_sync_service(
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        session_factory=SessionLocal,
        dry_run=dry_run,
        checkpoint_scope=checkpoint_scope,
    )
    service.owns_engines = True
    return service


class CloudSyncWorkerFactory:
    def __init__(self, *, local_engine, cloud_engine, session_factory, dry_run: bool) -> None:
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.session_factory = session_factory
        self.dry_run = dry_run
        self.checkpoint_scope = _build_checkpoint_scope_key(
            str(cloud_engine.url) if hasattr(cloud_engine, "url") else None,
            dry_run,
        )

    def __call__(self):
        db = self.session_factory()
        service = _build_cloud_sync_service(
            local_engine=self.local_engine,
            cloud_engine=self.cloud_engine,
            session_factory=self.session_factory,
            dry_run=self.dry_run,
            checkpoint_scope=self.checkpoint_scope,
        )
        return CloudBClassAutoSyncWorker(db=db, sync_executor=service)

    def close(self) -> None:
        try:
            self.local_engine.dispose()
        finally:
            if self.cloud_engine is not self.local_engine:
                self.cloud_engine.dispose()


def build_cloud_sync_worker_factory_from_env(dry_run: bool = False):
    cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
    if not dry_run and not cloud_database_url:
        raise RuntimeError("CLOUD_DATABASE_URL is required unless dry_run is enabled")

    local_engine = create_engine(DATABASE_URL)
    cloud_engine = create_engine(cloud_database_url) if cloud_database_url else local_engine

    return CloudSyncWorkerFactory(
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        session_factory=SessionLocal,
        dry_run=dry_run,
    )
