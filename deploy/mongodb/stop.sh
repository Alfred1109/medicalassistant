#!/usr/bin/env bash
set -euo pipefail
DB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec docker compose -f "$DB_DIR/compose.yml" stop mongo
