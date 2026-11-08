#!/usr/bin/env bash
set -euo pipefail
PILOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${QUESTIONNAIRE_ROOT:-$(dirname -- "$(dirname -- "$(dirname -- "$PILOT_DIR")")")/康复问卷管理系统}"
if [[ -e "$PILOT_DIR/.deps" ]]; then
    echo 'Private dependencies already exist; inspect them before reinstalling.' >&2
    exit 1
fi
exec "$SOURCE_ROOT/venv/bin/python" -m pip install --target "$PILOT_DIR/.deps" -r "$PILOT_DIR/requirements.lock"
