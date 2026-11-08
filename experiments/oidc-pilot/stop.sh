#!/usr/bin/env bash
set -euo pipefail
PILOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$PILOT_DIR/.runtime/process" ]]; then exit 0; fi
mapfile -t pilot_state < "$PILOT_DIR/.runtime/process"
pilot_pid="${pilot_state[0]}"
pilot_token="${pilot_state[1]}"
if [[ -r "/proc/$pilot_pid/environ" ]] && tr '\0' '\n' < "/proc/$pilot_pid/environ" | grep -Fxq "OIDC_PILOT_TOKEN=$pilot_token"; then
    kill -TERM "$pilot_pid"
fi
rm -f "$PILOT_DIR/.runtime/process"
