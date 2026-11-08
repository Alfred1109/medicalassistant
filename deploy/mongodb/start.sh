#!/usr/bin/env bash
set -euo pipefail
DB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose -f "$DB_DIR/compose.yml")
"${compose[@]}" up -d mongo
for attempt in {1..30}; do
    if "${compose[@]}" exec -T mongo mongosh --quiet --eval 'db.adminCommand({ping:1})' >/dev/null 2>&1; then
        break
    fi
    if [[ "$attempt" == 30 ]]; then
        echo 'MongoDB did not become reachable; inspect docker compose logs.' >&2
        exit 1
    fi
    sleep 1
done
"${compose[@]}" exec -T mongo mongosh --quiet --file /opt/rehab/init-replica.js
for attempt in {1..30}; do
    if "${compose[@]}" exec -T mongo mongosh --quiet --eval 'if (!db.hello().isWritablePrimary) quit(1)' >/dev/null 2>&1; then
        printf 'MongoDB replica set ready at 127.0.0.1:%s (rehab_rs)\n' "${REHAB_MONGO_PORT:-37021}"
        exit 0
    fi
    sleep 1
done
echo 'Replica set did not elect a primary; inspect docker compose logs.' >&2
exit 1
