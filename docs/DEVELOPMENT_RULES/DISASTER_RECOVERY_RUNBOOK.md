# Disaster Recovery Runbook

**Version**: v4.20.0
**Target**: PostgreSQL 15+ (Docker), Redis, File Storage
**RPO Target**: <= 15 minutes | **RTO Target**: <= 2 hours

---

## Overview

This runbook describes how to perform a complete recovery drill and production recovery for the XiHong ERP system. Run this drill **once per month** to ensure the recovery process is valid and team members are familiar with the steps.

---

## Part A: Pre-Drill Checklist

Before starting any recovery drill:

- [ ] Confirm you are operating on the **restore environment**, NOT production
- [ ] Note the start time (RTO clock begins)
- [ ] Confirm latest backup is available and the backup age is < 24 hours
- [ ] Confirm Docker Desktop or Docker Engine is running
- [ ] Have the database credentials ready (see `.env` or Docker Compose secrets)
- [ ] Notify team that restore drill is in progress (if relevant)

---

## Part B: PostgreSQL Full Restore (Docker Environment)

### B1: Stop the Application

```bash
# Stop backend and frontend (keep database running for now)
docker compose stop backend frontend celery_worker
```

### B2: Identify the Backup File

```bash
# List available backups (stored in backups/ or object storage)
ls -lh backups/*.sql.gz
# Example output: backups/xihong_erp_20260316_020000.sql.gz
```

### B3: Create a New PostgreSQL Container for Restore Test

```bash
# Use a separate container to avoid impacting the original data
docker run -d \
  --name xihong_restore_test \
  -e POSTGRES_USER=xihong \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=xihong_erp \
  -p 5433:5432 \
  postgres:15
```

### B4: Restore the Backup

```bash
# Wait for PostgreSQL to be ready
docker exec xihong_restore_test pg_isready -U xihong

# Decompress and restore
gunzip -c backups/xihong_erp_20260316_020000.sql.gz | \
  docker exec -i xihong_restore_test psql -U xihong xihong_erp

# Alternative: copy file into container then restore
docker cp backups/xihong_erp_20260316_020000.sql.gz xihong_restore_test:/tmp/
docker exec xihong_restore_test bash -c \
  "gunzip /tmp/xihong_erp_20260316_020000.sql.gz && psql -U xihong xihong_erp < /tmp/xihong_erp_20260316_020000.sql"
```

### B5: Run Restore Verification Script

```bash
# Point the verification script to the restore container
DATABASE_URL=postgresql+asyncpg://xihong:yourpassword@localhost:5433/xihong_erp \
  python scripts/verify_restore.py --hours 48

# Expected output: Verdict: PASS
```

### B6: Check Application Against Restored Database

```bash
# Temporarily point backend to restore container
DATABASE_URL=postgresql+asyncpg://xihong:yourpassword@localhost:5433/xihong_erp \
  uvicorn backend.main:app --port 8001

# Run smoke test
curl http://localhost:8001/health
curl http://localhost:8001/api/users/ -H "Authorization: Bearer <token>"
```

### B7: Record Results

Fill in `scripts/load_test/reports/REPORT_TEMPLATE.md` adapted for this drill:
- Time to restore: _____ minutes
- verify_restore.py: PASS / FAIL
- Manual spot checks: PASS / FAIL
- Notes on issues encountered:

### B8: Cleanup

```bash
docker stop xihong_restore_test
docker rm xihong_restore_test
# Restart application
docker compose start backend frontend celery_worker
```

---

## Part C: Production Restore Procedure (Emergency)

**WARNING: Only use this procedure when instructed by the on-call lead after incident declaration.**

### C1: Declare Incident

1. Set system to maintenance mode (if available)
2. Notify all active users via system announcement
3. Record incident start time

### C2: Stop Application Services

```bash
docker compose stop backend frontend celery_worker
# Keep database running for final WAL flush if possible
```

### C3: Export Current State (if DB is still accessible)

```bash
pg_dump -h localhost -U xihong -d xihong_erp \
  --no-password -F c -f backups/pre_restore_$(date +%Y%m%d_%H%M%S).dump
```

### C4: Select Recovery Point

Determine which backup to restore:
- For data corruption: last backup BEFORE the corruption event
- For hardware failure: latest available backup
- For accidental delete: point-in-time recovery using WAL archive if available

### C5: Restore Database

```bash
# Stop all connections
docker compose stop backend

# Drop and recreate database
docker exec xihong_postgres psql -U xihong -c "DROP DATABASE xihong_erp;"
docker exec xihong_postgres psql -U xihong -c "CREATE DATABASE xihong_erp;"

# Restore
gunzip -c backups/SELECTED_BACKUP.sql.gz | \
  docker exec -i xihong_postgres psql -U xihong xihong_erp
```

### C6: Run Alembic to Apply Missing Migrations

```bash
# Only if backup is older than current schema version
alembic upgrade head
```

### C7: Verify and Restart

```bash
python scripts/verify_restore.py --hours 48
docker compose start backend frontend celery_worker
# Monitor logs for 10 minutes
docker compose logs -f backend
```

### C8: Post-Incident

1. Note RTO achieved (start to service restoration)
2. Estimate data loss window (RPO achieved)
3. Write incident report within 24 hours
4. Schedule follow-up to address root cause

---

## Part D: Redis Recovery

Redis uses AOF persistence + daily RDB snapshots.

```bash
# Stop Redis
docker compose stop redis

# Replace appendonly.aof with backup
cp backups/redis_aof_YYYYMMDD.aof /var/lib/redis/appendonly.aof

# Or restore from RDB snapshot
cp backups/redis_dump_YYYYMMDD.rdb /var/lib/redis/dump.rdb

# Restart
docker compose start redis
```

Verify:
```bash
docker exec xihong_redis redis-cli ping
docker exec xihong_redis redis-cli info keyspace
```

---

## Part E: Drill Tracking Log

Record each monthly drill in this table:

| Date | Performed By | Backup Age | Restore Duration | verify_restore | RTO Achieved | Issues |
|---|---|---|---|---|---|---|
| YYYY-MM-DD | [name] | Xh | XX min | PASS/FAIL | XX min | [notes] |

---

## Part F: Improvement Items

If any drill reveals issues, add them here and resolve before the next drill:

| Date Identified | Issue | Owner | Target Resolution Date | Status |
|---|---|---|---|---|
| - | - | - | - | - |
