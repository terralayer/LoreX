#!/bin/sh
set -eu

alembic upgrade head

if [ "${LOREX_EMBEDDED_WORKERS:-1}" = "1" ] && [ "${1:-}" = "uvicorn" ]; then
    scanner_pid=""
    download_pid=""
    api_pid=""

    stop_children() {
        for pid in "$scanner_pid" "$download_pid" "$api_pid"; do
            if [ -n "$pid" ]; then
                kill "$pid" 2>/dev/null || true
            fi
        done
        for pid in "$scanner_pid" "$download_pid" "$api_pid"; do
            if [ -n "$pid" ]; then
                wait "$pid" 2>/dev/null || true
            fi
        done
    }

    trap stop_children INT TERM EXIT

    python -m lorex.workers.nntp_scanner --mode live &
    scanner_pid=$!
    python -m lorex.workers.download_worker &
    download_pid=$!
    "$@" &
    api_pid=$!

    set +e
    wait "$api_pid"
    status=$?
    set -e
    stop_children
    trap - INT TERM EXIT
    exit "$status"
fi

exec "$@"
