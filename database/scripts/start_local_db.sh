#!/usr/bin/env bash
# database/scripts/start_local_db.sh
# Start a disposable PostGIS + pgRouting Docker container for local development.
# This is NOT a Supabase project. It is a local test database only.
#
# Usage:
#   bash database/scripts/start_local_db.sh       # start
#   bash database/scripts/start_local_db.sh stop  # stop and remove
#
# After starting, apply migrations:
#   psql "$DATABASE_URL" -f database/migrations/001_initial.sql
#   psql "$DATABASE_URL" -f database/migrations/002_rls_and_schema_improvements.sql
#   psql "$DATABASE_URL" -f database/verify.sql

set -euo pipefail

CONTAINER_NAME="flood_aware_postgis"
PG_USER="flood_user"
PG_PASSWORD="flood_local_dev_only"
PG_DB="flood_aware"
PG_PORT="15432"

export DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"

if [[ "${1:-}" == "stop" ]]; then
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm   "$CONTAINER_NAME" 2>/dev/null || true
  echo "Container $CONTAINER_NAME stopped and removed."
  exit 0
fi

if docker inspect "$CONTAINER_NAME" &>/dev/null; then
  echo "Container $CONTAINER_NAME already exists. Starting if stopped..."
  docker start "$CONTAINER_NAME" 2>/dev/null || true
else
  echo "Starting PostGIS container: $CONTAINER_NAME"
  docker run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_USER="$PG_USER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -e POSTGRES_DB="$PG_DB" \
    -p "${PG_PORT}:5432" \
    postgis/postgis:17-3.5

  echo "Waiting for PostgreSQL to accept connections..."
  for i in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$PG_USER" -d "$PG_DB" -q; then
      echo "PostgreSQL ready after ${i}s"
      break
    fi
    sleep 1
  done
fi

echo ""
echo "DATABASE_URL=${DATABASE_URL}"
echo ""
echo "Apply migrations:"
echo "  docker exec -i $CONTAINER_NAME psql -U $PG_USER -d $PG_DB < database/migrations/001_initial.sql"
echo "  docker exec -i $CONTAINER_NAME psql -U $PG_USER -d $PG_DB < database/migrations/002_rls_and_schema_improvements.sql"
echo "  docker exec -i $CONTAINER_NAME psql -U $PG_USER -d $PG_DB < database/verify.sql"
