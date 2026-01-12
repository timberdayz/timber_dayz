#!/usr/bin/env bash
set -euo pipefail

# 统一数据迁移脚本
# 支持完整数据库迁移、选择性表迁移、增量同步
# 支持本地 ↔ 云端双向迁移

# 使用方法:
#   ./migrate_data.sh --mode full --source local --target cloud
#   ./migrate_data.sh --mode selective --tables "table1,table2" --source local --target cloud
#   ./migrate_data.sh --mode incremental --source local --target cloud

# 颜色输出（Windows 兼容）
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认配置
MODE="full"  # full, selective, incremental
SOURCE="local"
TARGET="cloud"
TABLES=""
DRY_RUN=false
VERIFY=true

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --source)
      SOURCE="$2"
      shift 2
      ;;
    --target)
      TARGET="$2"
      shift 2
      ;;
    --tables)
      TABLES="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-verify)
      VERIFY=false
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --mode MODE          Migration mode: full, selective, incremental (default: full)"
      echo "  --source SOURCE      Source environment: local, cloud (default: local)"
      echo "  --target TARGET      Target environment: local, cloud (default: cloud)"
      echo "  --tables TABLES      Comma-separated table list (for selective mode)"
      echo "  --dry-run            Preview mode, do not execute migration"
      echo "  --no-verify          Skip data verification after migration"
      echo "  --help               Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}[ERROR]${NC} Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# 验证参数
if [ "$MODE" != "full" ] && [ "$MODE" != "selective" ] && [ "$MODE" != "incremental" ]; then
  echo -e "${RED}[ERROR]${NC} Invalid mode: $MODE (must be full, selective, or incremental)"
  exit 1
fi

if [ "$MODE" = "selective" ] && [ -z "$TABLES" ]; then
  echo -e "${RED}[ERROR]${NC} Selective mode requires --tables option"
  exit 1
fi

# 加载环境变量
if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

# 数据库连接配置
if [ "$SOURCE" = "local" ]; then
  SOURCE_DB_URL="${DATABASE_URL:-postgresql://erp_user:erp_pass@localhost:5432/xihong_erp}"
elif [ "$SOURCE" = "cloud" ]; then
  SOURCE_DB_URL="${CLOUD_DATABASE_URL:-}"
  if [ -z "$SOURCE_DB_URL" ]; then
    echo -e "${RED}[ERROR]${NC} CLOUD_DATABASE_URL not set"
    exit 1
  fi
else
  echo -e "${RED}[ERROR]${NC} Invalid source: $SOURCE (must be local or cloud)"
  exit 1
fi

if [ "$TARGET" = "local" ]; then
  TARGET_DB_URL="${DATABASE_URL:-postgresql://erp_user:erp_pass@localhost:5432/xihong_erp}"
elif [ "$TARGET" = "cloud" ]; then
  TARGET_DB_URL="${CLOUD_DATABASE_URL:-}"
  if [ -z "$TARGET_DB_URL" ]; then
    echo -e "${RED}[ERROR]${NC} CLOUD_DATABASE_URL not set"
    exit 1
  fi
else
  echo -e "${RED}[ERROR]${NC} Invalid target: $TARGET (must be local or cloud)"
  exit 1
fi

echo -e "${GREEN}[INFO]${NC} Data Migration Tool"
echo "  Mode: $MODE"
echo "  Source: $SOURCE ($SOURCE_DB_URL)"
echo "  Target: $TARGET ($TARGET_DB_URL)"
if [ "$MODE" = "selective" ]; then
  echo "  Tables: $TABLES"
fi
if [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}[WARN]${NC} DRY-RUN mode: No changes will be made"
fi
echo ""

# 完整数据库迁移
if [ "$MODE" = "full" ]; then
  echo -e "${GREEN}[INFO]${NC} Starting full database migration..."
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] Would export from $SOURCE and import to $TARGET"
    exit 0
  fi
  
  # 创建备份目录
  BACKUP_DIR="backups/migration_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP_DIR"
  
  # 导出源数据库
  echo -e "${GREEN}[INFO]${NC} Exporting source database..."
  pg_dump "$SOURCE_DB_URL" \
    --format=custom \
    --file="$BACKUP_DIR/source_backup.dump" \
    --verbose || {
    echo -e "${RED}[ERROR]${NC} Failed to export source database"
    exit 1
  }
  
  # 备份目标数据库（防止失败）
  echo -e "${GREEN}[INFO]${NC} Backing up target database..."
  pg_dump "$TARGET_DB_URL" \
    --format=custom \
    --file="$BACKUP_DIR/target_backup.dump" \
    --verbose || {
    echo -e "${YELLOW}[WARN]${NC} Failed to backup target database (may not exist)"
  }
  
  # 恢复目标数据库
  echo -e "${GREEN}[INFO]${NC} Importing to target database..."
  pg_restore "$TARGET_DB_URL" \
    --clean \
    --if-exists \
    --verbose \
    "$BACKUP_DIR/source_backup.dump" || {
    echo -e "${RED}[ERROR]${NC} Failed to import to target database"
    echo -e "${YELLOW}[INFO]${NC} Target backup available at: $BACKUP_DIR/target_backup.dump"
    exit 1
  }
  
  echo -e "${GREEN}[OK]${NC} Full database migration completed"
  echo "  Backup location: $BACKUP_DIR"
  
  # 验证数据
  if [ "$VERIFY" = true ]; then
    echo -e "${GREEN}[INFO]${NC} Verifying data migration..."
    python3 scripts/migrate_selective_tables.py \
      --source "$SOURCE_DB_URL" \
      --target "$TARGET_DB_URL" \
      --verify-only || {
      echo -e "${YELLOW}[WARN]${NC} Data verification failed (see logs above)"
    }
  fi

# 选择性表迁移
elif [ "$MODE" = "selective" ]; then
  echo -e "${GREEN}[INFO]${NC} Starting selective table migration..."
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] Would migrate tables: $TABLES"
    exit 0
  fi
  
  # 调用 Python 工具
  python3 scripts/migrate_selective_tables.py \
    --source "$SOURCE_DB_URL" \
    --target "$TARGET_DB_URL" \
    --tables "$TABLES" \
    --verify || {
    echo -e "${RED}[ERROR]${NC} Selective table migration failed"
    exit 1
  }
  
  echo -e "${GREEN}[OK]${NC} Selective table migration completed"

# 增量同步
elif [ "$MODE" = "incremental" ]; then
  echo -e "${GREEN}[INFO]${NC} Starting incremental synchronization..."
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN] Would sync new data from $SOURCE to $TARGET"
    exit 0
  fi
  
  # 调用 Python 工具（增量模式）
  python3 scripts/migrate_selective_tables.py \
    --source "$SOURCE_DB_URL" \
    --target "$TARGET_DB_URL" \
    --incremental \
    --verify || {
    echo -e "${RED}[ERROR]${NC} Incremental synchronization failed"
    exit 1
  }
  
  echo -e "${GREEN}[OK]${NC} Incremental synchronization completed"
fi

echo -e "${GREEN}[OK]${NC} Migration completed successfully"
