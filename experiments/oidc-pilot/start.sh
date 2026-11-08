#!/usr/bin/env bash
set -euo pipefail
PILOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${QUESTIONNAIRE_ROOT:-$(dirname -- "$(dirname -- "$(dirname -- "$PILOT_DIR")")")/康复问卷管理系统}"
export OIDC_PILOT_TOKEN="$("$SOURCE_ROOT/venv/bin/python" -c 'import secrets;print(secrets.token_hex(24))')"
mkdir -p "$PILOT_DIR/.runtime"
chmod 700 "$PILOT_DIR/.runtime"
if [[ -f "$PILOT_DIR/.runtime/process" ]]; then
    read -r existing_pid < "$PILOT_DIR/.runtime/process"
    if [[ "$existing_pid" =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null; then
        echo 'Pilot process record is still live; use stop.sh or inspect it first.' >&2
        exit 1
    fi
fi
PILOT_RUN="$PILOT_DIR/.runtime/run-$OIDC_PILOT_TOKEN"
printf '%s\n%s\n' "$$" "$OIDC_PILOT_TOKEN" > "$PILOT_DIR/.runtime/process"
chmod 600 "$PILOT_DIR/.runtime/process"
exec "$SOURCE_ROOT/venv/bin/python" "$PILOT_DIR/pilot.py" --runtime "$PILOT_RUN"
