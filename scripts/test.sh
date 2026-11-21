#!/usr/bin/env bash
# Run the full acceptance suite against PostgreSQL 16.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -z "${TEST_DATABASE_URL:-}" ]; then
  echo "TEST_DATABASE_URL is required, e.g. postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME_WITH_TEST" >&2
  exit 2
fi

exec .venv/bin/pytest -q "$@"
