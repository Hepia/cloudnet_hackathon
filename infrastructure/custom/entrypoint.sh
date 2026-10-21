#!/bin/bash

set -uo pipefail

/usr/bin/install_db.sh

/usr/bin/mirai &
pid1=$!

/usr/bin/cnc &
pid2=$!

sleep 2
ss -lntu | tail -n +2

# Reap direct children when they exit,
# but keep the container alive.

while true; do
    wait -n || true
    sleep 1
done
