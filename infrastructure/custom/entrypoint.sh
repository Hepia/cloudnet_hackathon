#!/bin/bash

set -uo pipefail

/usr/bin/install_db.sh

# Start the CNC first and wait until it is actually listening on :23 before launching
# the Mirai bot. The bot resolves its CNC to 127.0.0.1:23 and connects once at startup;
# if the CNC is not yet listening its first connect fails and it only reconnects after a
# long, variable backoff, during which attack commands are accepted but nothing floods.
# (Previously mirai was started before cnc, which caused exactly that race.)
/usr/bin/cnc &
pid2=$!

for _ in $(seq 1 50); do
    if ss -lnt 2>/dev/null | grep -q ':23 '; then break; fi
    sleep 0.2
done

/usr/bin/mirai &
pid1=$!

sleep 2
ss -lntu | tail -n +2

# Reap direct children when they exit,
# but keep the container alive.

while true; do
    wait -n || true
    sleep 1
done
