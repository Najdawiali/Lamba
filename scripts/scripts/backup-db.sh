#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/lamba/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/lamba_${TIMESTAMP}.sql.gz"

# Dump and compress
docker compose -f /opt/lamba/docker-compose.yml exec -T postgres \
  pg_dump -U eagle -d eagle_vision --no-owner --no-privileges \
  | gzip > "$BACKUP_FILE"

# Verify the backup isn't empty
if [ ! -s "$BACKUP_FILE" ]; then
  echo "ERROR: Backup file is empty!" >&2
  rm -f "$BACKUP_FILE"
  exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "$(date): Backup created: $BACKUP_FILE ($SIZE)"

# Delete backups older than 7 days
find "$BACKUP_DIR" -name "lamba_*.sql.gz" -mtime +7 -delete

echo "$(date): Old backups cleaned"
